"""Tracked-event storage, backed by Postgres.

A tracked event is now a thin "user follows story thread X" record - the
timeline is the thread's beats, so tracking gains full history and syndication
collapse for free. The old JSON-file implementation is retired: it wrote to an
ephemeral filesystem (data/events.json is gitignored and lost on every
container redeploy), and every refresh burned three provider API calls.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Article,
    BeatArticle,
    StoryThread,
    ThreadBeat,
    TrackedEvent as TrackedEventRow,
)
from app.models import TimelineEntry, TrackEventRequest, TrackedEvent
from app.services.keywords import build_keyword_query, prepare_track_request
from app.services.threading import (
    ThreadCandidate,
    keyword_set,
    make_id,
    match_thread,
    slugify,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""


async def _timeline_for_thread(session: AsyncSession, thread_id: str) -> list[TimelineEntry]:
    """Build a TimelineEntry list from a thread's beats + their articles."""
    beats = list(
        (
            await session.execute(
                select(ThreadBeat)
                .where(ThreadBeat.thread_id == thread_id)
                .order_by(ThreadBeat.occurred_at.desc())
            )
        )
        .scalars()
        .all()
    )
    if not beats:
        return []

    rows = (
        await session.execute(
            select(BeatArticle.beat_id, Article)
            .join(Article, Article.id == BeatArticle.article_id)
            .where(BeatArticle.beat_id.in_([b.id for b in beats]))
        )
    ).all()

    primary: dict[str, Article] = {}
    for beat_id, article in rows:
        # Newest article per beat wins as the representative row.
        existing = primary.get(beat_id)
        if existing is None or (
            article.published_at
            and existing.published_at
            and article.published_at > existing.published_at
        ):
            primary[beat_id] = article

    timeline: list[TimelineEntry] = []
    for beat in beats:
        article = primary.get(beat.id)
        if article is None:
            continue
        timeline.append(
            TimelineEntry(
                id=beat.id,
                captured_at=_iso(beat.created_at),
                article_id=article.id,
                title=beat.headline,
                snippet=beat.summary or article.snippet,
                url=article.url,
                source=article.source,
                published_at=_iso(article.published_at),
                inferred_status=beat.status,
                match_score=beat.match_score,
                matched_keywords=list(beat.matched_keywords or []),
            )
        )
    return timeline


async def _row_to_model(session: AsyncSession, row: TrackedEventRow) -> TrackedEvent:
    timeline = await _timeline_for_thread(session, row.thread_id) if row.thread_id else []
    return TrackedEvent(
        id=row.id,
        title=row.title,
        keywords=list(row.keywords or []),
        sector=row.sector,
        location=row.location,
        progress_status=row.progress_status,
        created_at=_iso(row.created_at),
        updated_at=_iso(row.updated_at),
        source_article_url=row.source_article_url,
        timeline=timeline,
        keyword_query=row.keyword_query,
    )


async def list_events(session: AsyncSession) -> list[TrackedEvent]:
    rows = (
        await session.execute(
            select(TrackedEventRow)
            .options(selectinload(TrackedEventRow.thread))
            .order_by(TrackedEventRow.created_at.desc())
        )
    ).scalars().all()
    return [await _row_to_model(session, r) for r in rows]


async def get_event(session: AsyncSession, event_id: str) -> TrackedEvent | None:
    row = await session.get(TrackedEventRow, event_id)
    if row is None:
        return None
    return await _row_to_model(session, row)


async def _attach_thread(
    session: AsyncSession,
    *,
    title: str,
    keywords: list[str],
    sector: str,
    location: str,
) -> str:
    """Attach the event to an existing thread, or create a fresh one."""
    from datetime import timedelta

    lookback = _utcnow() - timedelta(days=45)
    open_threads = list(
        (
            await session.execute(
                select(StoryThread).where(
                    StoryThread.is_open.is_(True), StoryThread.last_seen >= lookback
                )
            )
        )
        .scalars()
        .all()
    )

    candidates = [
        ThreadCandidate(
            id=t.id,
            title=t.title,
            sector=t.sector,
            keywords=list(t.keywords or []),
            last_seen=t.last_seen,
        )
        for t in open_threads
    ]

    match = match_thread(
        title=title,
        keywords=keywords,
        sector=sector,
        published_at=_utcnow(),
        candidates=candidates,
    )
    if not match.is_new_thread and match.thread_id:
        return match.thread_id

    thread_id = make_id(title, str(uuid.uuid4()))
    now = _utcnow()
    session.add(
        StoryThread(
            id=thread_id,
            slug=slugify(title),
            title=title,
            sector=sector,
            location=location,
            language="unknown",
            keywords=keywords,
            current_status="unknown",
            first_seen=now,
            last_seen=now,
            beat_count=0,
            article_count=0,
        )
    )
    await session.flush()
    return thread_id


async def create_event(session: AsyncSession, payload: TrackEventRequest) -> TrackedEvent:
    keywords, sector, status, keyword_query = prepare_track_request(payload)

    thread_id = await _attach_thread(
        session,
        title=payload.title,
        keywords=keywords,
        sector=sector,
        location=payload.location,
    )

    now = _utcnow()
    row = TrackedEventRow(
        id=str(uuid.uuid4())[:12],
        thread_id=thread_id,
        title=payload.title,
        keywords=keywords,
        keyword_query=keyword_query or build_keyword_query(keywords),
        sector=sector,
        location=payload.location,
        progress_status=status,
        source_article_url=payload.url,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    return await _row_to_model(session, row)


async def refresh_event(session: AsyncSession, event_id: str) -> TrackedEvent | None:
    """Recompute the event's current status from the attached thread.

    No provider APIs are called - the archive is populated by the scheduled
    ingest, and this endpoint reads from it. Previous implementation issued
    three API calls per refresh; this issues zero.
    """
    row = await session.get(TrackedEventRow, event_id)
    if row is None:
        return None

    if row.thread_id:
        thread = await session.get(StoryThread, row.thread_id)
        if thread is not None:
            row.progress_status = thread.current_status

    row.updated_at = _utcnow()
    await session.commit()
    return await _row_to_model(session, row)


async def delete_event(session: AsyncSession, event_id: str) -> bool:
    row = await session.get(TrackedEventRow, event_id)
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True
