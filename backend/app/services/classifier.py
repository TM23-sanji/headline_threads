import re

from app.models import ClassifiedArticle, NewsArticle, Sector
from app.services.normalize import count_terms

# NewsData's free-tier IPTC categories, mapped onto our sectors. Used only as
# a fallback when local keyword scoring yields nothing.
PROVIDER_CATEGORY_MAP: dict[str, Sector] = {
    "crime": "crime",
    "politics": "politics",
    "health": "health",
    "environment": "environment",
    "science": "environment",
    "business": "other",
    "sports": "other",
    "entertainment": "other",
    "lifestyle": "other",
    "technology": "other",
    "world": "other",
    "top": "other",
    "domestic": "other",
    "education": "other",
    "tourism": "other",
    "food": "other",
}


def _from_provider_category(categories: list[str]) -> Sector | None:
    for raw in categories:
        mapped = PROVIDER_CATEGORY_MAP.get(str(raw).strip().lower())
        if mapped and mapped != "other":
            return mapped
    return None

SECTOR_KEYWORDS: dict[Sector, list[str]] = {
    "construction": [
        "bridge",
        "flyover",
        "overbridge",
        "construction",
        "nirman",
        "nirmaan",
        "pwd",
        "corridor",
        "culvert",
        "station",
        "पुल",
        "फ्लाईओवर",
        "निर्माण",
        "कॉरिडोर",
    ],
    "roads": ["road", "pothole", "gaddha", "gaddhe", "sadak", "सड़क", "गड्ढ", "repair", "patch"],
    "transport": ["bus", "e-bus", "metro", "train", "railway", "traffic", "ट्रैफिक", "रेल"],
    "water_lakes": ["lake", "talaab", "narmada", "river", "flood", "barish", "rain", "तालाब", "बाढ़"],
    "bmc_civic": ["bmc", "nigam", "municipal", "sealing", "civic", "निगम", "seal"],
    "health": ["hospital", "swine flu", "doctor", "patient", "health", "अस्पताल", "flu"],
    "crime": ["murder", "robbery", "theft", "police", "crime", "हत्या", "लूट"],
    "politics": ["minister", "bjp", "congress", "cm", "mla", "vidhan", "मंत्री", "सरकार"],
    "environment": ["pollution", "hyacinth", "environment", "green", "प्रदूषण"],
}


def _score_sector(text: str) -> tuple[Sector, float, str | None, str | None, list[str]]:
    """Score sectors using boundary-aware term matching.

    Substring matching previously filed Hindi crime stories under
    construction, because "पुल" (bridge) occurs inside "पुलिस" (police).
    """
    lowered = text.lower()
    best_sector: Sector = "other"
    best_score = 0
    best_matches: list[str] = []

    for sector, keywords in SECTOR_KEYWORDS.items():
        score, matched = count_terms(lowered, keywords)
        if score > best_score:
            best_sector = sector
            best_score = score
            best_matches = matched

    confidence = min(best_score / 3, 1.0) if best_score else 0.2

    subtopic = None
    status = None
    if best_sector == "construction":
        if re.search(r"delay|slow|late|deeri|धीमी|धीरे|अधूरा|अधूरी", lowered):
            subtopic = "delay"
            status = "delayed"
        elif re.search(r"pothole|damage|fail|quality|टूटा|टूटी|टूट\b", lowered):
            subtopic = "quality_issue"
            status = "poor_quality"

    return best_sector, confidence, subtopic, status, best_matches


def classify_article(article: NewsArticle) -> ClassifiedArticle:
    text = f"{article.title} {article.snippet}"
    sector, confidence, subtopic, status, matched = _score_sector(text)

    # NewsData supplies IPTC categories on the free tier; use them as a
    # tie-break when our own keyword scoring found nothing.
    if sector == "other" and article.provider_category:
        mapped = _from_provider_category(article.provider_category)
        if mapped:
            sector = mapped
            confidence = max(confidence, 0.4)

    summary = article.snippet[:180] if article.snippet else article.title[:180]

    return ClassifiedArticle(
        **article.model_dump(),
        sector=sector,
        subtopic=subtopic,
        status=status,
        confidence=confidence,
        keep=sector != "other",
        summary=summary,
        matched_keywords=matched,
    )


def classify_articles(articles: list[NewsArticle], sector: Sector | None = None) -> list[ClassifiedArticle]:
    classified = [classify_article(article) for article in articles]
    if sector is None:
        return classified
    return [article for article in classified if article.sector == sector]
