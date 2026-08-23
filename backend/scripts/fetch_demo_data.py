"""Capture live responses from all three news APIs into demo fixtures.

Run from the backend/ directory:

    uv run python scripts/fetch_demo_data.py
    uv run python scripts/fetch_demo_data.py --query 'Bhopal metro'

Writes into backend/data/demo/:
    raw_<provider>.json    exact API envelope, unmodified (for schema reference)
    demo_articles.json     merged + deduped NewsArticle[] (drop-in mock replacement)
    demo_articles.txt      human-readable dump for eyeballing
    capture_report.json    per-provider status, counts, errors, field coverage

Each provider is isolated: a 429 or auth failure on one is recorded and the
other two still get captured.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# Make `app` importable when run as a plain script from backend/.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings  # noqa: E402
from app.models import NewsArticle  # noqa: E402
from app.services.news_fetchers import MP_QUERY, _article_id  # noqa: E402
from app.services.normalize import (  # noqa: E402
    canonicalize_source,
    clean_content_stub,
    clean_provider_keywords,
    normalize_language,
    parse_published_at,
    to_iso,
)

OUT_DIR = BACKEND_DIR / "data" / "demo"
TIMEOUT = 25.0


# --------------------------------------------------------------------------
# Provider definitions: how to call, and how to normalize one item.
# --------------------------------------------------------------------------


def _norm_newsdata(item: dict[str, Any]) -> dict[str, Any]:
    title = item.get("title") or ""
    snippet = item.get("description") or ""
    source_raw = item.get("source_name") or item.get("source_id") or "NewsData"
    return {
        "title": title,
        "url": item.get("link") or "",
        "snippet": snippet,
        "source": canonicalize_source(source_raw),
        "source_raw": source_raw,
        "published_at": to_iso(parse_published_at(item.get("pubDate"))),
        "image_url": item.get("image_url"),
        "language": normalize_language(item.get("language"), text=f"{title} {snippet}"),
        "provider_keywords": clean_provider_keywords(item.get("keywords")),
        "provider_category": [str(c) for c in (item.get("category") or [])],
        "author": ", ".join(item.get("creator") or []) or None,
        "source_id": item.get("source_id"),
        "source_priority": item.get("source_priority"),
        "content_stub": clean_content_stub(item.get("content")),
        "is_duplicate": bool(item.get("duplicate")),
    }


def _norm_gnews(item: dict[str, Any]) -> dict[str, Any]:
    title = item.get("title") or ""
    snippet = item.get("description") or ""
    src = item.get("source") or {}
    source_raw = src.get("name") or "GNews"
    return {
        "title": title,
        "url": item.get("url") or "",
        "snippet": snippet,
        "source": canonicalize_source(source_raw),
        "source_raw": source_raw,
        "published_at": to_iso(parse_published_at(item.get("publishedAt"))),
        "image_url": item.get("image"),
        "language": normalize_language(item.get("lang"), text=f"{title} {snippet}"),
        "source_id": src.get("id"),
        "content_stub": clean_content_stub(item.get("content")),
    }


def _norm_newsapi(item: dict[str, Any]) -> dict[str, Any]:
    title = item.get("title") or ""
    snippet = item.get("description") or ""
    src = item.get("source") or {}
    source_raw = src.get("name") or "NewsAPI"
    return {
        "title": title,
        "url": item.get("url") or "",
        "snippet": snippet,
        "source": canonicalize_source(source_raw),
        "source_raw": source_raw,
        "published_at": to_iso(parse_published_at(item.get("publishedAt"))),
        "image_url": item.get("urlToImage"),
        "language": normalize_language("en", text=f"{title} {snippet}"),
        "author": item.get("author"),
        "source_id": src.get("id"),
        "content_stub": clean_content_stub(item.get("content")),
    }


PROVIDERS = [
    {
        "name": "newsdata",
        "key": settings.newsdata_api_key,
        "key_env": "NEWSDATA_API_KEY",
        "url": "https://newsdata.io/api/1/latest",
        "params": lambda q: {
            "apikey": settings.newsdata_api_key,
            "qInTitle": q,
            "country": "in",
            "language": "hi,en",
            "removeduplicate": 1,
        },
        "items": lambda p: p.get("results") or [],
        "normalize": _norm_newsdata,
    },
    {
        "name": "gnews",
        "key": settings.gnews_api_key,
        "key_env": "GNEWS_API_KEY",
        "url": "https://gnews.io/api/v4/search",
        "params": lambda q: {
            "q": q,
            "lang": "en",
            "max": 10,
            "apikey": settings.gnews_api_key,
        },
        "items": lambda p: p.get("articles") or [],
        "normalize": _norm_gnews,
    },
    {
        "name": "newsapi",
        "key": settings.newsapi_api_key,
        "key_env": "NEWS_API_KEY",
        "url": "https://newsapi.org/v2/everything",
        "params": lambda q: {
            "q": q,
            "searchIn": "title",
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 10,
            "apiKey": settings.newsapi_api_key,
        },
        "items": lambda p: p.get("articles") or [],
        "normalize": _norm_newsapi,
    },
]


def _redact(params: dict[str, Any]) -> dict[str, Any]:
    """Never write API keys into committed fixtures."""
    safe = {}
    for k, v in params.items():
        safe[k] = "***REDACTED***" if k.lower() in {"apikey", "api_key"} else v
    return safe


async def capture(provider: dict[str, Any], query: str) -> dict[str, Any]:
    name = provider["name"]
    result: dict[str, Any] = {
        "provider": name,
        "status": "unknown",
        "http_status": None,
        "raw_count": 0,
        "usable_count": 0,
        "error": None,
    }

    if not provider["key"]:
        result["status"] = "skipped_no_key"
        result["error"] = f"{provider['key_env']} is not set"
        print(f"  [skip] {name}: {provider['key_env']} not set")
        return result

    params = provider["params"](query)

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(provider["url"], params=params)
        result["http_status"] = response.status_code
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:400]
        result["status"] = "http_error"
        result["error"] = f"HTTP {exc.response.status_code}: {body}"
        print(f"  [FAIL] {name}: HTTP {exc.response.status_code} - {body[:160]}")
        return result
    except Exception as exc:  # noqa: BLE001 - capture anything, keep others alive
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"
        print(f"  [FAIL] {name}: {type(exc).__name__}: {exc}")
        return result

    items = provider["items"](payload)
    result["raw_count"] = len(items)

    # Persist the untouched envelope for schema reference (query redacted).
    raw_path = OUT_DIR / f"raw_{name}.json"
    raw_path.write_text(
        json.dumps(
            {
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "endpoint": provider["url"],
                "params": _redact(params),
                "payload": payload,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    normalized: list[dict[str, Any]] = []
    for item in items:
        n = provider["normalize"](item)
        if not n["title"] or not n["url"]:
            continue
        if n["title"].strip() == "[Removed]":
            continue
        n["provider"] = name
        n["id"] = _article_id(n["title"], n["url"])
        normalized.append(n)

    result["usable_count"] = len(normalized)
    result["articles"] = normalized
    result["status"] = "ok"
    print(f"  [ ok ] {name}: {len(items)} raw -> {len(normalized)} usable  (-> {raw_path.name})")
    return result


def field_coverage(articles: list[dict[str, Any]]) -> dict[str, Any]:
    """How often is each optional field actually populated? Drives later decisions."""
    if not articles:
        return {}
    fields = ["snippet", "published_at", "image_url", "language", "source"]
    cov: dict[str, Any] = {}
    for f in fields:
        present = sum(1 for a in articles if a.get(f))
        cov[f] = {"present": present, "total": len(articles), "pct": round(100 * present / len(articles))}
    return cov


RELEVANCE_RE = re.compile(r"bhopal|madhya\s*pradesh|भोपाल|मध्य\s*प्रदेश", re.IGNORECASE)


def on_topic_stats(articles: list[dict[str, Any]]) -> dict[str, Any]:
    """Share of articles actually about Bhopal/MP - the Phase A quality gate."""
    per: dict[str, dict[str, int]] = {}
    off: list[str] = []
    for a in articles:
        prov = a.get("provider", "?")
        bucket = per.setdefault(prov, {"on": 0, "total": 0})
        bucket["total"] += 1
        if RELEVANCE_RE.search(f"{a.get('title', '')} {a.get('snippet') or ''}"):
            bucket["on"] += 1
        else:
            off.append(f"[{prov}] {a.get('title', '')[:80]}")
    total = sum(b["total"] for b in per.values())
    on = sum(b["on"] for b in per.values())
    return {
        "per_provider": {k: f"{v['on']}/{v['total']}" for k, v in per.items()},
        "overall": f"{on}/{total}",
        "pct": round(100 * on / total) if total else 0,
        "off_topic": off,
    }


def date_formats(articles: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Sample raw date strings per provider - proves the format mismatch."""
    seen: dict[str, list[str]] = {}
    for a in articles:
        p = a.get("provider", "?")
        if a.get("published_at") and len(seen.setdefault(p, [])) < 3:
            seen[p].append(a["published_at"])
    return seen


