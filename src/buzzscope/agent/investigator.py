"""The investigator agent: an LLM in a tool-calling loop that explains each volume spike."""

from __future__ import annotations

import json
from collections.abc import Callable

import pandas as pd

from buzzscope.agent.llm import LLMClient
from buzzscope.agent.tools import TOOL_SPECS, ToolBox
from buzzscope.models import Finding, Post, ResearchPlan, Spike, TraceStep

SYSTEM_PROMPT = """你是資深的網路輿情分析師，負責解釋「{entity}」在 PTT 上的聲量變化，讀者是品牌的公關/行銷主管。

工作流程：
1. 呼叫 get_overview 了解資料，再呼叫 detect_spikes 找出聲量異常。
2. 對每一個 spike：
   a. 用 compare_terms 看該期間的特徵詞（這只是線索）。
   b. 用 search_posts 找該期間討論最多的文章，再用 read_posts 實際閱讀（每個 spike 至少讀 2 篇）。
   c. 判斷類型：
      - event：與「{entity}」本身有關的具體事件（新聞、活動、新品、客訴、爭議…）
      - unrelated：關鍵字撞名，文章其實不是在講「{entity}」（例如同字的地名、自然現象、動物）
      - noise：讀完找不到共同事件，只是正常波動
3. 全部 spike 都判斷完後，呼叫 submit_findings。

規則：
- 只根據你讀過的文章下結論，不要編造資料中沒有的資訊。
- cause 要具體描述發生什麼事，不要只列關鍵詞。
- evidence_post_ids 只能放你用 read_posts 讀過、且支持結論的文章，每個 spike 2–4 篇。
- sentiment 依文章內容與推/噓判斷；字典情緒分數只是參考，可能出錯。
- 全部用繁體中文。工具呼叫要有效率，可以一次呼叫多個工具。"""


def _short(result: str, n: int = 160) -> str:
    return result if len(result) <= n else result[:n] + "…"


def investigate(
    llm: LLMClient,
    plan: ResearchPlan,
    posts: list[Post],
    series: pd.DataFrame,
    spikes: list[Spike],
    max_steps: int = 24,
    on_step: Callable[[TraceStep], None] | None = None,
) -> tuple[list[Finding], str, list[TraceStep]]:
    box = ToolBox(posts, series, spikes, plan.entity, plan.keywords)
    trace: list[TraceStep] = []

    def log(kind: str, title: str, detail: str = "") -> None:
        step = TraceStep(kind=kind, title=title, detail=detail)
        trace.append(step)
        if on_step:
            on_step(step)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(entity=plan.entity)},
        {
            "role": "user",
            "content": f"使用者的問題：{plan.question}\n收集關鍵字：{'、'.join(plan.keywords)}\n"
            f"資料期間：最近 {plan.days} 天，共 {len(posts)} 篇文章。請開始分析。",
        },
    ]
    nudged = False
    for step in range(max_steps):
        force_submit = step == max_steps - 1
        reply = llm.chat(
            messages,
            tools=TOOL_SPECS,
            tool_choice={"type": "function", "function": {"name": "submit_findings"}}
            if force_submit
            else None,
        )
        messages.append(reply)
        calls = reply.get("tool_calls") or []
        if reply.get("content"):
            log("think", "Agent 想法", reply["content"])
        if not calls:
            if nudged:
                break
            nudged = True
            messages.append({"role": "user", "content": "請用工具完成分析，最後呼叫 submit_findings 提交。"})
            continue

        for call in calls:
            name, args = call["function"]["name"], call["function"]["arguments"]
            result = box.dispatch(name, args)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
            log("tool", f"{name}({_fmt_args(args)})", _short(result))

        if box.submitted is not None:
            break

    if box.submitted is None:
        log("info", "Agent 未在步數上限內提交結果")
        return [], "Agent 未在步數上限內完成分析，請提高 AGENT_MAX_STEPS 或縮短分析期間。", trace
    findings, summary = box.submitted
    for f in findings:
        f.evidence_post_ids = [pid for pid in f.evidence_post_ids if pid in box.by_id]
    return findings, summary, trace


def _fmt_args(args: str) -> str:
    try:
        data = json.loads(args) if isinstance(args, str) else args
    except json.JSONDecodeError:
        return "…"
    if "findings" in data:
        return f"{len(data['findings'])} findings"
    return ", ".join(f"{k}={v}" for k, v in data.items())[:80]
