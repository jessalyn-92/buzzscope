"""Non-LLM baseline analyst: explains each spike with its most distinctive terms.

It is the yardstick for the agent. It is free and deterministic, but it can't tell
a keyword collision (晨光 = morning light) or random noise from a real event.
"""

from __future__ import annotations

from datetime import timedelta

from buzzscope.analysis.keyness import distinctive_terms
from buzzscope.analysis.sentiment import label, post_sentiment
from buzzscope.models import Finding, Post, ResearchPlan, Spike, TraceStep

SENT_ZH = {"positive": "偏正面", "negative": "偏負面", "neutral": "中性"}


def explain_spikes(
    plan: ResearchPlan, posts: list[Post], spikes: list[Spike]
) -> tuple[list[Finding], list[TraceStep]]:
    findings, trace = [], []
    for s in spikes:
        window = [p for p in posts if s.start <= p.day <= s.end + timedelta(days=1)]
        baseline = [p for p in posts if s.start - timedelta(days=14) <= p.day < s.start]
        terms = distinctive_terms(window, baseline, k=5, exclude=plan.keywords + [plan.entity])
        top = [t for t, _, _ in terms]
        scores = [post_sentiment(p) for p in window]
        mean = sum(scores) / len(scores) if scores else 0.0
        lead = top[0] if top else ""
        evidence = sorted(
            (p for p in window if lead and lead in f"{p.title}{p.content}"),
            key=lambda p: len(p.comments),
            reverse=True,
        )[:3]
        findings.append(
            Finding(
                spike_date=s.peak_date,
                kind="event",
                cause="關鍵詞：" + "、".join(top) if top else "（無明顯特徵詞）",
                sentiment=label(mean),
                summary=f"{s.peak_date} 聲量 {s.peak_count} 篇（平常約 {s.baseline:g} 篇/日），字典情緒分數 {mean:+.2f}。",
                evidence_post_ids=[p.post_id for p in evidence],
                confidence=0.5,
            )
        )
        trace.append(TraceStep(kind="tool", title=f"compare_terms({s.start}~{s.end})", detail="、".join(top)))
    return findings, trace


def baseline_summary(plan: ResearchPlan, posts: list[Post], findings: list[Finding]) -> str:
    if not posts:
        return f"最近 {plan.days} 天沒有找到與「{plan.entity}」相關的文章。"
    scores = [post_sentiment(p) for p in posts]
    mean = sum(scores) / len(scores)
    parts = [
        f"最近 {plan.days} 天共 {len(posts)} 篇相關文章，整體情緒{SENT_ZH[label(mean)]}（{mean:+.2f}）。"
    ]
    if findings:
        parts.append(
            f"偵測到 {len(findings)} 次聲量異常："
            + "；".join(f"{f.spike_date} {f.cause}" for f in findings)
            + "。"
        )
    parts.append("（離線模式：原因只列出特徵詞，無法判斷撞名或雜訊，需人工閱讀確認。）")
    return "".join(parts)
