"""Core data models shared by scrapers, analysis, and the agent."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Sentiment = Literal["positive", "negative", "neutral", "mixed"]


class Comment(BaseModel):
    tag: str  # PTT push tag: 推 / 噓 / →
    author: str  # anonymized id
    content: str
    time: datetime | None = None


class Post(BaseModel):
    post_id: str
    board: str
    title: str
    author: str  # anonymized id
    published_at: datetime
    content: str
    url: str | None = None
    comments: list[Comment] = Field(default_factory=list)
    # Ground-truth labels. Only synthetic data has them; they are NEVER shown to the agent.
    labels: dict[str, str] = Field(default_factory=dict)

    @property
    def day(self) -> date:
        return self.published_at.date()

    @property
    def full_text(self) -> str:
        return "\n".join([self.title, self.content, *[c.content for c in self.comments]])


class ResearchPlan(BaseModel):
    """What to collect, decided by the planner from a natural-language question."""

    question: str
    entity: str
    keywords: list[str]
    exclude_keywords: list[str] = Field(default_factory=list)
    boards: list[str] = Field(default_factory=list)
    days: int = 90
    rationale: str = ""


class Spike(BaseModel):
    start: date
    end: date
    peak_date: date
    peak_count: int
    baseline: float
    zscore: float


FindingKind = Literal["event", "unrelated", "noise"]


class Finding(BaseModel):
    spike_date: date
    # event     = a real event about the entity
    # unrelated = keyword collision (e.g. 晨光 meaning "morning light", not the coffee brand)
    # noise     = no common cause, just normal fluctuation
    kind: FindingKind = "event"
    cause: str
    sentiment: Sentiment
    summary: str = ""
    evidence_post_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    verified: bool | None = None  # None = not checked
    verification_note: str = ""


class TraceStep(BaseModel):
    kind: str  # plan / fetch / tool / verify / info
    title: str
    detail: str = ""


class Usage(BaseModel):
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, other: Usage) -> None:
        self.llm_calls += other.llm_calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens


class Report(BaseModel):
    question: str
    mode: str
    plan: ResearchPlan
    n_posts: int
    start: date | None
    end: date | None
    spikes: list[Spike]
    findings: list[Finding]
    overall_summary: str
    trace: list[TraceStep] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
