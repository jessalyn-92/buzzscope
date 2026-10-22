import itertools
from datetime import date, datetime, timedelta

from buzzscope.analysis.keyness import distinctive_terms
from buzzscope.analysis.sentiment import label, lexicon_counts, post_sentiment
from buzzscope.analysis.volume import daily_series, detect_spikes
from buzzscope.models import Comment, Post

_ids = itertools.count()


def _post(day: date, text: str = "普通的一天", comments=()) -> Post:
    return Post(
        post_id=f"P{next(_ids)}",
        board="Test",
        title=text,
        author="a",
        published_at=datetime.combine(day, datetime.min.time()),
        content=text,
        comments=[Comment(tag=t, author="b", content=c) for t, c in comments],
    )


def test_negation_flips_positive_words():
    assert lexicon_counts("真的不推薦") == (0, 1)
    assert lexicon_counts("不錯喝") == (1, 0)  # 不錯 is itself positive
    assert lexicon_counts("不划算") == (0, 1)  # counted once as negative, not also as 划算


def test_post_sentiment_uses_push_and_boo():
    happy = _post(date(2026, 1, 1), "店員很親切", [("推", "推"), ("推", "好喝")])
    angry = _post(date(2026, 1, 1), "今天去買咖啡", [("噓", "太貴"), ("噓", "爛")])
    assert label(post_sentiment(happy)) == "positive"
    assert label(post_sentiment(angry)) == "negative"


def test_detect_spikes_finds_planted_burst_and_merges_days():
    start = date(2026, 1, 1)
    posts = []
    for d in range(40):
        n = 5 + (d % 3)  # gentle wobble
        if d == 25:
            n += 30
        if d == 26:
            n += 15
        posts += [_post(start + timedelta(days=d)) for _ in range(n)]
    series = daily_series(posts, start, start + timedelta(days=39))
    spikes = detect_spikes(series)
    assert len(spikes) == 1
    s = spikes[0]
    assert s.peak_date == start + timedelta(days=25)
    assert s.start == start + timedelta(days=25) and s.end == start + timedelta(days=26)


def test_detect_spikes_ignores_flat_series():
    start = date(2026, 1, 1)
    posts = [_post(start + timedelta(days=d)) for d in range(30) for _ in range(6)]
    assert detect_spikes(daily_series(posts, start, start + timedelta(days=29))) == []


def test_distinctive_terms_prefers_full_word():
    day = date(2026, 1, 1)
    window = [
        _post(day, t)
        for t in [
            "冰塊驗出大腸桿菌",
            "大腸桿菌超標好可怕",
            "又是大腸桿菌",
            "聽說有大腸桿菌耶",
            "大腸桿菌問題要重視",
            "衛生局說大腸桿菌",
            "這次大腸桿菌事件",
            "怕大腸桿菌不敢喝",
        ]
    ]
    baseline = [_post(day, "今天的拿鐵很好喝") for _ in range(20)]
    terms = [t for t, _, _ in distinctive_terms(window, baseline, k=5)]
    assert any("大腸桿菌" in t for t in terms)
    assert not any(t in {"腸桿", "桿菌"} for t in terms)
