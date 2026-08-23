"""Tracked-event endpoints.

The keyword-generation preview stays synchronous and does no I/O; every other
route reads or writes the Postgres archive via `event_store`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.models import (
    EventsResponse,
    KeywordGenerateRequest,
    KeywordGenerateResponse,
    TrackEventRequest,
    TrackedEvent,
)
from app.services.event_store import (
    create_event,
    delete_event,
    get_event,
    list_events,
    refresh_event,
)
from app.services.keywords import build_keyword_query, generate_keywords

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=EventsResponse)
async def get_events(session: AsyncSession = Depends(get_session)) -> EventsResponse:
    events = await list_events(session)
    return EventsResponse(total=len(events), events=events)


@router.get("/{event_id}", response_model=TrackedEvent)
async def get_event_by_id(
    event_id: str, session: AsyncSession = Depends(get_session)
) -> TrackedEvent:
    event = await get_event(session, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.post("/track", response_model=TrackedEvent)
async def track_event(
    payload: TrackEventRequest, session: AsyncSession = Depends(get_session)
) -> TrackedEvent:
    return await create_event(session, payload)


@router.post("/keywords", response_model=KeywordGenerateResponse)
async def generate_event_keywords(
    payload: KeywordGenerateRequest,
) -> KeywordGenerateResponse:
    keywords, sector, status = generate_keywords(payload.title, payload.snippet)
    return KeywordGenerateResponse(
        keywords=keywords,
        keyword_query=build_keyword_query(keywords),
        sector=sector,
        inferred_status=status,
    )


@router.post("/{event_id}/refresh", response_model=TrackedEvent)
async def refresh_event_updates(
    event_id: str, session: AsyncSession = Depends(get_session)
) -> TrackedEvent:
    event = await refresh_event(session, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.delete("/{event_id}")
async def remove_event(
    event_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, bool]:
    deleted = await delete_event(session, event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"deleted": True}