async def main() -> int:
    parser = argparse.ArgumentParser(description="Capture demo data from the three news APIs")
    parser.add_argument("--query", default=MP_QUERY, help="Search query to send to all providers")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\nQuery: {args.query}")
    print(f"Output: {OUT_DIR}\n")
    print("Fetching from 3 providers...")

    results = await asyncio.gather(*(capture(p, args.query) for p in PROVIDERS))

    # Merge + dedupe by article id, same strategy as fetch_all_articles().
    merged: dict[str, dict[str, Any]] = {}
    dupes = 0
    for r in results:
        for a in r.get("articles", []):
            if a["id"] in merged:
                dupes += 1
                continue
            merged[a["id"]] = a

    articles = list(merged.values())

    # Validate against the real Pydantic model so fixtures can't drift from the schema.
    validated: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for a in articles:
        try:
            validated.append(NewsArticle(**a).model_dump())
        except Exception as exc:  # noqa: BLE001
            invalid.append({"article": a, "error": str(exc)})

    (OUT_DIR / "demo_articles.json").write_text(
        json.dumps(validated, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    lines = [
        "=" * 78,
        f"DEMO DATA  |  query: {args.query}",
        f"captured : {datetime.now(timezone.utc).isoformat()}",
        f"articles : {len(validated)}",
        "=" * 78,
        "",
    ]
    for i, a in enumerate(validated, 1):
        lines += [
            f"[{i:02d}] {a['title']}",
            f"     provider : {a.get('provider')}",
            f"     source   : {a.get('source')}",
            f"     published: {a.get('published_at')}",
            f"     lang     : {a.get('language')}",
            f"     url      : {a.get('url')}",
            f"     image    : {a.get('image_url') or '(none)'}",
            f"     snippet  : {(a.get('snippet') or '(empty)')[:300]}",
            "",
        ]
    (OUT_DIR / "demo_articles.txt").write_text("\n".join(lines), encoding="utf-8")

    report = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "query": args.query,
        "providers": [{k: v for k, v in r.items() if k != "articles"} for r in results],
        "merged_total": len(validated),
        "duplicates_dropped": dupes,
        "schema_invalid": invalid,
        "field_coverage": field_coverage(validated),
        "on_topic": on_topic_stats(validated),
        "date_format_samples": date_formats(validated),
    }
    (OUT_DIR / "capture_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    ot = report["on_topic"]
    ok = [r for r in results if r["status"] == "ok"]
    print("\n" + "-" * 78)
    print(f'ON-TOPIC (Bhopal/MP): {ot["overall"]}  ({ot["pct"]}%)')
    for prov, frac in ot["per_provider"].items():
        print(f'    {prov:9s} {frac}')
    if ot["off_topic"]:
        print("  off-topic still present:")
        for t in ot["off_topic"]:
            print(f"    - {t}")
    print(f"providers ok       : {len(ok)}/3")
    print(f"merged articles    : {len(validated)}  (dropped {dupes} cross-provider duplicates)")
    if invalid:
        print(f"SCHEMA FAILURES    : {len(invalid)}  <-- see capture_report.json")
    if report["date_format_samples"]:
        print("date formats seen  :")
        for prov, samples in report["date_format_samples"].items():
            print(f"    {prov:9s} {samples}")
    print("-" * 78)
    print(f"wrote -> {OUT_DIR}/")
    for f in sorted(OUT_DIR.iterdir()):
        print(f"    {f.name}  ({f.stat().st_size:,} bytes)")

    failed = [r for r in results if r["status"] in {"http_error", "error"}]
    if failed:
        print("\nFAILURES:")
        for r in failed:
            print(f"  {r['provider']}: {r['error']}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
