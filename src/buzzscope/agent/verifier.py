"""Second-opinion check: does the cited evidence actually support each finding?

The verifier sees ONLY the finding and its evidence posts — not the agent's reasoning —
so it can't be talked into agreeing. Unsupported findings are kept but flagged.
"""

from __future__ import annotations

from buzzscope.agent.llm import LLMClient, parse_json
from buzzscope.models import Finding, Post

VERIFY_PROMPT = """你是嚴格的事實查核員。以下是一位分析師對「{entity}」某次聲量暴增的判斷，以及他引用的證據文章。
請只根據證據文章判斷這個結論是否成立，只輸出 JSON：{{"supported": true 或 false, "reason": "一句話理由"}}

判斷類型說明：event=與{entity}有關的具體事件；unrelated=關鍵字撞名，文章不是在講{entity}；noise=沒有共同事件。

分析師結論：
- 類型：{kind}
- 原因：{cause}
- 情緒：{sentiment}

證據文章：
{evidence}"""


def verify_findings(
    llm: LLMClient, entity: str, findings: list[Finding], posts_by_id: dict[str, Post]
) -> None:
    for f in findings:
        evidence = [posts_by_id[pid] for pid in f.evidence_post_ids if pid in posts_by_id]
        if not evidence:
            f.verified = f.kind == "noise"
            f.verification_note = "noise 類型不需要證據" if f.kind == "noise" else "沒有可查核的證據文章"
            continue
        text = "\n\n".join(
            f"[{p.post_id}] {p.title}\n{p.content[:300]}\n推文："
            + "；".join(f"{c.tag}{c.content}" for c in p.comments[:5])
            for p in evidence
        )
        reply = llm.chat(
            [
                {
                    "role": "user",
                    "content": VERIFY_PROMPT.format(
                        entity=entity, kind=f.kind, cause=f.cause, sentiment=f.sentiment, evidence=text
                    ),
                }
            ],
            json_mode=True,
        )
        try:
            data = parse_json(reply["content"])
            f.verified = bool(data.get("supported"))
            f.verification_note = str(data.get("reason", ""))
        except (ValueError, KeyError):
            f.verified = None
            f.verification_note = "查核回覆無法解析"
