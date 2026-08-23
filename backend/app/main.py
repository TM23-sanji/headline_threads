import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from app.config import settings
from app.routers.events import router as events_router
from app.routers.news import router as news_router
from app.routers.paper import router as paper_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Bhopal News API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(paper_router)
app.include_router(news_router)
app.include_router(events_router)


@app.on_event("shutdown")
async def _shutdown() -> None:
    from app.db.base import dispose_engine

    if settings.has_database:
        await dispose_engine()


@app.get("/health")
async def health() -> dict:
    """Report provider configuration and archive state.

    An empty result set is otherwise indistinguishable from a broken key or an
    exhausted quota, so provider status is surfaced explicitly.
    """
    from app.services.news_fetchers import PROVIDER_STATUS

    payload: dict = {
        "status": "ok",
        "providers_configured": settings.configured_providers,
        "provider_last_call": PROVIDER_STATUS or None,
        "database": settings.has_database,
    }

    if settings.has_database:
        from app.db.base import get_sessionmaker
        from app.db.models import Article, StoryThread, ThreadBeat

        try:
            async with get_sessionmaker()() as session:
                payload["archive"] = {
                    "articles": int(
                        await session.scalar(select(func.count()).select_from(Article)) or 0
                    ),
                    "threads": int(
                        await session.scalar(select(func.count()).select_from(StoryThread)) or 0
                    ),
                    "beats": int(
                        await session.scalar(select(func.count()).select_from(ThreadBeat)) or 0
                    ),
                    "latest": str(
                        await session.scalar(select(func.max(Article.published_at))) or ""
                    ),
                }
        except Exception as exc:  # noqa: BLE001
            payload["status"] = "degraded"
            payload["database_error"] = f"{type(exc).__name__}: {exc}"

    return payload
