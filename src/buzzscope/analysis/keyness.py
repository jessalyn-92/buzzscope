"""Which terms are unusually frequent in a time window vs. the baseline before it?

Chinese has no spaces, and we avoid a tokenizer dependency: we count character n-grams
(2–5 chars) by document frequency, score them with smoothed log-odds, then keep the
longest informative form (so 大腸桿菌 wins over 腸桿 / 桿菌).
"""

from __future__ import annotations

import math
import re
from collections import Counter

from buzzscope.models import Post

_CJK = "[\u4e00-\u9fff]"  # CJK Unified Ideographs
_RUN = re.compile(_CJK + r"+|[A-Za-z][A-Za-z0-9]+")
_CJK_RE = re.compile(_CJK)
GENERIC = {
    "大家",
    "覺得",
    "真的",
    "什麼",
    "可以",
    "就是",
    "因為",
    "所以",
    "還是",
    "已經",
    "今天",
    "最近",
    "一下",
    "怎麼",
    "這個",
    "那個",
    "自己",
    "沒有",
    "不是",
    "我們",
    "他們",
    "問題",
    "討論",
    "心得",
    "閒聊",
    "新聞",
    "情報",
    "一個",
    "現在",
    "知道",
    "比較",
    "感覺",
    "看到",
    "結果",
    "其他",
    "之後",
    "以上",
    "分享",
}


def _doc_grams(text: str, n_min: int = 2, n_max: int = 6) -> set[str]:
    grams: set[str] = set()
    for run in _RUN.findall(text):
        if run.isascii():
            grams.add(run)
            continue
        for n in range(n_min, n_max + 1):
            for i in range(len(run) - n + 1):
                grams.add(run[i : i + n])
    return grams


def _text(p: Post) -> str:
    return f"{p.title}\n{p.content}\n" + "\n".join(c.content for c in p.comments)


def _doc_freq(posts: list[Post]) -> Counter[str]:
    df: Counter[str] = Counter()
    for p in posts:
        df.update(_doc_grams(_text(p)))
    return df


def _is_fragment(term: str, texts: list[str], threshold: float = 0.8) -> bool:
    """A real word appears in varied contexts; a cut-off fragment (驗結果 from 抽驗結果) almost
    always has the same neighbour on one side. Check left/right neighbour variety."""
    left: Counter[str] = Counter()
    right: Counter[str] = Counter()
    total = 0
    for t in texts:
        start = 0
        while (i := t.find(term, start)) != -1:
            start = i + 1
            total += 1
            left[t[i - 1] if i > 0 else "^"] += 1
            j = i + len(term)
            right[t[j] if j < len(t) else "$"] += 1
    if total < 3:
        return False
    for side in (left, right):
        ch, n = side.most_common(1)[0]
        if n / total > threshold and _CJK_RE.fullmatch(ch):
            return True
    return False


def distinctive_terms(
    window: list[Post],
    baseline: list[Post],
    k: int = 10,
    exclude: list[str] | None = None,
    min_docs: int = 3,
) -> list[tuple[str, float, int]]:
    """Return [(term, score, docs_in_window)] sorted by distinctiveness."""
    if not window:
        return []
    exclude = [e for e in (exclude or []) if e]
    df_w, df_b = _doc_freq(window), _doc_freq(baseline)
    n_w, n_b = len(window), max(len(baseline), 1)

    scored = []
    for term, c_w in df_w.items():
        if c_w < min_docs or term in GENERIC:
            continue
        if any(term in e or e in term for e in exclude):
            continue
        c_b = df_b.get(term, 0)
        p_w = (c_w + 0.5) / (n_w + 1)
        p_b = (c_b + 0.5) / (n_b + 1)
        score = math.log(p_w / p_b) * math.sqrt(c_w / n_w)  # distinctive AND common in the window
        if score > 0:
            scored.append((term, score, c_w))
    scored.sort(key=lambda t: t[1], reverse=True)

    texts = [_text(p) for p in window]
    chosen: list[tuple[str, float, int]] = []
    for term, score, c_w in scored[: k * 30]:
        if not term.isascii() and _is_fragment(term, texts):
            continue
        if any(term in t for t, _, _ in chosen):
            continue  # a longer form is already chosen
        absorbed = [x for x in chosen if x[0] in term and c_w >= 0.8 * x[2]]
        if absorbed:  # prefer the longer, equally common form
            chosen = [x for x in chosen if x not in absorbed]
        chosen.append((term, round(score, 3), c_w))
        if len(chosen) >= k:
            break
    return chosen
