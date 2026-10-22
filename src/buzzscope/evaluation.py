"""Score a run against the planted events in a synthetic scenario.

Metrics (all in [0, 1]):
- event_recall       planted events that got a finding of kind "event" within ±2 days
- event_precision    "event" findings that correspond to a planted event
                     (decoys and noise reported as events lower this)
- decoy_rejection    decoy spikes NOT reported as events
- cause_accuracy     matched findings whose cause names the planted cause (alias match)
- sentiment_accuracy matched findings with the planted sentiment
- evidence_precision cited posts that really belong to the planted event (hidden label)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import timedelta

from buzzscope.models import Finding, Post, Report
from buzzscope.synthetic.scenarios import EventSpec, Scenario

TOLERANCE = timedelta(days=2)


@dataclass
class EventCheck:
    event_id: str
    planted_date: str
    is_decoy: bool
    finding_date: str | None = None
    finding_kind: str | None = None
    cause_ok: bool | None = None
    sentiment_ok: bool | None = None
    evidence_hits: int = 0
    evidence_total: int = 0
    cause: str = ""


@dataclass
class ScenarioScore:
    scenario: str
    checks: list[EventCheck] = field(default_factory=list)
    n_event_findings: int = 0
    n_true_event_findings: int = 0


def _nearest(findings: list[Finding], ev: EventSpec) -> Finding | None:
    near = [f for f in findings if abs(f.spike_date - ev.date) <= TOLERANCE]
    return min(near, key=lambda f: abs(f.spike_date - ev.date)) if near else None


def score_report(report: Report, scenario: Scenario, posts_by_id: dict[str, Post]) -> ScenarioScore:
    score = ScenarioScore(scenario=scenario.key)
    events = [f for f in report.findings if f.kind == "event"]
    score.n_event_findings = len(events)
    # one-to-one: each planted event can justify at most one "event" finding
    score.n_true_event_findings = sum(_nearest(events, ev) is not None for ev in scenario.gold_events)

    for ev in scenario.events:
        check = EventCheck(event_id=ev.id, planted_date=ev.date.isoformat(), is_decoy=not ev.relevant)
        f = _nearest(report.findings, ev)
        if f is not None:
            check.finding_date, check.finding_kind, check.cause = f.spike_date.isoformat(), f.kind, f.cause
            if ev.relevant and f.kind == "event":
                check.cause_ok = any(a.lower() in f.cause.lower() for a in ev.aliases)
                check.sentiment_ok = f.sentiment == ev.sentiment
                labels = [
                    posts_by_id[pid].labels.get("event") for pid in f.evidence_post_ids if pid in posts_by_id
                ]
                check.evidence_total = len(labels)
                check.evidence_hits = sum(lab == ev.id for lab in labels)
        score.checks.append(check)
    return score


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 3) if b else None


def aggregate(scores: list[ScenarioScore]) -> dict[str, float | None]:
    gold = [c for s in scores for c in s.checks if not c.is_decoy]
    decoys = [c for s in scores for c in s.checks if c.is_decoy]
    matched = [c for c in gold if c.finding_kind == "event"]
    return {
        "event_recall": _ratio(len(matched), len(gold)),
        "event_precision": _ratio(
            sum(s.n_true_event_findings for s in scores), sum(s.n_event_findings for s in scores)
        ),
        "decoy_rejection": _ratio(sum(c.finding_kind != "event" for c in decoys), len(decoys)),
        "cause_accuracy": _ratio(sum(bool(c.cause_ok) for c in matched), len(matched)),
        "sentiment_accuracy": _ratio(sum(bool(c.sentiment_ok) for c in matched), len(matched)),
        "evidence_precision": _ratio(
            sum(c.evidence_hits for c in matched), sum(c.evidence_total for c in matched)
        ),
    }


def to_dict(scores: list[ScenarioScore]) -> dict:
    return {"summary": aggregate(scores), "scenarios": [asdict(s) for s in scores]}


METRIC_LABELS = {
    "event_recall": "事件召回率 Event recall",
    "event_precision": "事件精確率 Event precision",
    "decoy_rejection": "撞名排除率 Decoy rejection",
    "cause_accuracy": "原因正確率 Cause accuracy",
    "sentiment_accuracy": "情緒正確率 Sentiment accuracy",
    "evidence_precision": "證據精確率 Evidence precision",
}


def to_markdown(mode: str, scores: list[ScenarioScore], model: str | None = None) -> str:
    summary = aggregate(scores)
    lines = [f"# Eval 結果：{mode}" + (f"（{model}）" if model else ""), "", "| 指標 | 分數 |", "|---|---|"]
    for key, label in METRIC_LABELS.items():
        v = summary[key]
        lines.append(f"| {label} | {'—' if v is None else f'{v:.0%}'} |")
    lines += [
        "",
        "## 逐事件結果",
        "",
        "| 情境 | 埋設事件 | 日期 | 類型 | Agent 判斷 | 原因對 | 情緒對 | 證據 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in scores:
        for c in s.checks:
            mark = {True: "✓", False: "✗", None: "—"}
            ev = f"{c.evidence_hits}/{c.evidence_total}" if c.evidence_total else "—"
            lines.append(
                f"| {s.scenario} | {c.event_id} | {c.planted_date} | {'撞名' if c.is_decoy else '事件'} | "
                f"{c.finding_kind or '未偵測'} | {mark[c.cause_ok]} | {mark[c.sentiment_ok]} | {ev} |"
            )
    extra = [s for s in scores if s.n_event_findings > s.n_true_event_findings]
    if extra:
        lines += ["", "被誤報為事件（非埋設事件）的 spike 數："]
        lines += [f"- {s.scenario}: {s.n_event_findings - s.n_true_event_findings}" for s in extra]
    return "\n".join(lines) + "\n"
