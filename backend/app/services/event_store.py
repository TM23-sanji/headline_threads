import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.models import TrackEventRequest, TrackedEvent
from app.services.keywords import aggregate_progress, new_timeline_entry, prepare_track_request, score_article_match
from app.services.news_fetchers import fetch_all_articles


def _ensure_store() -> None:
    settings.events_file.parent.mkdir(parents=True, exist_ok=True)
    if not settings.events_file.exists():
        settings.events_file.write_text("[]", encoding="utf-8")


def _load_events() -> list[dict]:
    _ensure_store()
    return json.loads(settings.events_file.read_text(encoding="utf-8"))


def _save_events(events: list[dict]) -> None:
    _ensure_store()
    settings.events_file.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")


def list_events() -> list[TrackedEvent]:
    return [TrackedEvent.model_validate(item) for item in _load_events()]


def get_event(event_id: str) -> TrackedEvent | None:
    for item in _load_events():
        if item["id"] == event_id:
            return TrackedEvent.model_validate(item)
    return None


async def create_event(payload: TrackEventRequest) -> TrackedEvent:
    keywords, sector, status, keyword_query = prepare_track_request(payload)
    now = datetime.now(timezone.utc).isoformat()

    event = {
        "id": str(uuid.uuid4())[:12],
        "title": payload.title,
        "keywords": keywords,
        "sector": sector,
        "location": payload.location,
        "progress_status": status,
        "created_at": now,
        "updated_at": now,
        "source_article_url": payload.url,
        "timeline": [],
        "keyword_query": keyword_query,
    }

    events = _load_events()
    events.insert(0, event)
    _save_events(events)

    refreshed = await refresh_event(event["id"])
    return refreshed or TrackedEvent.model_validate(event)


async def refresh_event(event_id: str) -> TrackedEvent | None:
    events = _load_events()
    target_index = next((idx for idx, item in enumerate(events) if item["id"] == event_id), None)
    if target_index is None:
        return None

    event = events[target_index]
    query = event.get("keyword_query") or " OR ".join(event.get("keywords", []))
    articles = await fetch_all_articles(query)

    existing_urls = {entry.get("url") for entry in event.get("timeline", [])}
    keywords = event.get("keywords", [])

    for article in articles:
        score, matched = score_article_match(f"{article.title} {article.snippet}", keywords)
        if score < 0.34:
            continue
        if article.url in existing_urls:
            continue

        event.setdefault("timeline", []).append(new_timeline_entry(article, keywords, score, matched))
        existing_urls.add(article.url)

    event["timeline"] = sorted(
        event.get("timeline", []),
        key=lambda entry: entry.get("published_at") or entry.get("captured_at", ""),
        reverse=True,
    )
    event["progress_status"] = aggregate_progress(event.get("timeline", []))
    event["updated_at"] = datetime.now(timezone.utc).isoformat()

    events[target_index] = event
    _save_events(events)
    return TrackedEvent.model_validate(event)


def delete_event(event_id: str) -> bool:
    events = _load_events()
    filtered = [item for item in events if item["id"] != event_id]
    if len(filtered) == len(events):
        return False
    _save_events(filtered)
    return True
