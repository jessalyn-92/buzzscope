"""Render a Report as Markdown (for the CLI, downloads, and GitHub-friendly output)."""

from __future__ import annotations

from buzzscope.models import Report

KIND_LABEL = {"event": "事件", "unrelated": "撞名／無關", "noise": "正常波動"}
SENT_LABEL = {"positive": "正面", "negative": "負面", "neutral": "中性", "mixed": "褒貶不一"}


def verification_badge(verified: bool | None) -> str:
    return {True: "✅ 證據支持", False: "⚠️ 證據不足", None: "— 未查核"}[verified]


def to_markdown(report: Report, post_urls: dict[str, str] | None = None) -> str:
    post_urls = post_urls or {}
    p = report.plan
    lines = [
        f"# 輿情分析報告：{p.entity}",
        "",
        f"> 問題：{report.question}",
        "",
        f"- 分析模式：{'Agent（LLM）' if report.mode == 'agent' else '離線 baseline'}",
        f"- 期間：{report.start} ～ {report.end}（{p.days} 天）",
        f"- 關鍵字：{'、'.join(p.keywords)}"
        + (f"；排除：{'、'.join(p.exclude_keywords)}" if p.exclude_keywords else ""),
        f"- 相關文章：{report.n_posts} 篇；聲量異常：{len(report.spikes)} 次",
    ]
    if report.usage.llm_calls:
        lines.append(
            f"- LLM 呼叫 {report.usage.llm_calls} 次，tokens：輸入 {report.usage.input_tokens:,} / 輸出 {report.usage.output_tokens:,}"
        )
    lines += ["", "## 總結", "", report.overall_summary, "", "## 聲量異常與原因", ""]
    if not report.findings:
        lines.append("此期間沒有偵測到明顯的聲量異常。")
    for f in report.findings:
        lines += [
            f"### {f.spike_date}｜{KIND_LABEL[f.kind]}｜{SENT_LABEL[f.sentiment]}",
            "",
            f"**原因：** {f.cause}",
            "",
        ]
        if f.summary:
            lines += [f.summary, ""]
        lines.append(
            f"信心 {f.confidence:.0%}｜{verification_badge(f.verified)}"
            + (f"：{f.verification_note}" if f.verification_note else "")
        )
        if f.evidence_post_ids:
            lines += ["", "證據文章："]
            for pid in f.evidence_post_ids:
                url = post_urls.get(pid)
                lines.append(f"- [{pid}]({url})" if url else f"- {pid}")
        lines.append("")
    return "\n".join(lines)
