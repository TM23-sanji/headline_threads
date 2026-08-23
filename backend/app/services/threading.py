"""Group articles into story threads via keyword matching.

A thread is a running story ("Bhopal illegal construction") followed across
weeks. Two distinct problems have to be solved:

1. **Continuation** - an article published next week about the same story must
   attach to the existing thread rather than start a new one.

2. **Syndication collapse** - the same development is reported by up to three
   providers within hours. Treating each as a timeline entry makes one event
   look like three developments. Same-day near-identical articles are
   therefore merged into a single *beat*, with the extra articles recorded as
   corroborating sources.

Matching uses keyword overlap plus title similarity. It is deliberately
lexical: Postgres FTS/trigram indexes back it, no external service is
required. Consequence: a Hindi article will not match its English counterpart.
Bridging that needs embeddings, which is why a vector column is reserved.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

# --- tuning -----------------------------------------------------------------
# Overlap needed for an article to join an existing thread.
THREAD_MATCH_THRESHOLD = 0.34
# Above this, two articles describe the same development (not a new one).
BEAT_DUPLICATE_THRESHOLD = 0.55
# Character-level similarity sufficient to call two articles the same development.
TITLE_DUPLICATE_THRESHOLD = 0.72
# Token overlap required to support a keyword-based duplicate decision.
BEAT_TITLE_SUPPORT = 0.34
# How close in time two articles must be to be candidates for the same beat.
BEAT_WINDOW = timedelta(hours=36)
# A thread stops accepting new articles after this much silence.
THREAD_STALE_AFTER = timedelta(days=45)
# Applied when the article's sector differs from the thread's.
SECTOR_MISMATCH_PENALTY = 0.85
# Headline token overlap that on its own justifies considering a match.
MIN_TITLE_OVERLAP = 0.34

_WORD_RE = re.compile(r"[\w\u0900-\u097F]+")


def _norm_keyword(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def keyword_set(keywords: list[str]) -> set[str]:
    """Expand phrases into their component words plus the whole phrase.

    Matching on whole phrases alone is too brittle: "illegal construction
    Bhopal" and "illegal construction drive" share no complete phrase but are
    obviously the same story.
    """
    expanded: set[str] = set()
    for kw in keywords:
        norm = _norm_keyword(kw)
        if not norm:
            continue
        expanded.add(norm)
        words = _WORD_RE.findall(norm)
        if len(words) > 1:
            expanded.update(w for w in words if len(w) > 3)
    return expanded


def overlap_score(a: set[str], b: set[str]) -> tuple[float, list[str]]:
    """Overlap coefficient: |A n B| / min(|A|, |B|).

    Preferred over Jaccard because keyword sets differ greatly in size; Jaccard
    would unfairly penalize a short headline matching a rich one.
    """
    if not a or not b:
        return 0.0, []
    shared = a & b
    return len(shared) / min(len(a), len(b)), sorted(shared)


# Words present in nearly every local headline. They carry no discriminating
# power and must not contribute to similarity.
_UBIQUITOUS = {
    "bhopal", "madhya", "pradesh", "mp", "india", "indian", "news", "update",
    "latest", "report", "reports", "said", "says", "video", "photos", "watch",
    "भोपाल", "मध्य", "प्रदेश", "समाचार", "न्यूज",
}

_TITLE_STOP = _UBIQUITOUS | {
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "with",
    "from", "by", "is", "are", "was", "were", "be", "been", "has", "have",
    "had", "will", "after", "before", "over", "under", "about", "into", "as",
    "its", "it", "this", "that", "than", "then", "who", "new", "amid",
}


def title_tokens(title: str) -> set[str]:
    return {
        t for t in _WORD_RE.findall(title.lower())
        if len(t) > 2 and t not in _TITLE_STOP and not t.isdigit()
    }


def title_similarity(a: str, b: str) -> float:
    """Token-level Jaccard similarity between two headlines.

    Character-level SequenceMatcher was used here originally and caused real
    false merges on live data: it scored entirely unrelated English headlines
    at 0.39-0.43 simply because prose shares characters. Measured examples:

        "Bhopal metro rail project delayed again..."     0.391
        "Bhopal milk procurement rises 38%..."

    Comparing content tokens instead makes unrelated headlines score ~0.
    """
    ta, tb = title_tokens(a), title_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def char_similarity(a: str, b: str) -> float:
    """Character-level ratio. Only meaningful for near-identical headlines,
    so it is reserved for same-day duplicate detection."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _distinctive_overlap(a: set[str], b: set[str]) -> tuple[int, int]:
    """Count shared multi-word phrases and shared distinctive single words."""
    shared = a & b
    phrases = sum(1 for s in shared if " " in s)
    words = sum(1 for s in shared if " " not in s and s not in _UBIQUITOUS)
    return phrases, words


