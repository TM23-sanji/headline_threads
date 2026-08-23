"""Cross-provider normalization.

The three providers disagree on nearly every shared field. Measured on live
captures:

  dates     newsdata "2026-08-22 19:30:00" (space, no tz, UTC per pubDateTZ)
            gnews    "2026-08-22T20:01:00Z"
            newsapi  "2026-08-22T07:10:36Z"
  language  newsdata "english"/"hindi"   gnews/newsapi "en"
  source    "The Times of India" / "Times of India" / "The Times Of India"

Everything is normalized here, before persistence. Storing un-normalized rows
is unrecoverable in practice: the providers give no deep backfill, so the
database is the only archive we will ever have.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",       # newsdata
    "%Y-%m-%dT%H:%M:%SZ",      # gnews / newsapi
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)


def parse_published_at(value: str | None) -> datetime | None:
    """Parse a provider date string into a timezone-aware UTC datetime.

    Providers that omit a timezone (newsdata) document their timestamps as UTC
    via the pubDateTZ field, so naive values are treated as UTC.
    """
    if not value:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    # Python <3.11 cannot parse a trailing "Z" via fromisoformat.
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        parsed = None

    if parsed is None:
        for fmt in _DATE_FORMATS:
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue

    if parsed is None:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


# --------------------------------------------------------------------------
# Language
# --------------------------------------------------------------------------

_LANGUAGE_MAP = {
    "english": "en",
    "en": "en",
    "eng": "en",
    "hindi": "hi",
    "hi": "hi",
    "hin": "hi",
    "marathi": "mr",
    "mr": "mr",
    "urdu": "ur",
    "ur": "ur",
    "gujarati": "gu",
    "tamil": "ta",
    "telugu": "te",
    "bengali": "bn",
    "punjabi": "pa",
}

_DEVANAGARI = re.compile(r"[\u0900-\u097F]")


def normalize_language(value: str | None, *, text: str = "") -> str:
    """Map a provider language label to an ISO-639-1 code.

    Falls back to script detection: NewsAPI hardcodes "en" for everything, so a
    Devanagari headline from that provider would otherwise be mislabelled and
    break the Hindi/English filter.
    """
    code = _LANGUAGE_MAP.get((value or "").strip().lower())

    if text and _DEVANAGARI.search(text):
        return "hi"

    return code or "unknown"


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------

_SOURCE_PREFIXES = ("the ",)
# Only domain suffixes are stripped. Words like "News"/"Digital" are part of
# legitimate outlet names here ("Bansal News", "INH News", "Khabar Digital"),
# and removing them mangles distinct publishers into unrecognizable stubs.
_SOURCE_SUFFIXES = (".co.in", ".com", ".in", ".org", ".net")

# Distinct outlets that repeatedly arrive under several spellings.
_SOURCE_ALIASES = {
    "times of india": "Times of India",
    "timesofindia": "Times of India",
    "times of india - epaper": "Times of India",
    "economic times": "The Economic Times",
    "economictimes": "The Economic Times",
    "free press journal": "Free Press Journal",
    "freepressjournal": "Free Press Journal",
    "hindustan times": "Hindustan Times",
    "hindustantimes": "Hindustan Times",
    "ndtv": "NDTV",
    "news18": "News18",
    "dainik bhaskar": "Dainik Bhaskar",
    "bhaskar": "Dainik Bhaskar",
    "naidunia": "Naidunia",
    "patrika": "Patrika",
    "amar ujala": "Amar Ujala",
    "jagran": "Dainik Jagran",
    "dainik jagran": "Dainik Jagran",
    "lokmat times": "Lokmat Times",
    "hans india": "The Hans India",
    "business standard": "Business Standard",
    "businessline": "BusinessLine",
    "etv bharat": "ETV Bharat",
    "latestly": "LatestLY",
    "inh news": "INH News",
    "bansal news": "Bansal News",
    "khabar digital": "Khabar Digital",
    "bhopal samachar": "Bhopal Samachar",
    "udaipur kiran": "Udaipur Kiran",
    "livemint": "Livemint",
    "mint": "Livemint",
}


def _source_key(name: str) -> str:
    """Aggressively fold a display name down to a comparison key."""
    key = unicodedata.normalize("NFKD", name).lower().strip()
    key = re.sub(r"[^\w\s.]", " ", key)
    key = re.sub(r"\s+", " ", key).strip()

    for suffix in _SOURCE_SUFFIXES:
        if key.endswith(suffix):
            key = key[: -len(suffix)].strip()

    for prefix in _SOURCE_PREFIXES:
        if key.startswith(prefix):
            key = key[len(prefix) :].strip()

    return key


def canonicalize_source(name: str | None) -> str:
    """Collapse spelling variants of the same outlet into one label.

    "The Times of India", "Times of India" and "The Times Of India" all appear
    in a single capture; without this a source filter fragments one publisher
    into three buckets.
    """
    if not name or not name.strip():
        return "Unknown"

    key = _source_key(name)
    if key in _SOURCE_ALIASES:
        return _SOURCE_ALIASES[key]

    # Unknown outlet: title-case the folded key so variants still converge.
    return " ".join(word.capitalize() for word in key.split()) or "Unknown"


# --------------------------------------------------------------------------
# Provider keywords
# --------------------------------------------------------------------------

# NewsData mixes genuine entities with generic section tags. The tags carry no
# information for threading and would match unrelated stories.
_GENERIC_KEYWORDS = {
    "news", "topnews", "top news", "top stories", "latest news", "breaking news",
    "national", "state", "india", "india news", "today newspaper", "newspaper",
    "bhopal news", "madhya pradesh news", "mp news", "city news", "local news",
    "top", "general", "other", "headlines", "trending",
}


def clean_provider_keywords(values: list[str] | None) -> list[str]:
    """Drop generic section tags from provider-supplied keywords."""
    if not values:
        return []

    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        kw = re.sub(r"\s+", " ", str(value).lower()).strip()
        if not kw or len(kw) < 3:
            continue
        if kw in _GENERIC_KEYWORDS or kw in seen:
            continue
        seen.add(kw)
        cleaned.append(kw)

    return cleaned


# --------------------------------------------------------------------------
# URLs
# --------------------------------------------------------------------------

_TRACKING_PARAMS = re.compile(
    r"^(utm_|fbclid|gclid|igshid|mc_cid|mc_eid|ref|source|amp)", re.IGNORECASE
)


def url_key(url: str) -> str:
    """Normalize a URL for duplicate detection.

    The same article is syndicated with differing tracking parameters, schemes
    and www prefixes; sha256(title|url) alone therefore fails to dedupe it.
    """
    from urllib.parse import urlsplit, urlunsplit

    if not url:
        return ""

    parts = urlsplit(url.strip().lower())
    netloc = parts.netloc.removeprefix("www.")
    path = parts.path.rstrip("/")
    query = "&".join(
        pair
        for pair in sorted(parts.query.split("&"))
        if pair and not _TRACKING_PARAMS.match(pair.split("=", 1)[0])
    )
    return urlunsplit(("", netloc, path, query, ""))


# --------------------------------------------------------------------------
# Term matching
# --------------------------------------------------------------------------

_DEVANAGARI_ONLY = re.compile(r"^[\u0900-\u097F\s]+$")
_TERM_CACHE: dict[str, re.Pattern[str]] = {}


def term_pattern(term: str) -> re.Pattern[str]:
    """Compile a boundary-aware pattern for a keyword term.

    Naive substring matching produced real misclassifications on live Hindi
    articles:

        "पुल"  (bridge)    matched inside "पुलिस"  (police)
        "पूर"  (complete)  matched inside "पूरे"   (entire)

    Devanagari terms are therefore matched as whole words. Latin terms keep
    prefix matching, so "construct" still matches "construction", but a
    leading word boundary prevents "road" matching "broad".
    """
    cached = _TERM_CACHE.get(term)
    if cached is not None:
        return cached

    escaped = re.escape(term)
    if _DEVANAGARI_ONLY.match(term):
        # Whole word: no Devanagari letter or matra may follow.
        pattern = re.compile(rf"(?<![\u0900-\u097F]){escaped}(?![\u0900-\u097F])")
    else:
        pattern = re.compile(rf"\b{escaped}", re.IGNORECASE)

    _TERM_CACHE[term] = pattern
    return pattern


def contains_term(text: str, term: str) -> bool:
    return bool(term_pattern(term).search(text))


def count_terms(text: str, terms: list[str]) -> tuple[int, list[str]]:
    """Count how many of `terms` occur in `text`, returning the matches."""
    matched = [t for t in terms if contains_term(text, t)]
    return len(matched), matched


def clean_content_stub(value: str | None) -> str | None:
    """Return usable content text, or None for paywalled/truncation markers.

    NewsData returns the literal string "ONLY AVAILABLE IN PAID PLANS" on the
    free tier; GNews and NewsAPI truncate to ~200-265 chars with a "[+N chars]"
    marker.
    """
    if not value:
        return None

    text = str(value).strip()
    if not text or "ONLY AVAILABLE IN" in text.upper():
        return None

    return re.sub(r"\s*\[\+\d+\s*chars\]\s*$", "", text).strip() or None
