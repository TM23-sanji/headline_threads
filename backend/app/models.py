from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Sector = Literal[
    "construction",
    "roads",
    "transport",
    "water_lakes",
    "bmc_civic",
    "health",
    "crime",
    "politics",
    "environment",
    "other",
]

ProgressStatus = Literal["planned", "ongoing", "delayed", "stalled", "completed", "unknown"]


Language = Literal["en", "hi", "unknown"]


class NewsArticle(BaseModel):
    id: str
    title: str
    snippet: str
    url: str
    source: str
    published_at: str | None = None
    image_url: str | None = None
    language: str | None = None
    provider: str | None = None

    # --- normalized (see services/normalize.py) ---
    source_raw: str | None = None
    published_at_iso: str | None = None

    # --- provider-supplied extras, free tier ---
    # NewsData returns entity-rich keywords and IPTC categories at no cost;
    # these feed keyword generation and act as a classifier cross-check.
    provider_keywords: list[str] = Field(default_factory=list)
    provider_category: list[str] = Field(default_factory=list)
    author: str | None = None
    source_id: str | None = None
    source_priority: int | None = None
    # Truncated body text (~200-265 chars) where the provider supplies it.
    content_stub: str | None = None
    is_duplicate: bool = False

    @property
    def text(self) -> str:
        """All usable text for this article (~300-500 chars in practice)."""
        return " ".join(part for part in (self.title, self.snippet, self.content_stub) if part)


class ClassifiedArticle(NewsArticle):
    sector: Sector = "other"
    subtopic: str | None = None
    status: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    keep: bool = False
    summary: str | None = None
    matched_keywords: list[str] = Field(default_factory=list)


class NewsResponse(BaseModel):
    query: str
    city: str
    sector: Sector | None
    total: int
    articles: list[ClassifiedArticle]
    providers: list[str] = Field(default_factory=list)


class NewspaperSection(BaseModel):
    sector: Sector
    label: str
    articles: list[ClassifiedArticle]


class NewspaperResponse(BaseModel):
    city: str
    date: str
    sections: list[NewspaperSection]
    total: int


class TimelineEntry(BaseModel):
    id: str
    captured_at: str
    article_id: str
    title: str
    snippet: str
    url: str
    source: str
    published_at: str | None = None
    inferred_status: ProgressStatus = "unknown"
    match_score: float = 0.0
    matched_keywords: list[str] = Field(default_factory=list)


class TrackedEvent(BaseModel):
    id: str
    title: str
    keywords: list[str]
    sector: Sector = "other"
    location: str = "Bhopal"
    progress_status: ProgressStatus = "unknown"
    created_at: str
    updated_at: str
    source_article_url: str | None = None
    timeline: list[TimelineEntry] = Field(default_factory=list)
    keyword_query: str = ""


class TrackEventRequest(BaseModel):
    title: str
    snippet: str = ""
    url: str | None = None
    sector: Sector | None = None
    location: str = "Bhopal"
    keywords: list[str] | None = None


class KeywordGenerateRequest(BaseModel):
    title: str
    snippet: str = ""


class KeywordGenerateResponse(BaseModel):
    keywords: list[str]
    keyword_query: str
    sector: Sector
    inferred_status: ProgressStatus


class EventsResponse(BaseModel):
    total: int
    events: list[TrackedEvent]


# --------------------------------------------------------------------------
# Faceted newspaper + story chains
# --------------------------------------------------------------------------


class FacetValue(BaseModel):
    value: str
    count: int


class PaperArticle(BaseModel):
    """An article as rendered in the paper, with its chips and chain link."""

    id: str
    title: str
    snippet: str
    url: str
    source: str
    provider: str
    language: str
    published_at: str | None = None
    image_url: str | None = None
    sector: Sector = "other"
    progress_status: ProgressStatus = "unknown"
    confidence: float = 0.0
    keywords: list[str] = Field(default_factory=list)
    thread_id: str | None = None
    thread_beat_count: int = 0


class PaperSection(BaseModel):
    sector: Sector
    label: str
    articles: list[PaperArticle]


class PaperResponse(BaseModel):
    city: str
    date: str
    total: int
    sections: list[PaperSection]
    facets: dict[str, list[FacetValue]] = Field(default_factory=dict)
    applied: dict = Field(default_factory=dict)


class BeatSource(BaseModel):
    id: str
    title: str
    url: str
    source: str
    provider: str
    language: str
    published_at: str | None = None


class Beat(BaseModel):
    """One development in a story chain."""

    id: str
    headline: str
    summary: str
    occurred_at: str
    status: ProgressStatus
    is_status_change: bool
    previous_status: ProgressStatus | None = None
    source_count: int
    sources: list[BeatSource] = Field(default_factory=list)


class Thread(BaseModel):
    id: str
    slug: str
    title: str
    sector: Sector
    language: str
    location: str
    current_status: ProgressStatus
    first_seen: str
    last_seen: str
    beat_count: int
    article_count: int
    keywords: list[str] = Field(default_factory=list)


class ThreadDetail(Thread):
    beats: list[Beat] = Field(default_factory=list)


class ThreadsResponse(BaseModel):
    total: int
    threads: list[Thread]
