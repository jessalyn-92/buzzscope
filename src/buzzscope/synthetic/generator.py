"""Deterministic generator for the synthetic PTT-style datasets."""

from __future__ import annotations

import math
import random
from datetime import datetime, time, timedelta
from pathlib import Path

from buzzscope.models import Comment, Post
from buzzscope.synthetic.scenarios import (
    FILLERS,
    GENERIC_NEU_COMMENTS,
    N_DAYS,
    SCENARIOS,
    START_DATE,
    EventSpec,
    Scenario,
)


def _poisson(rng: random.Random, lam: float) -> int:
    threshold, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= threshold:
            return k
        k += 1


def _fmt(template: str, scenario: Scenario, rng: random.Random, name: str) -> str:
    return template.format(e=name, item=rng.choice(scenario.items), place=rng.choice(scenario.places))


def _timestamp(rng: random.Random, day_offset: int) -> datetime:
    day = START_DATE + timedelta(days=day_offset)
    return datetime.combine(day, time(rng.randint(7, 23), rng.randint(0, 59), rng.randint(0, 59)))


def _comments(rng: random.Random, pools: list[tuple[list[tuple[str, str]], float]], n: int, when: datetime):
    out = []
    for i in range(n):
        r, acc = rng.random(), 0.0
        pool = pools[-1][0]
        for candidate, weight in pools:
            acc += weight
            if r <= acc:
                pool = candidate
                break
        tag, text = rng.choice(pool)
        out.append(
            Comment(
                tag=tag,
                author=f"user{rng.randint(1, 5000):04d}",
                content=text,
                time=when + timedelta(minutes=5 * (i + 1)),
            )
        )
    return out


def _base_post(scenario: Scenario, rng: random.Random, day_offset: int) -> Post:
    mood = rng.choices(["pos", "neu", "neg"], weights=[0.4, 0.35, 0.25])[0]
    name = scenario.entity if rng.random() < 0.75 else scenario.short_name
    pool = {"pos": scenario.pos_sentences, "neu": scenario.neu_sentences, "neg": scenario.neg_sentences}[mood]
    sentences = [_fmt(s, scenario, rng, name) for s in rng.sample(pool, k=min(2, len(pool)))]
    extra = _fmt(rng.choice(scenario.neu_sentences), scenario, rng, name)
    if extra not in sentences:
        sentences.append(extra)
    sentences.append(rng.choice(FILLERS))
    if name not in "".join(sentences):
        sentences.insert(0, f"分享一下最近對{name}的感想。")
    when = _timestamp(rng, day_offset)
    weights = {
        "pos": [
            (scenario.pos_comments, 0.6),
            (scenario.neu_comments + GENERIC_NEU_COMMENTS, 0.25),
            (scenario.neg_comments, 0.15),
        ],
        "neu": [
            (scenario.pos_comments, 0.3),
            (scenario.neu_comments + GENERIC_NEU_COMMENTS, 0.45),
            (scenario.neg_comments, 0.25),
        ],
        "neg": [
            (scenario.pos_comments, 0.15),
            (scenario.neu_comments + GENERIC_NEU_COMMENTS, 0.25),
            (scenario.neg_comments, 0.6),
        ],
    }[mood]
    return Post(
        post_id="",
        board=rng.choice(scenario.boards),
        title=_fmt(rng.choice(scenario.base_titles), scenario, rng, name),
        author=f"user{rng.randint(1, 5000):04d}",
        published_at=when,
        content="\n".join(s for s in sentences if s),
        comments=_comments(rng, weights, rng.randint(0, 10), when),
        labels={"event": "", "relevant": "1"},
    )


def _event_post(scenario: Scenario, ev: EventSpec, rng: random.Random, day_offset: int) -> Post:
    name = scenario.entity if rng.random() < 0.8 else scenario.short_name
    sentences = [
        _fmt(s, scenario, rng, name)
        for s in rng.sample(ev.sentences, k=min(rng.randint(3, 4), len(ev.sentences)))
    ]
    when = _timestamp(rng, day_offset)
    pools = [(ev.comments, 0.85), (GENERIC_NEU_COMMENTS, 0.15)]
    return Post(
        post_id="",
        board=rng.choice(ev.boards),
        title=_fmt(rng.choice(ev.titles), scenario, rng, name),
        author=f"user{rng.randint(1, 5000):04d}",
        published_at=when,
        content="\n".join(sentences),
        comments=_comments(rng, pools, rng.randint(4, 14), when),
        labels={"event": ev.id, "relevant": "1" if ev.relevant else "0"},
    )


def generate(scenario: Scenario, seed: int = 7) -> list[Post]:
    rng = random.Random(f"{scenario.key}-{seed}")
    posts: list[Post] = []
    for d in range(N_DAYS):
        weekday = (START_DATE + timedelta(days=d)).weekday()
        lam = scenario.base_rate * (1.3 if weekday >= 5 else 1.0)
        posts.extend(_base_post(scenario, rng, d) for _ in range(_poisson(rng, lam)))
        for ev in scenario.events:
            k = d - ev.day
            if 0 <= k < len(ev.profile):
                n = max(0, round(ev.profile[k] * rng.uniform(0.85, 1.15)))
                posts.extend(_event_post(scenario, ev, rng, d) for _ in range(n))
    posts.sort(key=lambda p: p.published_at)
    for i, p in enumerate(posts):
        p.post_id = f"SYN.{scenario.key}.{i:05d}"
    return posts


def dataset_path(key: str, directory: Path) -> Path:
    return directory / f"{key}.jsonl"


def write_dataset(key: str, directory: Path, seed: int = 7) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = dataset_path(key, directory)
    with path.open("w", encoding="utf-8") as f:
        for post in generate(SCENARIOS[key], seed=seed):
            f.write(post.model_dump_json() + "\n")
    return path


def ensure_dataset(key: str, directory: Path) -> Path:
    path = dataset_path(key, directory)
    if not path.exists():
        write_dataset(key, directory)
    return path


def load_dataset(path: Path) -> list[Post]:
    with path.open(encoding="utf-8") as f:
        return [Post.model_validate_json(line) for line in f if line.strip()]
