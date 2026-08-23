"""Newspaper and story-chain endpoints, served from the Neon archive."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.db.models import Article, BeatArticle, StoryThread
from app.models import (
    Beat,
    BeatSource,
    FacetValue,
    PaperArticle,
    PaperResponse,
    PaperSection,
    Thread,
    ThreadDetail,
    ThreadsResponse,
)
from app.services import queries
from app.services.news_fetchers import SECTOR_LABELS

router = APIRouter(prefix="/api", tags=["paper"])


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


async def _thread_lookup(session: AsyncSession, article_ids: list[str]) -> dict[str, tuple[str, int]]:
    """Map article id -> (thread_id, beat_count) so cards can link to a chain."""
    if not article_ids:
        return {}

    rows = (
        await session.execute(
            select(BeatArticle.article_id, StoryThread.id, StoryThread.beat_count)
            .join(queries.ThreadBeat, queries.ThreadBeat.id == BeatArticle.beat_id)
            .join(StoryThread, StoryThread.id == queries.ThreadBeat.thread_id)
            .where(BeatArticle.article_id.in_(article_ids))
        )
    ).all()
    return {aid: (tid, count) for aid, tid, count in rows}


def _to_paper_article(
    article: Article, threads: dict[str, tuple[str, int]]
) -> PaperArticle:
    thread_id, beat_count = threads.get(article.id, (None, 0))
    return PaperArticle(
        id=article.id,
        title=article.title,
        snippet=article.snippet or "",
        url=article.url,
        source=article.source,
        provider=article.provider,
        language=article.language,
        published_at=_iso(article.published_at),
        image_url=article.image_url,
        sector=article.sector,
        progress_status=article.progress_status,
        confidence=article.confidence,
        keywords=[k.keyword for k in (article.keywords or [])][:6],
        thread_id=thread_id,
        thread_beat_count=beat_count,
    )


@router.get("/paper", response_model=PaperResponse)
async def get_paper(
    session: AsyncSession = Depends(get_session),
    city: str = Query("Bhopal"),
    sector: list[str] = Query(default=[]),
    status: list[str] = Query(default=[]),
    language: list[str] = Query(default=[], description="en / hi"),
    provider: list[str] = Query(default=[]),
    source: list[str] = Query(default=[]),
    keyword: list[str] = Query(default=[]),
    since: str | None = Query(default=None, description="today|week|month|quarter"),
    q: str | None = Query(default=None),
    limit: int = Query(default=120, le=400),
) -> PaperResponse:
    filters = queries.ArticleFilters(
        sector=sector,
        status=status,
        language=language,
        provider=provider,
        source=source,
        keyword=keyword,
        since=since,
        q=q,
    )

    articles = await queries.list_articles(session, filters, limit=limit)
    threads = await _thread_lookup(session, [a.id for a in articles])

    grouped: dict[str, list[PaperArticle]] = {}
    for article in articles:
        grouped.setdefault(article.sector, []).append(
            _to_paper_article(article, threads)
        )

    sections = [
        PaperSection(
            sector=key,
            label=SECTOR_LABELS.get(key, key.replace("_", " ").title()),
            articles=items,
        )
        for key, items in sorted(grouped.items(), key=lambda kv: -len(kv[1]))
        if items
    ]

    raw_facets = await queries.facets(session, filters)

    return PaperResponse(
        city=city,
        date=datetime.now().strftime("%A, %d %B %Y"),
        total=len(articles),
        sections=sections,
        facets={
            name: [FacetValue(**v) for v in values]
            for name, values in raw_facets.items()
        },
        applied=filters.active(),
    )


def _to_thread(row: StoryThread) -> Thread:
    return Thread(
        id=row.id,
        slug=row.slug,
        title=row.title,
        sector=row.sector,
        language=row.language,
        location=row.location,
        current_status=row.current_status,
        first_seen=_iso(row.first_seen) or "",
        last_seen=_iso(row.last_seen) or "",
        beat_count=row.beat_count,
        article_count=row.article_count,
        keywords=list(row.keywords or [])[:8],
    )


@router.get("/threads", response_model=ThreadsResponse)
async def get_threads(
    session: AsyncSession = Depends(get_session),
    sector: str | None = None,
    status: str | None = None,
    language: str | None = None,
    chains_only: bool = Query(
        default=False, description="only stories with more than one development"
    ),
    limit: int = Query(default=50, le=200),
) -> ThreadsResponse:
    rows = await queries.list_threads(
        session,
        sector=sector,
        status=status,
        language=language,
        chains_only=chains_only,
        limit=limit,
    )
    return ThreadsResponse(total=len(rows), threads=[_to_thread(r) for r in rows])


@router.get("/threads/{thread_id}", response_model=ThreadDetail)
async def get_thread_detail(
    thread_id: str, session: AsyncSession = Depends(get_session)
) -> ThreadDetail:
    row = await queries.get_thread(session, thread_id)
    if row is None:
        raise HTTPException(status_code=404, detail="thread not found")

    beats = []
    for beat, articles in await queries.thread_beats(session, thread_id):
        beats.append(
            Beat(
                id=beat.id,
                headline=beat.headline,
                summary=beat.summary,
                occurred_at=_iso(beat.occurred_at) or "",
                status=beat.status,
                is_status_change=beat.is_status_change,
                previous_status=beat.previous_status,
                source_count=beat.source_count,
                sources=[
                    BeatSource(
                        id=a.id,
                        title=a.title,
                        url=a.url,
                        source=a.source,
                        provider=a.provider,
                        language=a.language,
                        published_at=_iso(a.published_at),
                    )
                    for a in articles
                ],
            )
        )

    return ThreadDetail(**_to_thread(row).model_dump(), beats=beats)
