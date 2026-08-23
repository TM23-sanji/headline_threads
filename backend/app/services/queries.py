"""Read queries for the newspaper and thread views.

All filtering happens in Postgres against the ingested archive, so no filter
combination costs an API call. Facet counts are computed with the filter under
consideration removed, which is what lets the UI show how many results each
option *would* return rather than only counts for the current selection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Article, ArticleKeyword, BeatArticle, StoryThread, ThreadBeat

__all__ = [
    "Article", "ArticleKeyword", "BeatArticle", "StoryThread", "ThreadBeat",
    "ArticleFilters", "list_articles", "count_articles", "facets",
    "list_threads", "get_thread", "thread_beats", "SINCE_WINDOWS",
]

SINCE_WINDOWS = {
    "today": timedelta(days=1),
    "week": timedelta(days=7),
    "month": timedelta(days=30),
    "quarter": timedelta(days=90),
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ArticleFilters:
    sector: list[str] = field(default_factory=list)
    status: list[str] = field(default_factory=list)
    language: list[str] = field(default_factory=list)
    provider: list[str] = field(default_factory=list)
    source: list[str] = field(default_factory=list)
    keyword: list[str] = field(default_factory=list)
    since: str | None = None
    q: str | None = None

    def active(self) -> dict[str, list[str] | str | None]:
        return {
            k: v
            for k, v in {
                "sector": self.sector,
                "status": self.status,
                "language": self.language,
                "provider": self.provider,
                "source": self.source,
                "keyword": self.keyword,
                "since": self.since,
                "q": self.q,
            }.items()
            if v
        }


def _conditions(f: ArticleFilters, *, skip: str | None = None) -> list:
    """Build WHERE clauses, optionally omitting one facet.

    Omitting the facet being counted is what makes facet counts represent
    "results if you picked this" instead of "results you already have".
    """
    conds = []

    if f.sector and skip != "sector":
        conds.append(Article.sector.in_(f.sector))
    if f.status and skip != "status":
        conds.append(Article.progress_status.in_(f.status))
    if f.language and skip != "language":
        conds.append(Article.language.in_(f.language))
    if f.provider and skip != "provider":
        conds.append(Article.provider.in_(f.provider))
    if f.source and skip != "source":
        conds.append(Article.source.in_(f.source))

    if f.since and skip != "since":
        window = SINCE_WINDOWS.get(f.since)
        if window:
            conds.append(Article.published_at >= utcnow() - window)

    if f.keyword and skip != "keyword":
        conds.append(
            Article.id.in_(
                select(ArticleKeyword.article_id).where(
                    ArticleKeyword.keyword.in_([k.lower() for k in f.keyword])
                )
            )
        )

    if f.q and skip != "q":
        pattern = f"%{f.q.lower()}%"
        conds.append(
            or_(
                func.lower(Article.title).like(pattern),
                func.lower(Article.snippet).like(pattern),
            )
        )

    return conds


def _base(f: ArticleFilters, *, skip: str | None = None) -> Select:
    stmt = select(Article)
    conds = _conditions(f, skip=skip)
    return stmt.where(and_(*conds)) if conds else stmt


async def list_articles(
    session: AsyncSession, f: ArticleFilters, limit: int = 120
) -> list[Article]:
    stmt = (
        _base(f)
        .options(selectinload(Article.keywords))
        .order_by(Article.published_at.desc().nullslast())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def count_articles(session: AsyncSession, f: ArticleFilters) -> int:
    conds = _conditions(f)
    stmt = select(func.count()).select_from(Article)
    if conds:
        stmt = stmt.where(and_(*conds))
    return int(await session.scalar(stmt) or 0)


async def _facet(
    session: AsyncSession, f: ArticleFilters, column, name: str
) -> list[dict]:
    conds = _conditions(f, skip=name)
    stmt = select(column, func.count()).group_by(column).order_by(func.count().desc())
    if conds:
        stmt = stmt.where(and_(*conds))
    rows = (await session.execute(stmt)).all()
    return [
        {"value": value, "count": count}
        for value, count in rows
        if value is not None
    ]


async def facets(session: AsyncSession, f: ArticleFilters) -> dict[str, list[dict]]:
    """Counts per facet value, each computed with its own filter removed."""
    out = {
        "sector": await _facet(session, f, Article.sector, "sector"),
        "status": await _facet(session, f, Article.progress_status, "status"),
        "language": await _facet(session, f, Article.language, "language"),
        "provider": await _facet(session, f, Article.provider, "provider"),
        "source": await _facet(session, f, Article.source, "source"),
    }

    # Date buckets need one count per window rather than a GROUP BY.
    since_counts = []
    for key, window in SINCE_WINDOWS.items():
        conds = _conditions(f, skip="since")
        conds.append(Article.published_at >= utcnow() - window)
        n = await session.scalar(
            select(func.count()).select_from(Article).where(and_(*conds))
        )
        since_counts.append({"value": key, "count": int(n or 0)})
    out["since"] = since_counts

    # Top keywords for the chip rail.
    kconds = _conditions(f, skip="keyword")
    kstmt = (
        select(ArticleKeyword.keyword, func.count())
        .join(Article, Article.id == ArticleKeyword.article_id)
        .group_by(ArticleKeyword.keyword)
        .having(func.count() > 1)
        .order_by(func.count().desc())
        .limit(40)
    )
    if kconds:
        kstmt = kstmt.where(and_(*kconds))
    out["keyword"] = [
        {"value": k, "count": c} for k, c in (await session.execute(kstmt)).all()
    ]

    return out


# --------------------------------------------------------------------------
# Threads
# --------------------------------------------------------------------------


async def list_threads(
    session: AsyncSession,
    *,
    sector: str | None = None,
    status: str | None = None,
    language: str | None = None,
    chains_only: bool = False,
    limit: int = 50,
) -> list[StoryThread]:
    stmt = select(StoryThread)
    if sector:
        stmt = stmt.where(StoryThread.sector == sector)
    if status:
        stmt = stmt.where(StoryThread.current_status == status)
    if language:
        stmt = stmt.where(StoryThread.language == language)
    if chains_only:
        # Only stories that actually developed over more than one beat.
        stmt = stmt.where(StoryThread.beat_count > 1)

    stmt = stmt.order_by(
        StoryThread.beat_count.desc(), StoryThread.last_seen.desc()
    ).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def get_thread(session: AsyncSession, thread_id: str) -> StoryThread | None:
    return await session.scalar(
        select(StoryThread)
        .where(StoryThread.id == thread_id)
        .options(selectinload(StoryThread.beats))
    )


async def thread_beats(session: AsyncSession, thread_id: str) -> list[tuple[ThreadBeat, list[Article]]]:
    """Beats oldest-first, each with its corroborating articles."""
    beats = list(
        (
            await session.execute(
                select(ThreadBeat)
                .where(ThreadBeat.thread_id == thread_id)
                .order_by(ThreadBeat.occurred_at)
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

    grouped: dict[str, list[Article]] = {}
    for beat_id, article in rows:
        grouped.setdefault(beat_id, []).append(article)

    return [(b, grouped.get(b.id, [])) for b in beats]
