"""Command-line entry point: `buzzscope gen-data | analyze | eval`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from buzzscope.config import get_settings
from buzzscope.models import ResearchPlan, TraceStep


def _llm(settings):
    from buzzscope.agent.llm import OpenAIClient

    if not settings.has_llm:
        sys.exit("agent 模式需要 OPENAI_API_KEY（可寫在 .env）。沒有 key 請改用 --mode baseline。")
    return OpenAIClient(settings.openai_api_key, settings.openai_model)


def _print_step(step: TraceStep) -> None:
    icon = {"plan": "🧭", "fetch": "📥", "tool": "🔧", "think": "💭", "verify": "🔎", "info": "ℹ️"}.get(
        step.kind, "•"
    )
    print(f"{icon} {step.title}")


def cmd_gen_data(args) -> None:
    from buzzscope.synthetic.generator import write_dataset
    from buzzscope.synthetic.scenarios import SCENARIOS

    out = Path(args.out or get_settings().synthetic_dir)
    for key in SCENARIOS:
        print("wrote", write_dataset(key, out))


def _make_source(spec: str, settings):
    if spec.startswith("synthetic:"):
        from buzzscope.scraper.base import SyntheticSource

        return SyntheticSource(spec.split(":", 1)[1], settings.synthetic_dir)
    if spec == "ptt":
        from buzzscope.scraper.ptt import PTTSource

        return PTTSource(settings)
    sys.exit(f"未知的資料來源：{spec}（可用 synthetic:coffee / synthetic:tea / synthetic:phone / ptt）")


def cmd_analyze(args) -> None:
    from buzzscope.agent.planner import heuristic_plan
    from buzzscope.pipeline import run_analysis
    from buzzscope.report import to_markdown

    settings = get_settings()
    source = _make_source(args.source, settings)
    llm = _llm(settings) if args.mode == "agent" else None

    plan = None
    if args.keywords or args.boards:
        base = heuristic_plan(args.question, args.days)
        plan = ResearchPlan(
            question=args.question,
            entity=args.entity or base.entity,
            keywords=args.keywords.split(",") if args.keywords else base.keywords,
            exclude_keywords=args.exclude.split(",") if args.exclude else [],
            boards=args.boards.split(",") if args.boards else [],
            days=args.days,
            rationale="使用者手動指定",
        )
    if args.source == "ptt" and plan is None and llm is None:
        sys.exit("即時爬 PTT 時，baseline 模式請用 --boards 指定看板（agent 模式會自動規劃）。")

    report, _, _ = run_analysis(
        args.question,
        source,
        mode=args.mode,
        llm=llm,
        days=args.days,
        plan_override=plan,
        max_steps=settings.agent_max_steps,
        on_step=_print_step,
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{report.plan.entity}_{report.mode}"
    (out / f"{stem}.md").write_text(to_markdown(report), encoding="utf-8")
    (out / f"{stem}.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(f"\n報告已存到 {out / (stem + '.md')}")


def cmd_eval(args) -> None:
    from buzzscope.evaluation import score_report, to_dict, to_markdown
    from buzzscope.pipeline import run_analysis
    from buzzscope.scraper.base import SyntheticSource
    from buzzscope.synthetic.generator import load_dataset
    from buzzscope.synthetic.scenarios import SCENARIOS

    settings = get_settings()
    llm = _llm(settings) if args.mode == "agent" else None
    scores = []
    keys = args.scenarios.split(",") if args.scenarios else list(SCENARIOS)
    for key in keys:
        scenario = SCENARIOS[key]
        source = SyntheticSource(key, settings.synthetic_dir)
        print(f"\n=== {key}: {scenario.example_question}")
        report, _, _ = run_analysis(
            scenario.example_question,
            source,
            mode=args.mode,
            llm=llm,
            max_steps=settings.agent_max_steps,
            on_step=_print_step if args.verbose else None,
        )
        posts = {p.post_id: p for p in load_dataset(source.path)}
        scores.append(score_report(report, scenario, posts))
        for f in report.findings:
            print(f"  {f.spike_date} [{f.kind}] {f.cause}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model = settings.openai_model if args.mode == "agent" else None
    md = to_markdown(args.mode, scores, model)
    (out / f"{args.mode}.md").write_text(md, encoding="utf-8")
    (out / f"{args.mode}.json").write_text(
        json.dumps(to_dict(scores), ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    if llm is not None:
        u = llm.usage
        print(f"\nLLM 呼叫 {u.llm_calls} 次，輸入 {u.input_tokens:,} tokens，輸出 {u.output_tokens:,} tokens")
    print("\n" + md)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="buzzscope", description="BuzzScope 輿情雷達")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("gen-data", help="產生模擬資料集")
    p.add_argument("--out")
    p.set_defaults(func=cmd_gen_data)

    p = sub.add_parser("analyze", help="分析一個問題")
    p.add_argument("question")
    p.add_argument("--source", default="synthetic:coffee", help="synthetic:<coffee|tea|phone> 或 ptt")
    p.add_argument("--mode", choices=["agent", "baseline"], default="baseline")
    p.add_argument("--days", type=int, default=90)
    p.add_argument("--entity")
    p.add_argument("--keywords", help="逗號分隔，覆蓋自動規劃")
    p.add_argument("--exclude", help="逗號分隔的排除關鍵字")
    p.add_argument("--boards", help="逗號分隔的 PTT 看板，例如 Food,Drink")
    p.add_argument("--out", default="reports")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("eval", help="用模擬資料集評估分析品質")
    p.add_argument("--mode", choices=["agent", "baseline"], default="baseline")
    p.add_argument("--scenarios", help="逗號分隔，預設全部")
    p.add_argument("--out", default="eval/results")
    p.add_argument("-v", "--verbose", action="store_true")
    p.set_defaults(func=cmd_eval)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
