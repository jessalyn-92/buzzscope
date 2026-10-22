import json

import pytest
from policy_llm import PolicyLLM

from buzzscope.agent.llm import ScriptedLLM, parse_json
from buzzscope.agent.planner import heuristic_plan, llm_plan
from buzzscope.evaluation import aggregate, score_report
from buzzscope.pipeline import run_analysis
from buzzscope.scraper.base import SyntheticSource
from buzzscope.synthetic.generator import load_dataset
from buzzscope.synthetic.scenarios import SCENARIOS


@pytest.fixture
def coffee(tmp_path):
    return SyntheticSource("coffee", tmp_path)


def test_heuristic_plan_extracts_entity_and_short_form():
    plan = heuristic_plan("最近大家怎麼看晨光咖啡？")
    assert plan.entity == "晨光咖啡"
    assert plan.keywords == ["晨光咖啡", "晨光"]
    assert heuristic_plan("雲豹手機最近在網路上的評價怎麼樣？").entity == "雲豹手機"


def test_llm_plan_parses_and_keeps_entity_as_keyword():
    llm = ScriptedLLM(
        ['```json\n{"entity": "晨光咖啡", "keywords": ["晨光"], "boards": ["Food"], "days": 30}\n```']
    )
    plan = llm_plan("晨光咖啡風評？", llm)
    assert plan.keywords == ["晨光咖啡", "晨光"]
    assert plan.boards == ["Food"] and plan.days == 30


def test_parse_json_tolerates_fences():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_agent_loop_end_to_end_rejects_bad_evidence_then_accepts(coffee):
    llm = PolicyLLM("晨光咖啡", bad_first_submit=True)
    plan = heuristic_plan(SCENARIOS["coffee"].example_question)
    report, _, _ = run_analysis(plan.question, coffee, mode="agent", llm=llm, plan_override=plan)

    tool_steps = [s.title for s in report.trace if s.kind == "tool"]
    assert sum(t.startswith("submit_findings") for t in tool_steps) == 2  # first bounced, second accepted
    assert len(report.findings) == len(report.spikes) == 4
    assert all(f.verified for f in report.findings)

    score = score_report(report, SCENARIOS["coffee"], {p.post_id: p for p in load_dataset(coffee.path)})
    summary = aggregate([score])
    assert summary["event_recall"] == 1.0
    assert summary["decoy_rejection"] == 1.0  # 晨光 = morning light was recognised as unrelated
    assert summary["event_precision"] == 1.0


def test_submit_findings_requires_evidence_to_be_read(coffee):
    from buzzscope.agent.tools import ToolBox
    from buzzscope.analysis.volume import daily_series, detect_spikes

    plan = heuristic_plan(SCENARIOS["coffee"].example_question)
    posts = coffee.fetch(plan)
    series = daily_series(posts, min(p.day for p in posts), max(p.day for p in posts))
    spikes = detect_spikes(series)
    box = ToolBox(posts, series, spikes, plan.entity, plan.keywords)
    some_id = posts[0].post_id
    findings = [
        {
            "spike_date": str(s.peak_date),
            "kind": "event",
            "cause": "x",
            "sentiment": "negative",
            "summary": "",
            "evidence_post_ids": [some_id],
            "confidence": 0.5,
        }
        for s in spikes
    ]
    result = box.submit_findings(findings, "s")
    assert result["accepted"] is False
    assert any("還沒用 read_posts 讀過" in e for e in result["errors"])


def test_tools_never_leak_ground_truth_labels(coffee):
    from buzzscope.agent.tools import ToolBox
    from buzzscope.analysis.volume import daily_series, detect_spikes

    plan = heuristic_plan(SCENARIOS["coffee"].example_question)
    posts = coffee.fetch(plan)
    series = daily_series(posts, min(p.day for p in posts), max(p.day for p in posts))
    box = ToolBox(posts, series, detect_spikes(series), plan.entity, plan.keywords)
    out = box.dispatch("read_posts", json.dumps({"post_ids": [p.post_id for p in posts[:5]]}))
    out += box.dispatch("search_posts", {"query": "冰塊"})
    assert "coffee_ice" not in out and "labels" not in out and "relevant" not in out


def test_unknown_tool_and_bad_args_return_errors_not_exceptions(coffee):
    from buzzscope.agent.tools import ToolBox

    box = ToolBox([], None, [], "x", ["x"])
    assert "未知的工具" in box.dispatch("rm_rf", "{}")
    assert "error" in box.dispatch("_between", "{}")
    assert "error" in box.dispatch("compare_terms", "{not json")
