"""The tools the investigator agent can call. Every tool reads from the collected posts only.

Two rules keep the agent honest:
- Ground-truth labels in synthetic data are never serialized into tool output.
- submit_findings is validated: evidence must exist, must have been read, and must fall
  inside the spike window. Invalid submissions are bounced back with the reasons.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, timedelta
from typing import Any

import pandas as pd

from buzzscope.analysis.keyness import distinctive_terms
from buzzscope.analysis.sentiment import label, post_sentiment
from buzzscope.models import Finding, Post, Spike

MAX_READ_PER_CALL = 5
EVIDENCE_SLACK_BEFORE = timedelta(days=2)
EVIDENCE_SLACK_AFTER = timedelta(days=4)


def _d(s: str) -> date:
    return date.fromisoformat(str(s)[:10])


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_overview",
            "description": "資料總覽：文章數、日期範圍、看板分布、整體情緒、全期間高頻詞。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_spikes",
            "description": "用統計方法（滾動中位數 + MAD）找出聲量異常暴增的期間。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_volume",
            "description": "取得某段期間每日文章數與平均情緒分數（-1 到 1）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_terms",
            "description": "比較某段期間與前 14 天，找出該期間特別常出現的詞（找原因的線索，不是答案）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_posts",
            "description": "在已收集的文章中搜尋（標題、內文或推文包含 query），回傳文章 id、日期、標題、推噓數，依討論熱度排序。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜尋字串；留空表示該期間所有文章"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD，可省略"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD，可省略"},
                    "limit": {"type": "integer", "description": "最多幾篇，預設 10"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_posts",
            "description": f"閱讀文章全文（截斷）與前幾則推文。一次最多 {MAX_READ_PER_CALL} 篇。",
            "parameters": {
                "type": "object",
                "properties": {"post_ids": {"type": "array", "items": {"type": "string"}}},
                "required": ["post_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_findings",
            "description": "提交最終分析。每個偵測到的 spike 都要有一筆 finding。",
            "parameters": {
                "type": "object",
                "properties": {
                    "findings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "spike_date": {"type": "string", "description": "spike 高峰日 YYYY-MM-DD"},
                                "kind": {
                                    "type": "string",
                                    "enum": ["event", "unrelated", "noise"],
                                    "description": "event=與分析對象有關的具體事件；unrelated=關鍵字撞名、與對象無關；noise=沒有共同事件的正常波動",
                                },
                                "cause": {
                                    "type": "string",
                                    "description": "具體原因：發生了什麼事（一句話）",
                                },
                                "sentiment": {
                                    "type": "string",
                                    "enum": ["positive", "negative", "neutral", "mixed"],
                                },
                                "summary": {"type": "string", "description": "2-3 句說明，包含網友主要反應"},
                                "evidence_post_ids": {"type": "array", "items": {"type": "string"}},
                                "confidence": {"type": "number", "description": "0 到 1"},
                            },
                            "required": [
                                "spike_date",
                                "kind",
                                "cause",
                                "sentiment",
                                "summary",
                                "evidence_post_ids",
                                "confidence",
                            ],
                        },
                    },
                    "overall_summary": {
                        "type": "string",
                        "description": "給品牌/公關主管看的 3-5 句總結與建議",
                    },
                },
                "required": ["findings", "overall_summary"],
            },
        },
    },
]


class ToolBox:
    def __init__(
        self, posts: list[Post], series: pd.DataFrame, spikes: list[Spike], entity: str, keywords: list[str]
    ):
        self.posts = sorted(posts, key=lambda p: p.published_at)
        self.by_id = {p.post_id: p for p in self.posts}
        self.series = series
        self.spikes = spikes
        self.entity = entity
        self.keywords = keywords
        self.read_ids: set[str] = set()
        self.submitted: tuple[list[Finding], str] | None = None
        self.rejections = 0

    # ---- helpers -------------------------------------------------------------------------
    def _between(self, start: date, end: date) -> list[Post]:
        return [p for p in self.posts if start <= p.day <= end]

    @staticmethod
    def _brief(p: Post) -> dict[str, Any]:
        return {
            "id": p.post_id,
            "date": p.day.isoformat(),
            "board": p.board,
            "title": p.title,
            "comments": len(p.comments),
            "push": sum(c.tag == "推" for c in p.comments),
            "boo": sum(c.tag == "噓" for c in p.comments),
        }

    # ---- tools ---------------------------------------------------------------------------
    def get_overview(self) -> dict[str, Any]:
        if not self.posts:
            return {"n_posts": 0, "note": "沒有收集到文章"}
        scores = [post_sentiment(p) for p in self.posts]
        mid = len(self.posts) // 2
        terms = distinctive_terms(self.posts, [], k=12, exclude=self.keywords + [self.entity], min_docs=5)
        return {
            "entity": self.entity,
            "keywords": self.keywords,
            "n_posts": len(self.posts),
            "date_range": [self.posts[0].day.isoformat(), self.posts[-1].day.isoformat()],
            "posts_per_day_median": float(self.series["count"].median()),
            "boards": dict(Counter(p.board for p in self.posts).most_common(8)),
            "mean_sentiment": round(sum(scores) / len(scores), 3),
            "sentiment_first_half_vs_second_half": [
                round(sum(scores[:mid]) / max(mid, 1), 3),
                round(sum(scores[mid:]) / max(len(scores) - mid, 1), 3),
            ],
            "frequent_terms": [t for t, _, _ in terms],
        }

    def detect_spikes(self) -> dict[str, Any]:
        return {
            "n_spikes": len(self.spikes),
            "spikes": [
                {
                    "start": s.start.isoformat(),
                    "end": s.end.isoformat(),
                    "peak_date": s.peak_date.isoformat(),
                    "peak_posts": s.peak_count,
                    "baseline_posts_per_day": s.baseline,
                    "zscore": s.zscore,
                }
                for s in self.spikes
            ],
        }

    def get_daily_volume(self, start_date: str, end_date: str) -> dict[str, Any]:
        start, end = _d(start_date), _d(end_date)
        rows = self.series.loc[(self.series.index >= start) & (self.series.index <= end)]
        return {
            "days": [
                {
                    "date": d.isoformat(),
                    "posts": int(r["count"]),
                    "sentiment": None if pd.isna(r["sentiment"]) else float(r["sentiment"]),
                }
                for d, r in rows.iterrows()
            ]
        }

    def compare_terms(self, start_date: str, end_date: str) -> dict[str, Any]:
        start, end = _d(start_date), _d(end_date)
        window = self._between(start, end)
        baseline = self._between(start - timedelta(days=14), start - timedelta(days=1))
        terms = distinctive_terms(window, baseline, k=12, exclude=self.keywords + [self.entity])
        return {
            "window_posts": len(window),
            "baseline_posts": len(baseline),
            "distinctive_terms": [{"term": t, "docs": n} for t, _, n in terms],
        }

    def search_posts(
        self, query: str = "", start_date: str | None = None, end_date: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        start = _d(start_date) if start_date else date.min
        end = _d(end_date) if end_date else date.max
        hits = [p for p in self._between(start, end) if not query or query in p.full_text]
        hits.sort(key=lambda p: len(p.comments), reverse=True)  # most-discussed first
        limit = max(1, min(int(limit or 10), 20))
        return {"total_matches": len(hits), "posts": [self._brief(p) for p in hits[:limit]]}

    def read_posts(self, post_ids: list[str]) -> dict[str, Any]:
        out, missing = [], []
        for pid in post_ids[:MAX_READ_PER_CALL]:
            p = self.by_id.get(pid)
            if p is None:
                missing.append(pid)
                continue
            self.read_ids.add(pid)
            out.append(
                {
                    **self._brief(p),
                    "content": p.content[:500],
                    "top_comments": [f"{c.tag} {c.content}" for c in p.comments[:8]],
                    "lexicon_sentiment": label(post_sentiment(p)),
                }
            )
        result: dict[str, Any] = {"posts": out}
        if missing:
            result["not_found"] = missing
        if len(post_ids) > MAX_READ_PER_CALL:
            result["note"] = f"一次最多讀 {MAX_READ_PER_CALL} 篇，其餘請再呼叫一次"
        return result

    def submit_findings(self, findings: list[dict[str, Any]], overall_summary: str) -> dict[str, Any]:
        errors: list[str] = []
        parsed: list[Finding] = []
        for i, raw in enumerate(findings):
            try:
                f = Finding(
                    spike_date=_d(raw["spike_date"]),
                    kind=raw.get("kind", "event"),
                    cause=str(raw.get("cause", "")).strip(),
                    sentiment=raw.get("sentiment", "neutral"),
                    summary=str(raw.get("summary", "")),
                    evidence_post_ids=list(raw.get("evidence_post_ids", [])),
                    confidence=float(raw.get("confidence", 0.5)),
                )
            except Exception as exc:  # noqa: BLE001 - report any malformed item back to the agent
                errors.append(f"finding #{i + 1} 格式錯誤：{exc}")
                continue
            spike = self._spike_for(f.spike_date)
            if spike is None:
                errors.append(f"{f.spike_date} 不對應任何偵測到的 spike（請使用 detect_spikes 的 peak_date）")
                continue
            f.spike_date = spike.peak_date
            if not f.cause:
                errors.append(f"{f.spike_date}：cause 不能是空的")
            if f.kind != "noise" and not f.evidence_post_ids:
                errors.append(f"{f.spike_date}：event/unrelated 至少要附 1 篇證據文章")
            for pid in f.evidence_post_ids:
                p = self.by_id.get(pid)
                if p is None:
                    errors.append(f"{f.spike_date}：證據 {pid} 不存在")
                elif pid not in self.read_ids:
                    errors.append(f"{f.spike_date}：證據 {pid} 你還沒用 read_posts 讀過")
                elif not (spike.start - EVIDENCE_SLACK_BEFORE <= p.day <= spike.end + EVIDENCE_SLACK_AFTER):
                    errors.append(f"{f.spike_date}：證據 {pid}（{p.day}）不在這個 spike 的期間內")
            parsed.append(f)

        covered = {f.spike_date for f in parsed}
        missing = [s.peak_date.isoformat() for s in self.spikes if s.peak_date not in covered]
        if missing:
            errors.append(f"以下 spike 還沒有 finding：{', '.join(missing)}")

        if errors and self.rejections < 2:
            self.rejections += 1
            return {"accepted": False, "errors": errors, "hint": "修正後再呼叫一次 submit_findings"}
        self.submitted = (parsed, overall_summary)
        return {"accepted": True, "warnings": errors}

    def _spike_for(self, d: date) -> Spike | None:
        for s in self.spikes:
            if s.start - timedelta(days=1) <= d <= s.end + timedelta(days=1):
                return s
        return None

    # ---- dispatch ------------------------------------------------------------------------
    def dispatch(self, name: str, arguments: str | dict[str, Any]) -> str:
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else dict(arguments)
            fn = getattr(self, name, None)
            if name.startswith("_") or name not in {t["function"]["name"] for t in TOOL_SPECS} or fn is None:
                return json.dumps({"error": f"未知的工具 {name}"}, ensure_ascii=False)
            return json.dumps(fn(**args), ensure_ascii=False, default=str)
        except Exception as exc:  # noqa: BLE001 - tool errors go back to the model, not up the stack
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
