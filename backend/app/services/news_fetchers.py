import asyncio
import hashlib
import logging
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.models import NewsArticle
from app.services.normalize import (
    canonicalize_source,
    clean_content_stub,
    clean_provider_keywords,
    normalize_language,
    parse_published_at,
    to_iso,
)

logger = logging.getLogger(__name__)

MP_QUERY = 'Bhopal OR "Madhya Pradesh"'

SECTOR_LABELS = {
    "construction": "Construction & Infra",
    "roads": "Roads & Potholes",
    "transport": "Transport",
    "water_lakes": "Water & Lakes",
    "bmc_civic": "BMC & Civic",
    "health": "Health",
    "crime": "Crime & Safety",
    "politics": "Politics",
    "environment": "Environment",
    "other": "General",
}


def _article_id(title: str, url: str) -> str:
    return hashlib.sha256(f"{title}|{url}".encode()).hexdigest()[:16]


def _parse_date(value: str | None) -> str | None:
    """Normalize a provider timestamp to an ISO-8601 UTC string."""
    return to_iso(parse_published_at(value))


async def fetch_newsdata(query: str = MP_QUERY) -> list[NewsArticle]:
    if not settings.newsdata_api_key:
        return []

    # qInTitle restricts matching to the headline. Measured on live data this
    # lifts Bhopal/MP relevance from 2/10 (plain `q`) to 10/10, and surfaces
    # Hindi articles that the body-wide search buried.
    # removeduplicate is free on this tier and drops provider-side repeats.
    params = {
        "apikey": settings.newsdata_api_key,
        "qInTitle": query,
        "country": "in",
        "language": "hi,en",
        "removeduplicate": 1,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get("https://newsdata.io/api/1/latest", params=params)
        response.raise_for_status()
        payload = response.json()

    articles: list[NewsArticle] = []
    for item in payload.get("results", []):
        title = item.get("title") or ""
        url = item.get("link") or ""
        if not title or not url:
            continue

        snippet = item.get("description") or ""
        source_raw = item.get("source_name") or "NewsData"
        published = _parse_date(item.get("pubDate"))

        articles.append(
            NewsArticle(
                id=_article_id(title, url),
                title=title,
                snippet=snippet,
                url=url,
                source=canonicalize_source(source_raw),
                source_raw=source_raw,
                published_at=published,
                published_at_iso=published,
                image_url=item.get("image_url"),
                language=normalize_language(item.get("language"), text=f"{title} {snippet}"),
                provider="newsdata",
                provider_keywords=clean_provider_keywords(item.get("keywords")),
                provider_category=[str(c) for c in (item.get("category") or [])],
                author=", ".join(item.get("creator") or []) or None,
                source_id=item.get("source_id"),
                source_priority=item.get("source_priority"),
                content_stub=clean_content_stub(item.get("content")),
                is_duplicate=bool(item.get("duplicate")),
            )
        )

    return articles


async def fetch_gnews(query: str = MP_QUERY) -> list[NewsArticle]:
    if not settings.gnews_api_key:
        return []

    # `country` filters by *publisher* location, not story location (per GNews
    # docs), so it is deliberately omitted. The default `in=title,description`
    # already measures 10/10 on-topic; adding `content` drops it to 4/10.
    # Note: the free tier serves news with a ~12 hour delay.
    params = {
        "q": query,
        "lang": "en",
        "max": 10,
        "apikey": settings.gnews_api_key,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get("https://gnews.io/api/v4/search", params=params)
        response.raise_for_status()
        payload = response.json()

    articles: list[NewsArticle] = []
    for item in payload.get("articles", []):
        title = item.get("title") or ""
        url = item.get("url") or ""
        if not title or not url:
            continue

        source_obj = item.get("source") or {}
        snippet = item.get("description") or ""
        source_raw = source_obj.get("name") or "GNews"
        published = _parse_date(item.get("publishedAt"))

        articles.append(
            NewsArticle(
                id=_article_id(title, url),
                title=title,
                snippet=snippet,
                url=url,
                source=canonicalize_source(source_raw),
                source_raw=source_raw,
                published_at=published,
                published_at_iso=published,
                image_url=item.get("image"),
                language=normalize_language(item.get("lang"), text=f"{title} {snippet}"),
                provider="gnews",
                source_id=source_obj.get("id"),
                content_stub=clean_content_stub(item.get("content")),
            )
        )

    return articles


async def fetch_newsapi(query: str = MP_QUERY) -> list[NewsArticle]:
    if not settings.newsapi_api_key:
        return []

    # searchIn=title restricts matching to the headline: measured 5/10 -> 10/10
    # on-topic. Without it, /everything matches the article body and returns
    # national stories that merely mention Madhya Pradesh in passing.
    params = {
        "q": query,
        "searchIn": "title",
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 10,
        "apiKey": settings.newsapi_api_key,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get("https://newsapi.org/v2/everything", params=params)
        response.raise_for_status()
        payload = response.json()

    articles: list[NewsArticle] = []
    for item in payload.get("articles", []):
        title = item.get("title") or ""
        url = item.get("url") or ""
        if not title or not url or title == "[Removed]":
            continue

        source_obj = item.get("source") or {}
        snippet = item.get("description") or ""
        source_raw = source_obj.get("name") or "NewsAPI"
        published = _parse_date(item.get("publishedAt"))

        articles.append(
            NewsArticle(
                id=_article_id(title, url),
                title=title,
                snippet=snippet,
                url=url,
                source=canonicalize_source(source_raw),
                source_raw=source_raw,
                published_at=published,
                published_at_iso=published,
                image_url=item.get("urlToImage"),
                # NewsAPI hardcodes English; script detection corrects that.
                language=normalize_language("en", text=f"{title} {snippet}"),
                provider="newsapi",
                author=item.get("author"),
                source_id=source_obj.get("id"),
                content_stub=clean_content_stub(item.get("content")),
            )
        )

    return articles


def mock_articles() -> list[NewsArticle]:
    now = datetime.now(timezone.utc).isoformat()
    samples = [
        (
            "संत हिरदाराम नगर में एलिवेटेड ब्रिज का काम धीमा, त्यौहारों में कारोबार प्रभावित",
            "निर्माणाधीन एलिवेटेड ब्रिज का काम मंद गति से चलने से ट्रैफिक अव्यवस्थित हो गया है।",
            "https://www.naidunia.com/example/elevated-bridge-delay",
            "Nai Dunia",
        ),
        (
            "BMC repairs fail within days as patched road deteriorates, streetlights go dark",
            "Residents report potholes returning soon after municipal repairs in Bhopal.",
            "https://timesofindia.indiatimes.com/city/bhopal/example-road-repairs",
            "Times of India",
        ),
        (
            "Four Swine Flu Deaths, 25 Cases Reported Across MP",
            "Health department data shows rising swine flu cases across Madhya Pradesh.",
            "https://www.freepressjournal.in/bhopal/example-swine-flu",
            "Free Press Journal",
        ),
        (
            "Prabhat Square flyover delay pushes cost from Rs 44 crore to Rs 72 crore",
            "PWD officials face review as coordination issues stall Bhopal flyover work.",
            "https://www.bhaskar.com/local/mp/bhopal/example-flyover-delay",
            "Dainik Bhaskar",
        ),
    ]

    return [
        NewsArticle(
            id=_article_id(title, url),
            title=title,
            snippet=snippet,
            url=url,
            source=source,
            published_at=now,
            provider="mock",
        )
        for title, snippet, url, source in samples
    ]


PROVIDER_STATUS: dict[str, dict[str, object]] = {}


async def fetch_all_articles(query: str = MP_QUERY) -> list[NewsArticle]:
    """Fetch from all three providers, isolating failures.

    Free tiers rate-limit aggressively (~100-200 req/day). Previously a single
    429 propagated out of asyncio.gather and discarded the other two providers'
    results as well; each provider is now independently recoverable.
    """
    fetchers = (
        ("newsdata", fetch_newsdata),
        ("gnews", fetch_gnews),
        ("newsapi", fetch_newsapi),
    )

    results = await asyncio.gather(
        *(fetcher(query) for _, fetcher in fetchers),
        return_exceptions=True,
    )

    merged: dict[str, NewsArticle] = {}
    for (name, _), result in zip(fetchers, results, strict=True):
        if isinstance(result, BaseException):
            detail = f"{type(result).__name__}: {result}"
            if isinstance(result, httpx.HTTPStatusError):
                detail = f"HTTP {result.response.status_code}"
            PROVIDER_STATUS[name] = {"ok": False, "count": 0, "error": detail}
            logger.warning("provider %s failed: %s", name, detail)
            continue

        PROVIDER_STATUS[name] = {"ok": True, "count": len(result), "error": None}
        for article in result:
            merged.setdefault(article.id, article)

    if merged:
        return list(merged.values())

    # Only fall back to samples when nothing is configured. An empty result
    # from configured providers is real information and must not be masked.
    if not settings.configured_providers:
        logger.warning("no provider keys configured - serving mock articles")
        return mock_articles()

    logger.warning("all configured providers returned no articles")
    return []
