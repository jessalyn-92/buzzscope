"""Cheap, transparent sentiment baseline: a small lexicon + PTT push/boo tags.

Used for the trend charts in every mode (it costs nothing and is consistent across runs).
The agent does NOT trust it blindly; it reads posts to judge each spike's sentiment itself.
"""

from __future__ import annotations

from buzzscope.models import Post

POSITIVE = [
    "好喝",
    "好吃",
    "推薦",
    "喜歡",
    "可愛",
    "划算",
    "CP值",
    "親切",
    "乾淨",
    "滿意",
    "值得",
    "誠意",
    "讚",
    "不錯",
    "順口",
    "佛心",
    "成功",
    "Q彈",
    "貼心",
    "方便",
    "很棒",
    "好美",
    "期待",
    "回購",
    "很香",
    "很快",
    "超乎預期",
    "加油",
    "有誠意",
    "處理得不錯",
]
NEGATIVE = [
    "太貴",
    "偏貴",
    "難喝",
    "噁心",
    "失望",
    "很差",
    "爛",
    "很慢",
    "誇張",
    "傻眼",
    "可怕",
    "太扯",
    "不敢",
    "退坑",
    "當機",
    "異常",
    "過期",
    "超標",
    "漲價",
    "喝不起",
    "雜訊",
    "卡頓",
    "冷淡",
    "很衰",
    "硬傷",
    "不穩",
    "白跑",
    "太淡",
    "太酸",
    "不舒服",
    "不划算",
    "不合格",
    "災情",
    "綠線",
    "爆料",
    "暫停營業",
    "等超久",
    "品控",
    "又漲",
    "掰掰",
    "生氣",
    "抵制",
]
NEGATORS = ("不", "沒", "別")


def lexicon_counts(text: str) -> tuple[int, int]:
    """Count (positive, negative) hits. Negative phrases claim their span first, so 不划算
    counts once as negative instead of also as 划算; 不/沒 before a positive word flips it."""
    neg, taken = 0, set()
    for word in NEGATIVE:
        start = 0
        while (i := text.find(word, start)) != -1:
            start = i + len(word)
            neg += 1
            taken.update(range(i, i + len(word)))
    pos = 0
    for word in POSITIVE:
        start = 0
        while (i := text.find(word, start)) != -1:
            start = i + len(word)
            if taken.intersection(range(i, i + len(word))):
                continue
            if i > 0 and text[i - 1] in NEGATORS and not word.startswith("不"):
                neg += 1
            else:
                pos += 1
    return pos, neg


def post_sentiment(post: Post) -> float:
    """Score in [-1, 1]. Half from the author's text, half from how commenters reacted."""
    p, n = lexicon_counts(f"{post.title}\n{post.content}")
    body = (p - n) / (p + n) if p + n else 0.0
    pushes = sum(c.tag == "推" for c in post.comments)
    boos = sum(c.tag == "噓" for c in post.comments)
    cp, cn = lexicon_counts("\n".join(c.content for c in post.comments))
    reaction_pos, reaction_neg = pushes + cp, boos + cn
    if reaction_pos + reaction_neg == 0:
        return body
    reaction = (reaction_pos - reaction_neg) / (reaction_pos + reaction_neg)
    return 0.5 * body + 0.5 * reaction


def label(score: float, threshold: float = 0.15) -> str:
    if score > threshold:
        return "positive"
    if score < -threshold:
        return "negative"
    return "neutral"
