"""Daily volume/sentiment series and robust spike detection."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from buzzscope.analysis.sentiment import post_sentiment
from buzzscope.models import Post, Spike


def daily_series(posts: list[Post], start: date, end: date) -> pd.DataFrame:
    """One row per day (zero-filled): post count, comment count, mean sentiment, share negative."""
    days = pd.date_range(start, end, freq="D").date
    rows = {d: {"count": 0, "comments": 0, "sent_sum": 0.0, "neg": 0} for d in days}
    for p in posts:
        if p.day in rows:
            s = post_sentiment(p)
            r = rows[p.day]
            r["count"] += 1
            r["comments"] += len(p.comments)
            r["sent_sum"] += s
            r["neg"] += s < -0.15
    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.name = "date"
    df["sentiment"] = (df["sent_sum"] / df["count"].replace(0, np.nan)).round(3)
    df["neg_share"] = (df["neg"] / df["count"].replace(0, np.nan)).round(3)
    return df.drop(columns=["sent_sum", "neg"])


def detect_spikes(
    series: pd.DataFrame,
    window: int = 14,
    z_threshold: float = 3.5,
    min_excess: int = 5,
) -> list[Spike]:
    """Flag days far above the trailing baseline, then merge consecutive days into one spike.

    Baseline = rolling *median* of the previous `window` days and the scale is the MAD,
    so a spike can't inflate its own baseline (a mean/std baseline would).
    """
    counts = series["count"].astype(float)
    trailing = counts.shift(1)
    median = trailing.rolling(window, min_periods=7).median()
    mad = trailing.rolling(window, min_periods=7).apply(
        lambda x: np.median(np.abs(x - np.median(x))), raw=True
    )
    sigma = np.maximum.reduce([1.4826 * mad.fillna(0), np.sqrt(median.fillna(0)), np.ones(len(counts))])
    z = (counts - median) / sigma
    flagged = (z >= z_threshold) & ((counts - median) >= min_excess)

    spikes: list[Spike] = []
    current: list[date] = []
    flagged_days = [d for d, f in zip(series.index, flagged, strict=True) if f]
    for d in flagged_days:
        if current and (d - current[-1]) > timedelta(days=1):
            spikes.append(_make_spike(current, counts, median, z))
            current = []
        current.append(d)
    if current:
        spikes.append(_make_spike(current, counts, median, z))
    return spikes


def _make_spike(days: list[date], counts: pd.Series, median: pd.Series, z: pd.Series) -> Spike:
    peak = max(days, key=lambda d: counts[d])
    return Spike(
        start=days[0],
        end=days[-1],
        peak_date=peak,
        peak_count=int(counts[peak]),
        baseline=round(float(median[days[0]]), 1),
        zscore=round(float(z[peak]), 1),
    )
