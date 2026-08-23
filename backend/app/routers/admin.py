"""Admin endpoints.

Currently exposes the ingest trigger so a scheduler (GitHub Actions) can hit
it periodically. History cannot be backfilled from any provider, so the
archive only grows if this route is called regularly.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.base import get_session
from app.services.ingest import ingest
from app.services.news_fetchers import MP_QUERY

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _require_secret(x_ingest_secret: str | None = Header(default=None)) -> None:
    """Guard admin endpoints with a shared secret.

    `secrets.compare_digest` avoids timing side-channels. Deployments without
    a configured secret refuse the call outright instead of silently allowing
    it - a missing env var must never be a bypass.
    """
    configured = settings.ingest_secret.strip()
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingest secret is not configured on the server",
        )
    provided = (x_ingest_secret or "").strip()
    if not provided or not secrets.compare_digest(provided, configured):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


@router.post("/ingest", dependencies=[Depends(_require_secret)])
async def trigger_ingest(
    query: str = MP_QUERY,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await ingest(session, query=query)
    return result.as_dict()
