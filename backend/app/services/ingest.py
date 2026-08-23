"""Ingest pipeline: providers -> normalize -> classify -> keyword -> Neon.

This is the only place history is created. The providers offer no meaningful
backfill (NewsData's archive is paid; GNews and NewsAPI cap at ~30 days), so
anything not ingested is permanently unavailable. The pipeline is idempotent:
re-running it re-scores existing rows without duplicating them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Article,
    ArticleKeyword,
    BeatArticle,
    FetchLog,
    StoryThread,
    ThreadBeat,
)
from app.models import NewsArticle
from app.services.classifier import classify_article
from app.services.keywords import generate_keywords, infer_progress_status
from app.services.news_fetchers import MP_QUERY, PROVIDER_STATUS, fetch_all_articles
from app.services.normalize import parse_published_at, url_key
from app.services.threading import (
    BeatCandidate,
    ThreadCandidate,
    find_duplicate_beat,
    keyword_set,
    make_id,
    match_thread,
    resolve_thread_status,
    slugify,
)

logger = logging.getLogger(__name__)

# Threads older than this are not considered for new matches.
THREAD_LOOKBACK = timedelta(days=45)


@dataclass
class IngestResult:
    fetched: int = 0
    new_articles: int = 0
    updated_articles: int = 0
    new_threads: int = 0
    new_beats: int = 0
    merged_beats: int = 0
    providers: dict[str, dict] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "fetched": self.fetched,
            "new_articles": self.new_articles,
            "updated_articles": self.updated_articles,
            "new_threads": self.new_threads,
            "new_beats": self.new_beats,
            "merged_beats": self.merged_beats,
            "providers": self.providers,
            "errors": self.errors,
        }


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _upsert_article(
    session: AsyncSession, art: NewsArticle, keywords: list[str]
) -> tuple[bool, Article]:
    """Insert or refresh one article. Returns (created, row)."""
    classified = classify_article(art)
    status = infer_progress_status(art.text)
    published = parse_published_at(art.published_at) or utcnow()

    values = {
        "id": art.id,
        "title": art.title,
        "snippet": art.snippet or "",
        "content_stub": art.content_stub,
        "url": art.url,
        "url_key": url_key(art.url),
        "source": art.source,
        "source_raw": art.source_raw,
        "source_id": art.source_id,
        "source_priority": art.source_priority,
        "author": art.author,
        "provider": art.provider or "unknown",
        "language": art.language or "unknown",
        "published_at": published,
        "image_url": art.image_url,
        "sector": classified.sector,
        "subtopic": classified.subtopic,
        "confidence": classified.confidence,
        "progress_status": status,
        "provider_category": art.provider_category or [],
        "is_duplicate": art.is_duplicate,
        "raw": {"provider_keywords": art.provider_keywords},
    }

    existing = await session.get(Article, art.id)
    created = existing is None

    stmt = (
        pg_insert(Article)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[Article.id],
            # ingested_at is preserved: it records when we first saw the story.
            set_={
                k: v for k, v in values.items() if k not in {"id", "ingested_at"}
            },
        )
        .returning(Article)
    )
    row = (await session.execute(stmt)).scalar_one()

    for kw in keywords:
        await session.execute(
            pg_insert(ArticleKeyword)
            .values(
                article_id=art.id,
                keyword=kw,
                origin="provider" if kw in (art.provider_keywords or []) else "heuristic",
                weight=1.0,
            )
            .on_conflict_do_nothing(constraint="uq_article_keyword")
        )

    return created, row


async def _load_thread_candidates(
    session: AsyncSession, since: datetime
) -> dict[str, ThreadCandidate]:
    rows = (
        await session.execute(
            select(StoryThread).where(
                StoryThread.is_open.is_(True), StoryThread.last_seen >= since
            )
        )
    ).scalars().all()

    return {
        t.id: ThreadCandidate(
            id=t.id,
            title=t.title,
            sector=t.sector,
            keywords=list(t.keywords or []),
            last_seen=t.last_seen,
        )
        for t in rows
    }


async def _load_beats(session: AsyncSession, thread_id: str) -> list[BeatCandidate]:
    rows = (
        await session.execute(
            select(ThreadBeat).where(ThreadBeat.thread_id == thread_id)
        )
    ).scalars().all()

    return [
        BeatCandidate(
            id=b.id,
            headline=b.headline,
            occurred_at=b.occurred_at,
            keywords=list(b.matched_keywords or []),
        )
        for b in rows
    ]


async def ingest(
    session: AsyncSession,
    query: str = MP_QUERY,
    articles: list[NewsArticle] | None = None,
) -> IngestResult:
    """Run one ingest cycle.

    `articles` may be supplied to replay fixtures without spending API quota.
    """
    result = IngestResult()

    if articles is None:
        articles = await fetch_all_articles(query)
        for name, status in PROVIDER_STATUS.items():
            result.providers[name] = dict(status)
            session.add(
                FetchLog(
                    provider=name,
                    query=query,
                    ok=bool(status.get("ok")),
                    article_count=int(status.get("count") or 0),
                    error=status.get("error"),
                )
            )
            if not status.get("ok"):
                result.errors.append(f"{name}: {status.get('error')}")

    result.fetched = len(articles)
    if not articles:
        await session.commit()
        return result

    # Oldest first so threads accumulate beats in chronological order.
    articles = sorted(articles, key=lambda a: a.published_at or "")

    candidates = await _load_thread_candidates(session, utcnow() - THREAD_LOOKBACK)

    for art in articles:
        keywords, sector, status = generate_keywords(
            art.title, art.snippet, art.provider_keywords
        )
        created, _ = await _upsert_article(session, art, keywords)
        if created:
            result.new_articles += 1
        else:
            result.updated_articles += 1

        published = parse_published_at(art.published_at) or utcnow()

        match = match_thread(
            title=art.title,
            keywords=keywords,
            sector=sector,
            published_at=published,
            candidates=list(candidates.values()),
        )

        if match.is_new_thread:
            thread_id = make_id(art.title, art.url)
            session.add(
                StoryThread(
                    id=thread_id,
                    slug=slugify(art.title),
                    title=art.title,
                    sector=sector,
                    language=art.language or "unknown",
                    keywords=keywords,
                    current_status=status,
                    first_seen=published,
                    last_seen=published,
                    beat_count=0,
                    article_count=0,
                )
            )
            await session.flush()
            candidates[thread_id] = ThreadCandidate(
                id=thread_id,
                title=art.title,
                sector=sector,
                keywords=keywords,
                last_seen=published,
            )
            result.new_threads += 1
        else:
            thread_id = match.thread_id
            cand = candidates[thread_id]
            cand.last_seen = max(cand.last_seen, published)
            merged = list(dict.fromkeys([*cand.keywords, *keywords]))[:12]
            cand.keywords = merged
            cand.keyword_index = keyword_set(merged)

        # Collapse same-day syndication into one beat.
        existing_beats = await _load_beats(session, thread_id)
        dup = find_duplicate_beat(
            title=art.title,
            keywords=keywords,
            published_at=published,
            beats=existing_beats,
        )

        if dup is None:
            prev_status = (
                sorted(existing_beats, key=lambda b: b.occurred_at)[-1]
                if existing_beats
                else None
            )
            previous = None
            if prev_status is not None:
                prev_row = await session.get(ThreadBeat, prev_status.id)
                previous = prev_row.status if prev_row else None

            beat_id = make_id(thread_id, art.title, str(published))
            session.add(
                ThreadBeat(
                    id=beat_id,
                    thread_id=thread_id,
                    headline=art.title,
                    summary=(art.snippet or "")[:400],
                    occurred_at=published,
                    status=status,
                    is_status_change=bool(previous and previous != status),
                    previous_status=previous,
                    matched_keywords=keywords,
                    match_score=match.score,
                    source_count=1,
                )
            )
            await session.flush()
            result.new_beats += 1
        else:
            beat_id = dup.id
            beat_row = await session.get(ThreadBeat, beat_id)
            if beat_row is not None:
                beat_row.source_count += 1
            result.merged_beats += 1

        await session.execute(
            pg_insert(BeatArticle)
            .values(beat_id=beat_id, article_id=art.id, is_primary=dup is None)
            .on_conflict_do_nothing()
        )

    await session.flush()
    await _refresh_thread_rollups(session, list(candidates.keys()))
    await session.commit()
    return result


async def _refresh_thread_rollups(session: AsyncSession, thread_ids: list[str]) -> None:
    """Recompute counts and current status for the touched threads."""
    for thread_id in thread_ids:
        thread = await session.get(StoryThread, thread_id)
        if thread is None:
            continue

        beats = (
            await session.execute(
                select(ThreadBeat)
                .where(ThreadBeat.thread_id == thread_id)
                .order_by(ThreadBeat.occurred_at)
            )
        ).scalars().all()

        if not beats:
            continue

        article_count = (
            await session.execute(
                select(BeatArticle).join(
                    ThreadBeat, ThreadBeat.id == BeatArticle.beat_id
                ).where(ThreadBeat.thread_id == thread_id)
            )
        ).scalars().all()

        thread.beat_count = len(beats)
        thread.article_count = len(article_count)
        thread.first_seen = beats[0].occurred_at
        thread.last_seen = beats[-1].occurred_at
        thread.current_status = resolve_thread_status([b.status for b in beats])
        thread.updated_at = utcnow()
