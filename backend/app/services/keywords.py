import re
import uuid
from datetime import datetime, timezone

from app.models import ProgressStatus, Sector, TrackEventRequest
from app.models import NewsArticle
from app.services.classifier import classify_article
from app.services.normalize import contains_term

STOP_WORDS = {
    "the",
    "a",
    "an",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "and",
    "or",
    "with",
    "from",
    "by",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "has",
    "have",
    "had",
    "will",
    "after",
    "before",
    "over",
    "under",
    "about",
    "into",
    "during",
    "latest",
    "news",
    "update",
    "report",
    "reports",
    "said",
    "says",
    "amid",
    "across",
    "mp",
    "bhopal",
    "madhya",
    "pradesh",
    "के",
    "में",
    "से",
    "पर",
    "की",
    "का",
    "को",
    "और",
    "या",
    "है",
    "था",
    "थी",
    "थे",
    "एक",
    "यह",
    "वह",
    "तो",
    "भी",
    "ही",
    "लिए",
    "साथ",
    "बाद",
    "पहले",
    "न्यूज",
    "समाचार",
    "ताजा",
}

PROJECT_TERMS = [
    "bridge",
    "flyover",
    "overbridge",
    "elevated",
    "corridor",
    "metro",
    "road",
    "station",
    "hospital",
    "lake",
    "nigam",
    "bmc",
    "pwd",
    "project",
    "construction",
    "पुल",
    "फ्लाईओवर",
    "ओवरब्रिज",
    "सड़क",
    "निर्माण",
    "कॉरिडोर",
    "स्टेशन",
    "निगम",
]

