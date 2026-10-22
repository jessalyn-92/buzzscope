"""Data sources: anything that turns a ResearchPlan into a list of posts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from buzzscope.models import Post, ResearchPlan
from buzzscope.synthetic.generator import ensure_dataset, load_dataset
from buzzscope.synthetic.scenarios import END_DATE

ProgressFn = Callable[[str], None]


class Source(Protocol):
    name: str
    reference_now: datetime  # "today" for this source; the analysis window ends the day before

    def fetch(self, plan: ResearchPlan, on_progress: ProgressFn | None = None) -> list[Post]: ...


def matches_plan(post: Post, plan: ResearchPlan) -> bool:
    """Keyword match on title + body; exclude keywords veto. Comments are ignored on purpose:
    a passing mention in one comment shouldn't pull a whole thread in."""
    text = f"{post.title}\n{post.content}"
    if any(x and x in text for x in plan.exclude_keywords):
        return False
    return any(k and k in text for k in plan.keywords)


class SyntheticSource:
    """Offline source backed by a generated dataset (see synthetic/scenarios.py)."""

    def __init__(self, scenario_key: str, directory: Path):
        self.name = f"synthetic:{scenario_key}"
        self.path = ensure_dataset(scenario_key, directory)

    @property
    def reference_now(self) -> datetime:
        # The synthetic world "ends" on END_DATE; treat that as today.
        return datetime.combine(END_DATE + timedelta(days=1), datetime.min.time())

    def fetch(self, plan: ResearchPlan, on_progress: ProgressFn | None = None) -> list[Post]:
        posts = load_dataset(self.path)
        since = self.reference_now - timedelta(days=plan.days)
        kept = [p for p in posts if p.published_at >= since and matches_plan(p, plan)]
        if on_progress:
            on_progress(f"從模擬資料集載入 {len(posts)} 篇，符合關鍵字 {len(kept)} 篇")
        return kept
