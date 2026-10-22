"""BuzzScope dashboard. Run with: streamlit run src/buzzscope/app/streamlit_app.py"""

from __future__ import annotations

import os

import streamlit as st

from buzzscope.agent.llm import OpenAIClient
from buzzscope.agent.planner import heuristic_plan
from buzzscope.app.charts import sentiment_chart, volume_chart
from buzzscope.config import get_settings
from buzzscope.models import ResearchPlan, TraceStep
from buzzscope.pipeline import run_analysis
from buzzscope.report import KIND_LABEL, SENT_LABEL, to_markdown, verification_badge
from buzzscope.scraper.base import SyntheticSource
from buzzscope.scraper.ptt import PTTSource
from buzzscope.synthetic.scenarios import SCENARIOS

st.set_page_config(page_title="BuzzScope 輿情雷達", page_icon="📡", layout="wide")
settings = get_settings()

STEP_ICON = {"plan": "🧭", "fetch": "📥", "tool": "🔧", "think": "💭", "verify": "🔎", "info": "📊"}
SENT_EMOJI = {"positive": "🟢", "negative": "🔴", "neutral": "⚪", "mixed": "🟡"}

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("設定")
    source_kind = st.radio(
        "資料來源",
        ["模擬資料（虛構品牌）", "即時爬取 PTT"],
        help="模擬資料是虛構品牌，內含埋好的事件，可驗證分析是否正確。",
    )
    scenario_key = None
    if source_kind.startswith("模擬"):
        scenario_key = st.selectbox(
            "情境",
            list(SCENARIOS),
            format_func=lambda k: f"{SCENARIOS[k].entity}（{k}）",
        )

    api_key = settings.openai_api_key or st.text_input(
        "OpenAI API key", type="password", help="只存在這次瀏覽的記憶體中，不會寫入任何檔案。"
    )
    analyst = st.radio(
        "分析方式",
        ["AI Agent", "離線 baseline（免 API key）"],
        index=0 if api_key else 1,
        help="Agent 會自己閱讀文章判斷原因、撞名與情緒；baseline 只列出特徵詞。",
    )
    mode = "agent" if analyst == "AI Agent" else "baseline"
    days = st.slider("分析天數", 14, 180, 90, step=1)

    with st.expander("進階：手動指定關鍵字／看板"):
        manual_keywords = st.text_input("關鍵字（逗號分隔）", placeholder="留空則自動規劃")
        manual_exclude = st.text_input("排除關鍵字（逗號分隔）")
        manual_boards = st.text_input("PTT 看板（逗號分隔）", placeholder="例如 Food,Drink")

    st.caption(f"模型：`{settings.openai_model}`（可用環境變數 OPENAI_MODEL 修改）")

# ---------------------------------------------------------------- header
st.title("📡 BuzzScope 輿情雷達")
st.markdown(
    "用一句話提問，Agent 會**自己規劃要收集什麼、找出聲量異常、閱讀文章判斷原因**，並附上可查證的原文。"
)

default_q = SCENARIOS[scenario_key].example_question if scenario_key else "最近大家怎麼看 iPhone？"
question = st.text_input("你想知道什麼？", value=default_q)
run = st.button("開始分析", type="primary")


def build_plan() -> ResearchPlan | None:
    if not (manual_keywords or manual_boards):
        return None
    base = heuristic_plan(question, days)
    return ResearchPlan(
        question=question,
        entity=base.entity,
        keywords=[k.strip() for k in manual_keywords.split(",") if k.strip()] or base.keywords,
        exclude_keywords=[k.strip() for k in manual_exclude.split(",") if k.strip()],
        boards=[b.strip() for b in manual_boards.split(",") if b.strip()],
        days=days,
        rationale="使用者手動指定",
    )


if run:
    if mode == "agent" and not api_key:
        st.error("AI Agent 模式需要 OpenAI API key，或改用離線 baseline。")
        st.stop()
    plan = build_plan()
    if source_kind.startswith("即時") and mode == "baseline" and not (plan and plan.boards):
        st.error("離線 baseline 不會自動規劃看板，請在「進階」填入 PTT 看板。")
        st.stop()

    if source_kind.startswith("即時"):
        source = PTTSource(settings)
    else:
        source = SyntheticSource(scenario_key, settings.synthetic_dir)
    llm = OpenAIClient(api_key, os.getenv("OPENAI_MODEL", settings.openai_model)) if mode == "agent" else None

    with st.status("分析中…", expanded=True) as status:

        def on_step(step: TraceStep) -> None:
            status.write(f"{STEP_ICON.get(step.kind, '•')} {step.title}")

        try:
            report, series, posts = run_analysis(
                question,
                source,
                mode=mode,
                llm=llm,
                days=days,
                plan_override=plan,
                max_steps=settings.agent_max_steps,
                on_step=on_step,
            )
        except Exception as exc:  # show the error in the UI instead of a stack trace
            status.update(label="分析失敗", state="error")
            st.exception(exc)
            st.stop()
        status.update(
            label=f"完成：{report.n_posts} 篇文章、{len(report.spikes)} 次聲量異常",
            state="complete",
            expanded=False,
        )
    st.session_state["result"] = (report, series, {p.post_id: p for p in posts})

# ---------------------------------------------------------------- results
if "result" in st.session_state:
    report, series, posts_by_id = st.session_state["result"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("相關文章", f"{report.n_posts:,}")
    c2.metric("聲量異常", len(report.spikes))
    c3.metric("判定為事件", sum(f.kind == "event" for f in report.findings))
    c4.metric("LLM 呼叫", report.usage.llm_calls if report.usage.llm_calls else "—")

    st.subheader("總結")
    st.info(report.overall_summary)

    st.plotly_chart(volume_chart(series, report), width="stretch")
    st.plotly_chart(sentiment_chart(series), width="stretch")

    st.subheader("聲量異常與原因")
    if not report.findings:
        st.write("此期間沒有偵測到明顯的聲量異常。")
    for f in report.findings:
        with st.container(border=True):
            st.markdown(
                f"**{f.spike_date}**　`{KIND_LABEL[f.kind]}`　{SENT_EMOJI[f.sentiment]} {SENT_LABEL[f.sentiment]}"
                f"　信心 {f.confidence:.0%}　{verification_badge(f.verified)}"
            )
            st.markdown(f"#### {f.cause}")
            if f.summary:
                st.write(f.summary)
            if f.verification_note:
                st.caption(f"查核：{f.verification_note}")
            if f.evidence_post_ids:
                with st.expander(f"證據文章（{len(f.evidence_post_ids)}）"):
                    for pid in f.evidence_post_ids:
                        p = posts_by_id.get(pid)
                        if p is None:
                            continue
                        head = f"[{p.title}]({p.url})" if p.url else p.title
                        st.markdown(
                            f"**{head}**　<small>{p.board}・{p.day}・{len(p.comments)} 則推文</small>",
                            unsafe_allow_html=True,
                        )
                        st.caption(p.content[:180].replace("\n", " ") + "…")

    with st.expander("Agent 執行過程"):
        for step in report.trace:
            st.markdown(f"{STEP_ICON.get(step.kind, '•')} **{step.title}**")
            if step.detail:
                st.caption(step.detail[:400])

    st.download_button(
        "下載報告（Markdown）",
        to_markdown(report, {k: v.url for k, v in posts_by_id.items() if v.url}),
        file_name=f"buzzscope_{report.plan.entity}.md",
        mime="text/markdown",
    )
