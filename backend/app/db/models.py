"""Database schema for the Bhopal news archive.

Design notes grounded in measured provider behaviour:

* No provider offers deep backfill (NewsData archive is paid; GNews/NewsAPI
  cap at ~30 days). This table set IS the historical archive - anything not
  ingested is lost permanently.
* The same story arrives from up to three providers on the same day. A naive
  timeline would render that as three "developments". Articles are therefore
  grouped into `thread_beats`: one beat = one real development, carrying one
  or more articles as corroborating sources.
* Text per article is only ~300-500 chars (title + description + a truncated
  stub), so status inference is frequently `unknown` and must be stored as
  such rather than guessed.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import SCHEMA, Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Article(Base):
    """A single provider's rendering of a story."""

    __tablename__ = "articles"

    # sha256(title|url)[:16], matching the existing in-app article id.
    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    snippet: Mapped[str] = mapped_column(Text, default="", nullable=False)
    content_stub: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_key: Mapped[str] = mapped_column(Text, nullable=False)  # normalized, for dedupe

    source: Mapped[str] = mapped_column(Text, nullable=False)       # canonical
    source_raw: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[str | None] = mapped_column(Text)
    source_priority: Mapped[int | None] = mapped_column(Integer)
    author: Mapped[str | None] = mapped_column(Text)

    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="unknown", nullable=False)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    image_url: Mapped[str | None] = mapped_column(Text)

    sector: Mapped[str] = mapped_column(String(24), default="other", nullable=False)
    subtopic: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    progress_status: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)

    provider_category: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, nullable=False
    )
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    raw: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    keywords: Mapped[list["ArticleKeyword"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_articles_published_at", "published_at"),
        Index("ix_articles_sector", "sector"),
        Index("ix_articles_language", "language"),
        Index("ix_articles_provider", "provider"),
        Index("ix_articles_source", "source"),
        Index("ix_articles_status", "progress_status"),
        Index("ix_articles_url_key", "url_key"),
        {"schema": SCHEMA},
    )


class ArticleKeyword(Base):
    """Keywords attached to an article, from the provider or our extractor."""

    __tablename__ = "article_keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.articles.id", ondelete="CASCADE"), nullable=False
    )
    keyword: Mapped[str] = mapped_column(Text, nullable=False)
    # "provider" (NewsData supplied) or "heuristic" (extracted locally)
    origin: Mapped[str] = mapped_column(String(16), default="heuristic", nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    article: Mapped[Article] = relationship(back_populates="keywords")

    __table_args__ = (
        UniqueConstraint("article_id", "keyword", name="uq_article_keyword"),
        Index("ix_article_keywords_keyword", "keyword"),
        {"schema": SCHEMA},
    )


class StoryThread(Base):
    """A running story: 'Bhopal illegal construction' followed over weeks."""

    __tablename__ = "story_threads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    sector: Mapped[str] = mapped_column(String(24), default="other", nullable=False)
    location: Mapped[str] = mapped_column(Text, default="Bhopal", nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="unknown", nullable=False)

    # Keyword signature used for matching new articles into this thread.
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)

    current_status: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    beat_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    article_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    beats: Mapped[list["ThreadBeat"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", order_by="ThreadBeat.occurred_at"
    )

    __table_args__ = (
        Index("ix_story_threads_sector", "sector"),
        Index("ix_story_threads_last_seen", "last_seen"),
        Index("ix_story_threads_open", "is_open"),
        {"schema": SCHEMA},
    )


class ThreadBeat(Base):
    """One development in a thread.

    Multiple provider articles covering the same development on the same day
    collapse into a single beat, so the timeline reflects real progress rather
    than syndication volume.
    """

    __tablename__ = "thread_beats"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    thread_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.story_threads.id", ondelete="CASCADE"), nullable=False
    )

    headline: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    # True when this beat's status differs from the preceding beat.
    is_status_change: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(16))

    matched_keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    match_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    thread: Mapped[StoryThread] = relationship(back_populates="beats")
    articles: Mapped[list["BeatArticle"]] = relationship(
        back_populates="beat", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_thread_beats_thread", "thread_id"),
        Index("ix_thread_beats_occurred", "occurred_at"),
        {"schema": SCHEMA},
    )


class BeatArticle(Base):
    """Join: the provider articles corroborating one beat."""

    __tablename__ = "beat_articles"

    beat_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.thread_beats.id", ondelete="CASCADE"), primary_key=True
    )
    article_id: Mapped[str] = mapped_column(
        ForeignKey(f"{SCHEMA}.articles.id", ondelete="CASCADE"), primary_key=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    beat: Mapped[ThreadBeat] = relationship(back_populates="articles")
    article: Mapped[Article] = relationship()

    __table_args__ = ({"schema": SCHEMA},)


class TrackedEvent(Base):
    """A user following a thread. Replaces backend/data/events.json."""

    __tablename__ = "tracked_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    thread_id: Mapped[str | None] = mapped_column(
        ForeignKey(f"{SCHEMA}.story_threads.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    keyword_query: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sector: Mapped[str] = mapped_column(String(24), default="other", nullable=False)
    location: Mapped[str] = mapped_column(Text, default="Bhopal", nullable=False)
    progress_status: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    source_article_url: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    thread: Mapped[StoryThread | None] = relationship()

    __table_args__ = (
        Index("ix_tracked_events_thread", "thread_id"),
        {"schema": SCHEMA},
    )


class FetchLog(Base):
    """Per-provider outcome of each ingest call. Makes quota/rate-limit
    failures diagnosable instead of silently thinning results."""

    __tablename__ = "fetch_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    query: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    article_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    ran_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_fetch_log_ran_at", "ran_at"),
        Index("ix_fetch_log_provider", "provider"),
        {"schema": SCHEMA},
    )