def make_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def slugify(title: str) -> str:
    slug = re.sub(r"[^\w\s\u0900-\u097F-]", "", title.lower())
    slug = re.sub(r"[\s_]+", "-", slug).strip("-")
    return slug[:80] or "thread"


@dataclass
class ThreadCandidate:
    """Lightweight view of a thread, for matching without loading the ORM."""

    id: str
    title: str
    sector: str
    keywords: list[str]
    last_seen: datetime
    keyword_index: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not self.keyword_index:
            self.keyword_index = keyword_set(self.keywords)


@dataclass
class MatchResult:
    thread_id: str | None
    score: float
    matched_keywords: list[str]
    is_new_thread: bool


def match_thread(
    *,
    title: str,
    keywords: list[str],
    sector: str,
    published_at: datetime,
    candidates: list[ThreadCandidate],
    threshold: float = THREAD_MATCH_THRESHOLD,
) -> MatchResult:
    """Find the best existing thread for an article, if any."""
    article_keys = keyword_set(keywords)
    if not article_keys:
        return MatchResult(None, 0.0, [], True)

    best: tuple[float, ThreadCandidate | None, list[str]] = (0.0, None, [])

    for cand in candidates:
        if published_at - cand.last_seen > THREAD_STALE_AFTER:
            continue

        score, shared = overlap_score(article_keys, cand.keyword_index)
        phrases, words = _distinctive_overlap(article_keys, cand.keyword_index)
        tsim = title_similarity(title, cand.title)

        # A shared topic must be demonstrated, not inferred from fuzzy string
        # resemblance. Require either a shared multi-word phrase, two shared
        # distinctive words, or substantial headline token overlap.
        if phrases < 1 and words < 2 and tsim < MIN_TITLE_OVERLAP:
            continue

        # Headline overlap supports the keyword score but cannot replace it.
        score = max(score, tsim)

        # Sector is a soft signal, not a gate. The classifier legitimately
        # drifts across related sectors as a story develops - an illegal
        # construction story moves between "bmc_civic" and "construction" -
        # so a mismatch is penalized rather than excluded.
        if cand.sector != sector and "other" not in (cand.sector, sector):
            score *= SECTOR_MISMATCH_PENALTY

        if score > best[0]:
            best = (score, cand, shared)

    score, cand, shared = best
    if cand is not None and score >= threshold:
        return MatchResult(cand.id, round(score, 4), shared, False)

    return MatchResult(None, round(score, 4), shared, True)


@dataclass
class BeatCandidate:
    id: str
    headline: str
    occurred_at: datetime
    keywords: list[str]
    keyword_index: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not self.keyword_index:
            self.keyword_index = keyword_set(self.keywords)


def find_duplicate_beat(
    *,
    title: str,
    keywords: list[str],
    published_at: datetime,
    beats: list[BeatCandidate],
) -> BeatCandidate | None:
    """Return an existing beat describing the same development, if any.

    This is what stops three providers reporting one event from rendering as
    three separate developments in the timeline.
    """
    article_keys = keyword_set(keywords)

    for beat in beats:
        if abs(published_at - beat.occurred_at) > BEAT_WINDOW:
            continue

        # Syndicated copies are near-identical, so character-level similarity
        # is appropriate here (unlike thread matching, where it over-matches).
        if char_similarity(title, beat.headline) >= TITLE_DUPLICATE_THRESHOLD:
            return beat

        tsim = title_similarity(title, beat.headline)
        score, _ = overlap_score(article_keys, beat.keyword_index)
        if score >= BEAT_DUPLICATE_THRESHOLD and tsim >= BEAT_TITLE_SUPPORT:
            return beat

    return None


# Ordered by how much attention a status deserves when summarizing a thread.
_STATUS_PRIORITY = ["delayed", "stalled", "ongoing", "planned", "completed", "unknown"]


def resolve_thread_status(beat_statuses: list[str]) -> str:
    """Current status of a thread, given its beats oldest-first.

    The newest meaningful status wins. Only when recent beats are all
    `unknown` do we fall back to the most notable status among them.
    """
    if not beat_statuses:
        return "unknown"

    for status in reversed(beat_statuses):
        if status != "unknown":
            return status

    recent = beat_statuses[-5:]
    for status in _STATUS_PRIORITY:
        if status in recent:
            return status
    return "unknown"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
