"""Turn a natural-language question into a ResearchPlan (what to collect)."""

from __future__ import annotations

import re

from buzzscope.agent.llm import LLMClient, parse_json
from buzzscope.models import ResearchPlan

PLANNER_PROMPT = """你是網路輿情研究的資料規劃員。使用者會用一句話問某個品牌/產品/人物的網路討論狀況。
請規劃要去 PTT 收集哪些資料，只輸出一個 JSON 物件，格式：
{
  "entity": "分析對象的正式名稱",
  "keywords": ["3-6 個搜尋關鍵字，包含常見簡稱、英文名、網友慣用說法"],
  "exclude_keywords": ["只放『幾乎一定代表無關意思』的詞；不確定就留空，寧可多收再由分析判斷"],
  "boards": ["2-5 個最可能討論此對象的 PTT 看板英文名稱"],
  "days": 分析天數（整數，使用者沒指定就用 {default_days}）,
  "rationale": "一句話說明你的規劃理由"
}
注意：關鍵字越短越容易撞名（例如品牌簡稱可能也是一般詞彙），這沒關係，後續分析會處理撞名，但請在 rationale 提到撞名風險。"""

_FILLER = re.compile(
    r"(請|幫我|幫忙|分析|看看|一下|最近|近期|大家|網友|網路上|網路|在|對於|對|怎麼看|怎麼樣|怎樣|如何|"
    r"的|評價|風向|討論|輿情|聲量|口碑|狀況|情況|最新|是|什麼|嗎|呢|？|\?|！|!|。|，|,)"
)


def _is_cjk(ch: str) -> bool:
    return 0x4E00 <= ord(ch) <= 0x9FFF


def heuristic_plan(question: str, days: int = 90) -> ResearchPlan:
    """No-LLM fallback: strip question words, keep the entity, add a 2-char short form.

    The short form (晨光咖啡 → 晨光) mirrors how people actually write, and deliberately
    invites keyword collisions — catching those is the analyst's job.
    """
    entity = _FILLER.sub(" ", question).split()
    name = max(entity, key=len) if entity else question.strip()
    keywords = [name]
    if len(name) >= 4 and all(_is_cjk(ch) for ch in name):
        keywords.append(name[:2])
    return ResearchPlan(
        question=question,
        entity=name,
        keywords=keywords,
        days=days,
        rationale="未使用 LLM：從問題擷取名稱，並加入兩字簡稱以涵蓋網友常見寫法（可能撞名）。",
    )


def llm_plan(question: str, llm: LLMClient, days: int = 90) -> ResearchPlan:
    reply = llm.chat(
        [
            {"role": "system", "content": PLANNER_PROMPT.replace("{default_days}", str(days))},
            {"role": "user", "content": question},
        ],
        json_mode=True,
    )
    data = parse_json(reply["content"])
    keywords = [k.strip() for k in data.get("keywords", []) if k and k.strip()]
    entity = (data.get("entity") or "").strip() or heuristic_plan(question).entity
    if entity not in keywords:
        keywords.insert(0, entity)
    return ResearchPlan(
        question=question,
        entity=entity,
        keywords=keywords[:6],
        exclude_keywords=[k for k in data.get("exclude_keywords", []) if k][:6],
        boards=[b for b in data.get("boards", []) if b][:5],
        days=int(data.get("days") or days),
        rationale=data.get("rationale", ""),
    )
