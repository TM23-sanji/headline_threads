from fastapi import APIRouter, HTTPException, Query

from app.models import (
    EventsResponse,
    KeywordGenerateRequest,
    KeywordGenerateResponse,
    NewspaperResponse,
    NewspaperSection,
    NewsResponse,
    Sector,
    TrackEventRequest,
    TrackedEvent,
)
from app.services.classifier import classify_articles
from app.services.keywords import build_keyword_query, generate_keywords
from app.services.news_fetchers import MP_QUERY, SECTOR_LABELS, fetch_all_articles

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("", response_model=NewsResponse)
async def get_news(
    q: str = Query(default=MP_QUERY, description="Search query for MP/Bhopal news"),
    city: str = Query(default="Bhopal"),
    sector: Sector | None = Query(default=None, description="Filter by classified sector"),
) -> NewsResponse:
    articles = await fetch_all_articles(q)
    classified = classify_articles(articles, sector=sector)
    providers = sorted({article.provider or "unknown" for article in articles})

    return NewsResponse(
        query=q,
        city=city,
        sector=sector,
        total=len(classified),
        articles=classified,
        providers=providers,
    )


@router.get("/paper", response_model=NewspaperResponse)
async def get_newspaper(
    city: str = Query(default="Bhopal"),
    sector: Sector | None = Query(default=None),
) -> NewspaperResponse:
    articles = await fetch_all_articles(MP_QUERY)
    classified = classify_articles(articles, sector=sector)

    grouped: dict[Sector, list] = {key: [] for key in SECTOR_LABELS}
    for article in classified:
        if article.keep or sector:
            grouped[article.sector].append(article)

    sections = [
        NewspaperSection(sector=sector_key, label=SECTOR_LABELS[sector_key], articles=items)
        for sector_key, items in grouped.items()
        if items
    ]

    from datetime import datetime

    return NewspaperResponse(
        city=city,
        date=datetime.now().strftime("%A, %d %B %Y"),
        sections=sections,
        total=sum(len(section.articles) for section in sections),
    )
