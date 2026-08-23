import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select

from app.config import settings
from app.routers.admin import router as admin_router
from app.routers.events import router as events_router
from app.routers.paper import router as paper_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """App startup/shutdown.

    The previous `@app.on_event("shutdown")` form is deprecated in FastAPI
    and does not fire reliably on serverless-style hosts. A lifespan context
    manager is the supported replacement.
    """
    logger.info(
        "startup: providers=%s db=%s",
        settings.configured_providers,
        settings.has_database,
    )
    try:
        yield
    finally:
        if settings.has_database:
            from app.db.base import dispose_engine

            await dispose_engine()
            logger.info("shutdown: db engine disposed")


app = FastAPI(title="Bhopal News API", version="0.3.0", lifespan=lifespan)

# CORS. Vercel gives every preview deploy a per-commit URL, so an exact
# origin list can't cover them. `allow_origin_regex` runs alongside
# `allow_origins`, and either match is accepted.
_cors_kwargs: dict = {
    "allow_origins": settings.cors_origin_list,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if settings.cors_origin_regex:
    _cors_kwargs["allow_origin_regex"] = settings.cors_origin_regex

app.add_middleware(CORSMiddleware, **_cors_kwargs)

app.include_router(paper_router)
app.include_router(events_router)
app.include_router(admin_router)


@app.get("/health")
async def health() -> dict:
    """Report provider configuration and archive state.

    Render uses this as the deploy health probe, so it stays cheap and
    non-authenticated. An empty archive is otherwise indistinguishable from a
    broken key or exhausted quota, so provider config is surfaced explicitly.
    """
    from app.services.news_fetchers import PROVIDER_STATUS

    payload: dict = {
        "status": "ok",
        "version": app.version,
        "providers_configured": settings.configured_providers,
        "provider_last_call": PROVIDER_STATUS or None,
        "database": settings.has_database,
    }

    if not settings.has_database:
        return payload

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
    except Exception as exc:  # noqa: BLE001 - health must not raise
        payload["status"] = "degraded"
        payload["database_error"] = f"{type(exc).__name__}: {exc}"

    return payload
