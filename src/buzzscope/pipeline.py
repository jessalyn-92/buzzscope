"""End-to-end run: plan → collect → measure → investigate → verify → report."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Literal

import pandas as pd

from buzzscope.agent.investigator import investigate
from buzzscope.agent.llm import LLMClient
from buzzscope.agent.planner import heuristic_plan, llm_plan
from buzzscope.agent.verifier import verify_findings
from buzzscope.analysis.baseline import baseline_summary, explain_spikes
from buzzscope.analysis.volume import daily_series, detect_spikes
from buzzscope.models import Post, Report, ResearchPlan, TraceStep, Usage
from buzzscope.scraper.base import Source

Mode = Literal["agent", "baseline"]


def run_analysis(
    question: str,
    source: Source,
    mode: Mode = "baseline",
    llm: LLMClient | None = None,
    days: int = 90,
    plan_override: ResearchPlan | None = None,
    max_steps: int = 24,
    verify: bool = True,
    on_step: Callable[[TraceStep], None] | None = None,
) -> tuple[Report, pd.DataFrame, list[Post]]:
    """Returns (report, daily series DataFrame, collected posts)."""
    if mode == "agent" and llm is None:
        raise ValueError("agent mode needs an LLM client (set OPENAI_API_KEY)")
    trace: list[TraceStep] = []

    def log(step: TraceStep) -> None:
        trace.append(step)
        if on_step:
            on_step(step)

    # 1. plan
    if plan_override is not None:
        plan = plan_override
    elif mode == "agent" and llm is not None:
        plan = llm_plan(question, llm, days)
    else:
        plan = heuristic_plan(question, days)
    log(
        TraceStep(
            kind="plan",
            title=f"研究規劃：{plan.entity}",
            detail=f"關鍵字 {plan.keywords}；排除 {plan.exclude_keywords}；看板 {plan.boards}；{plan.days} 天。{plan.rationale}",
        )
    )

    # 2. collect
    posts = source.fetch(plan, on_progress=lambda msg: log(TraceStep(kind="fetch", title=msg)))
    end = source.reference_now.date() - timedelta(days=1)
    start = end - timedelta(days=plan.days - 1)
    posts = [p for p in posts if start <= p.day <= end]

    # 3. measure
    series = daily_series(posts, start, end)
    spikes = detect_spikes(series)
    log(
        TraceStep(
            kind="info",
            title=f"統計偵測到 {len(spikes)} 次聲量異常",
            detail="、".join(f"{s.peak_date}（{s.peak_count} 篇，平常 {s.baseline:g}）" for s in spikes),
        )
    )

    # 4. investigate
    usage = Usage()
    if mode == "agent" and llm is not None:
        findings, summary, _ = investigate(llm, plan, posts, series, spikes, max_steps=max_steps, on_step=log)
        # 5. verify (independent second opinion)
        if verify and findings:
            verify_findings(llm, plan.entity, findings, {p.post_id: p for p in posts})
            n_bad = sum(f.verified is False for f in findings)
            log(
                TraceStep(
                    kind="verify", title=f"查核完成：{len(findings) - n_bad}/{len(findings)} 項有證據支持"
                )
            )
        usage = llm.usage
    else:
        findings, steps = explain_spikes(plan, posts, spikes)
        for s in steps:
            log(s)
        summary = baseline_summary(plan, posts, findings)

    report = Report(
        question=question,
        mode=mode,
        plan=plan,
        n_posts=len(posts),
        start=start,
        end=end,
        spikes=spikes,
        findings=sorted(findings, key=lambda f: f.spike_date),
        overall_summary=summary,
        trace=trace,
        usage=usage,
    )
    return report, series, posts