LOCATION_HINTS = [
    "sant hirdaram",
    "bairagarh",
    "prabhat",
    "ambedkar",
    "narmada",
    "kolar",
    "arera",
    "narmadapuram",
    "संत हिरदाराम",
    "बैरागढ़",
    "प्रभात",
    "अंबेडकर",
    "नर्मदा",
    "कोलार",
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _tokenize(text: str) -> list[str]:
    cleaned = re.sub(r"[^\w\s\-]", " ", text.lower())
    return [token for token in cleaned.split() if len(token) > 2 and token not in STOP_WORDS]


# Words that may survive stopword filtering but cannot anchor a keyword.
# The previous implementation accepted any bigram longer than 8 characters,
# which admitted grammatical fragments like "away while" and "while crossing"
# and made tracking queries retrieve noise.
WEAK_WORDS = {
    "while", "away", "back", "down", "out", "off", "up", "then", "than",
    "when", "where", "which", "who", "whom", "whose", "what", "why", "how",
    "many", "much", "more", "most", "some", "any", "all", "both", "each",
    "other", "another", "such", "own", "same", "very", "just", "only",
    "also", "even", "still", "yet", "here", "there", "now", "today",
    "yesterday", "tomorrow", "again", "once", "ever", "never", "always",
    "may", "might", "must", "should", "would", "could", "can", "shall",
    "get", "got", "getting", "make", "made", "making", "take", "taken",
    "taking", "give", "given", "put", "keep", "kept", "goes", "going",
    "gone", "came", "come", "coming", "seen", "saw", "look", "looking",
    "including", "amongst", "among", "between", "against", "through",
    "without", "within", "along", "around", "behind", "beyond", "despite",
    "toward", "towards", "upon", "via", "per", "due", "next", "last",
    "first", "second", "third", "new", "old", "big", "small", "high", "low",
}

_NUMERIC_ONLY = re.compile(r"^[\d\W_]+$")
MAX_PHRASE_WORDS = 4


def _is_weak(token: str) -> bool:
    return token in WEAK_WORDS or len(token) <= 2 or bool(_NUMERIC_ONLY.match(token))


def _title_entities(title: str) -> list[str]:
    """Capitalized multi-word runs from the original headline.

    Case is preserved before lowercasing elsewhere, so proper nouns such as
    "Sant Hirdaram Nagar" or "Prabhat Square" can be recovered. Headlines that
    are entirely uppercase carry no case signal and are skipped.
    """
    if title.isupper():
        return []

    # Headlines in Title Case capitalize nearly every word, so a greedy run
    # swallows the whole headline ("evidence seized as accused move judicial
    # custody"). Detect that and fall back to shorter windows.
    words = [w for w in re.findall(r"[A-Za-z']+", title) if len(w) > 2]
    capitalized = sum(1 for w in words if w[0].isupper())
    title_case = bool(words) and capitalized / len(words) > 0.7

    entities: list[str] = []
    for match in re.finditer(r"\b([A-Z][a-z\u0900-\u097F]+(?:\s+[A-Z][a-z\u0900-\u097F]+)*)", title):
        tokens = [t for t in match.group(1).lower().split() if t not in STOP_WORDS]
        tokens = [t for t in tokens if not _is_weak(t)]
        if len(tokens) < 2:
            continue

        if title_case or len(tokens) > MAX_PHRASE_WORDS:
            # Emit a few non-overlapping 3-word windows rather than every
            # sliding window; overlapping variants are redundant and inflate
            # keyword-overlap scores during thread matching.
            for i in range(0, len(tokens) - 1, 3):
                window = tokens[i : i + 3]
                if len(window) >= 2:
                    entities.append(" ".join(window))
        else:
            entities.append(" ".join(tokens))

    return entities


# Hindi verbs, auxiliaries and generic nouns. Without these, sliding bigrams
# produce fragments like "रोटी खाने" ("eating roti") and "खाने तीन".
HINDI_WEAK = {
    "खाने", "खाना", "रहे", "रही", "रहा", "बनाया", "बनाई", "करेंगे", "करने",
    "करते", "करती", "करता", "किया", "किए", "कहा", "कहना", "हुआ", "हुई", "हुए",
    "गया", "गए", "गई", "दिया", "दी", "दिए", "लिया", "ली", "होगा", "होगी",
    "जाएगा", "जाएगी", "आया", "आई", "मिला", "मिली", "देखा", "बताया", "लगा",
    "सकता", "सकती", "चाहिए", "वाले", "वाली", "वाला", "अपने", "अपनी", "इस",
    "उस", "जो", "कि", "तक", "पास", "बीच", "दौरान", "जैसे", "तरह", "बार",
    "समय", "दिन", "साल", "लोग", "लोगों", "मामला", "मामले", "बड़ा", "बड़ी",
}


def _devanagari_phrases(text: str) -> list[str]:
    """Adjacent Devanagari word pairs, for Hindi headlines.

    Hindi has no case signal, so entity detection relies on adjacency of
    content words. Both tokens of a pair must be substantive, otherwise the
    result is a grammatical fragment rather than a topic.
    """
    tokens = [
        t for t in re.findall(r"[\u0900-\u097F]+", text)
        if t not in STOP_WORDS and t not in HINDI_WEAK and len(t) > 2
    ]

    phrases = [
        f"{left} {right}"
        for left, right in zip(tokens, tokens[1:])
        if left not in HINDI_WEAK and right not in HINDI_WEAK
    ]

    # Keep standalone long nouns too; Hindi compounds are often one token.
    phrases.extend(t for t in tokens if len(t) >= 6)
    return phrases[:5]


def _extract_phrases(text: str, title: str = "") -> list[str]:
    """Extract candidate keyword phrases, ordered most- to least-distinctive."""
    lowered = _normalize(text)
    source_title = title or text
    phrases: list[str] = []

    # 1. Known place names - the strongest signal for a local story.
    phrases.extend(hint for hint in LOCATION_HINTS if hint in lowered)

    # 2. Proper nouns from the headline.
    phrases.extend(_title_entities(source_title))

    # 3. Hindi phrases.
    if re.search(r"[\u0900-\u097F]", source_title):
        phrases.extend(_devanagari_phrases(source_title))

    # 4. Bigrams anchored by a project/domain term, both tokens meaningful.
    tokens = _tokenize(text)
    for left, right in zip(tokens, tokens[1:]):
        if _is_weak(left) or _is_weak(right):
            continue
        bigram = f"{left} {right}"
        if any(contains_term(bigram, term) for term in PROJECT_TERMS):
            phrases.append(bigram)

    # 5. Bare project terms, as a fallback anchor. Boundary-aware, so "पुल"
    #    (bridge) is not extracted from "पुलिस" (police).
    phrases.extend(term for term in PROJECT_TERMS if contains_term(lowered, term))

    unique: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        key = re.sub(r"\s+", " ", phrase).strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(key)

    return unique[:8]


def build_keyword_query(keywords: list[str]) -> str:
    """Build a provider query from keywords.

    Only multi-word phrases and distinctive single tokens are used. Bare common
    words would OR-match most of the feed and defeat the purpose of tracking.
    """
    usable = [
        kw for kw in keywords
        if " " in kw or (len(kw) > 5 and kw not in STOP_WORDS and not _is_weak(kw))
    ]
    if not usable:
        usable = [kw for kw in keywords if kw][:2]

    quoted = [f'"{kw}"' if " " in kw else kw for kw in usable[:5]]
    return " OR ".join(quoted)


# Hindi stems must be full words. The previous pattern used the stem "पूर",
# which matched "पूरे" ("entire") and marked unrelated stories as completed.
_STATUS_PATTERNS: list[tuple[ProgressStatus, str]] = [
    ("completed", r"\b(complete|completed|inaugurat\w*|opened|finished)\b|(?<![\u0900-\u097F])(पूरा|पूरी|पूर्ण|उद्घाटन|तैयार)(?![\u0900-\u097F])"),
    ("delayed", r"\b(delay\w*|slow|late|pending|stuck)\b|(?<![\u0900-\u097F])(देरी|धीमी|अधूरा|अधूरी|लंबित)(?![\u0900-\u097F])"),
    ("stalled", r"\b(halt\w*|stopped|stalled|suspend\w*)\b|(?<![\u0900-\u097F])(रोक|ठप|बंद)(?![\u0900-\u097F])"),
    ("planned", r"\b(will start|to begin|launch\w*|approval|approved|sanction\w*|proposed)\b|(?<![\u0900-\u097F])(शुरू|मंजूरी|प्रस्तावित|स्वीकृत)(?![\u0900-\u097F])"),
    ("ongoing", r"\b(underway|in progress|ongoing|construction|repair\w*|building)\b|(?<![\u0900-\u097F])(निर्माण|चल रहा|जारी)(?![\u0900-\u097F])"),
]


# Unambiguous evidence that something actually finished.
_STRONG_COMPLETION = re.compile(
    r"\b(inaugurat\w+|has been completed|have been completed|was completed|"
    r"were completed|now complete|opened to (the )?public|thrown open)\b"
    r"|(?<![\u0900-\u097F])(उद्घाटन|लोकार्पण)(?![\u0900-\u097F])"
)

# Future or conditional framing. "will begin once civil work is complete"
# describes work that has NOT finished, but contains the word "complete".
_FUTURE_MARKER = re.compile(
    r"\b(will (begin|start|be|resume)|to (begin|start|be built|be completed)|"
    r"expected to|yet to|due to (begin|start)|once .{0,40}(complete|finish)|"
    r"after .{0,30}completion|awaiting|proposed|slated|set to)\b"
    r"|(?<![\u0900-\u097F])(प्रस्तावित|जल्द|होगा|होगी)(?![\u0900-\u097F])"
)


def infer_progress_status(text: str) -> ProgressStatus:
    """Infer project progress from ~300-500 chars of headline + description.

    Detail is usually absent at this length, so `unknown` is a common and
    honest outcome; it must not be replaced with a guess.
    """
    lowered = _normalize(text)

    # Completion words frequently appear inside forward-looking clauses, so
    # require unambiguous evidence before declaring something finished.
    if _STRONG_COMPLETION.search(lowered):
        return "completed"

    future = _FUTURE_MARKER.search(lowered)

    for status, pattern in _STATUS_PATTERNS:
        if not re.search(pattern, lowered):
            continue
        if status == "completed" and future:
            # Word appears, but the framing is forward-looking.
            continue
        return status

    return "planned" if future else "unknown"


def generate_keywords(
    title: str,
    snippet: str = "",
    provider_keywords: list[str] | None = None,
) -> tuple[list[str], Sector, ProgressStatus]:
    """Generate keywords for an article.

    Provider-supplied keywords (NewsData returns entity-rich ones on the free
    tier) are trusted first, then topped up with locally extracted phrases.
    Only two of the three providers supply none, so the heuristic still carries
    most of the load.
    """
    text = f"{title} {snippet}".strip()
    classified = classify_article(
        NewsArticle(
            id="kw",
            title=title,
            snippet=snippet,
            url="",
            source="",
        )
    )

    keywords: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        key = re.sub(r"\s+", " ", candidate.lower()).strip()
        if not key or key in seen or key in STOP_WORDS:
            return
        if " " not in key and _is_weak(key):
            return
        seen.add(key)
        keywords.append(key)

    for candidate in provider_keywords or []:
        add(candidate)

    for phrase in _extract_phrases(text, title=title):
        add(phrase)

    # Last resort: distinctive single tokens, so an article is never keywordless.
    if len(keywords) < 3:
        for token in _tokenize(text):
            if not _is_weak(token):
                add(token)
            if len(keywords) >= 3:
                break

    if not keywords:
        add(title[:40])

    status = infer_progress_status(text)
    if classified.status == "delayed":
        status = "delayed"

    return keywords[:8], classified.sector, status


def prepare_track_request(payload: TrackEventRequest) -> tuple[list[str], Sector, ProgressStatus, str]:
    if payload.keywords:
        keywords = payload.keywords[:8]
        sector = payload.sector or "other"
        status = infer_progress_status(f"{payload.title} {payload.snippet}")
    else:
        keywords, sector, status = generate_keywords(payload.title, payload.snippet)
        if payload.sector:
            sector = payload.sector

    if payload.location.lower() not in " ".join(keywords).lower():
        keywords = [payload.location, *keywords][:8]

    return keywords, sector, status, build_keyword_query(keywords)


def score_article_match(text: str, keywords: list[str]) -> tuple[float, list[str]]:
    lowered = _normalize(text)
    matched = [kw for kw in keywords if _normalize(kw) in lowered]
    if not keywords:
        return 0.0, []
    score = len(matched) / len(keywords)
    return score, matched


def new_timeline_entry(article: NewsArticle, keywords: list[str], score: float, matched: list[str]) -> dict:
    status = infer_progress_status(f"{article.title} {article.snippet}")
    return {
        "id": str(uuid.uuid4())[:12],
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "article_id": article.id,
        "title": article.title,
        "snippet": article.snippet,
        "url": article.url,
        "source": article.source,
        "published_at": article.published_at,
        "inferred_status": status,
        "match_score": round(score, 3),
        "matched_keywords": matched,
    }


def aggregate_progress(timeline: list[dict]) -> ProgressStatus:
    if not timeline:
        return "unknown"

    ordered = sorted(timeline, key=lambda item: item.get("captured_at", ""), reverse=True)
    latest = ordered[0].get("inferred_status", "unknown")
    if latest != "unknown":
        return latest

    statuses = [entry.get("inferred_status", "unknown") for entry in ordered[:5]]
    for candidate in ("delayed", "stalled", "ongoing", "planned", "completed"):
        if candidate in statuses:
            return candidate
    return "unknown"
