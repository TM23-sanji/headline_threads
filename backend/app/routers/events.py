from fastapi import APIRouter, HTTPException

from app.models import (
    EventsResponse,
    KeywordGenerateRequest,
    KeywordGenerateResponse,
    TrackEventRequest,
    TrackedEvent,
)
from app.services.event_store import create_event, delete_event, get_event, list_events, refresh_event
from app.services.keywords import build_keyword_query, generate_keywords

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=EventsResponse)
async def get_events() -> EventsResponse:
    events = list_events()
    return EventsResponse(total=len(events), events=events)


@router.get("/{event_id}", response_model=TrackedEvent)
async def get_event_by_id(event_id: str) -> TrackedEvent:
    event = get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.post("/track", response_model=TrackedEvent)
async def track_event(payload: TrackEventRequest) -> TrackedEvent:
    return await create_event(payload)


@router.post("/keywords", response_model=KeywordGenerateResponse)
async def generate_event_keywords(payload: KeywordGenerateRequest) -> KeywordGenerateResponse:
    keywords, sector, status = generate_keywords(payload.title, payload.snippet)
    return KeywordGenerateResponse(
        keywords=keywords,
        keyword_query=build_keyword_query(keywords),
        sector=sector,
        inferred_status=status,
    )


@router.post("/{event_id}/refresh", response_model=TrackedEvent)
async def refresh_event_updates(event_id: str) -> TrackedEvent:
    event = await refresh_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.delete("/{event_id}")
async def remove_event(event_id: str) -> dict[str, bool]:
    deleted = delete_event(event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"deleted": True}
