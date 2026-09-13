"""Deterministic organization of items into companies and topics (non-AI).

Two independent axes, both rule-based and explainable:

- company: the entity a page belongs to. Prefers a declared brand
  (``og:site_name`` / ``application-name``); otherwise the registrable domain,
  cleaned into a human label (``bbc.co.uk`` -> ``Bbc``).
- topic: a bounded, keyword-scored subject bucket (technology, health, ...).

These feed per-company / per-topic Discord channels and the search API filters.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .crawler.discovery import registrable_domain

# Bounded topic taxonomy -> lowercase keyword markers (word-ish match).
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "ai-ml": ["artificial intelligence", "machine learning", "neural network",
              "deep learning", "llm", "gpt", "transformer model", "chatbot", "openai"],
    "security-cyber": ["cybersecurity", "vulnerability", "malware", "ransomware",
                       "data breach", "exploit", "phishing", "zero-day", "cve",
                       "threat actor", "encryption"],
    "crypto-web3": ["bitcoin", "ethereum", "blockchain", "crypto", "web3", "nft",
                    "defi", "stablecoin", "token", "wallet"],
    "technology": ["software", "hardware", "startup", "app", "developer", "cloud",
                   "api", "programming", "open source", "gadget", "semiconductor"],
    "business-finance": ["earnings", "revenue", "market", "stock", "investor",
                         "acquisition", "ipo", "economy", "inflation", "trade",
                         "company announced", "quarterly"],
    "politics-government": ["election", "senate", "congress", "parliament",
                            "government", "policy", "president", "minister",
                            "legislation", "campaign", "diplomacy"],
    "health-medicine": ["health", "disease", "vaccine", "hospital", "patient",
                        "clinical", "medicine", "outbreak", "mental health",
                        "diagnosis", "treatment"],
    "science": ["research", "study", "scientists", "physics", "biology",
                "chemistry", "space", "nasa", "experiment", "discovery", "climate model"],
    "environment-climate": ["climate change", "emissions", "renewable", "wildfire",
                            "pollution", "biodiversity", "sustainability", "carbon"],
    "sports": ["match", "tournament", "league", "championship", "player", "coach",
               "olympic", "score", "football", "soccer", "basketball", "cricket"],
    "entertainment": ["film", "movie", "music", "album", "celebrity", "box office",
                      "streaming", "series", "trailer", "concert"],
    "gaming": ["video game", "gaming", "esports", "console", "playstation", "xbox",
               "nintendo", "steam", "gameplay"],
    "education": ["university", "student", "school", "course", "curriculum",
                  "scholarship", "tuition", "professor", "academic"],
    "law-legal": ["lawsuit", "court", "ruling", "judge", "verdict", "attorney",
                  "legal", "settlement", "indictment", "appeal"],
    "world-news": ["war", "conflict", "border", "refugee", "united nations",
                   "sanctions", "ceasefire", "protest", "humanitarian"],
    "jobs-careers": ["hiring", "job", "career", "layoff", "workforce", "recruit",
                     "salary", "employment", "vacancy"],
    "real-estate": ["real estate", "housing", "mortgage", "property", "rent",
                    "landlord", "homebuyer"],
    "travel": ["travel", "airline", "flight", "tourism", "hotel", "destination",
               "visa", "passport"],
    "food": ["recipe", "restaurant", "cuisine", "chef", "cooking", "food safety"],
    "culture-religion": ["culture", "religion", "church", "festival", "tradition",
                         "heritage", "art exhibition"],
}

DEFAULT_TOPIC = "general"

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 90) -> str:
    """Discord-safe channel slug (lowercase, hyphen-separated)."""
    s = _SLUG_RE.sub("-", (text or "").lower()).strip("-")
    return (s or "misc")[:max_len]


def company_for(url: str, meta: dict | None = None) -> str:
    """Human-readable company/entity label for a page."""
    meta = meta or {}
    for key in ("og:site_name", "application-name", "al:android:app_name",
                "twitter:site"):
        val = (meta.get(key) or "").strip().lstrip("@")
        if val and len(val) <= 60:
            return val
    host = urlparse(url).netloc or url
    base = registrable_domain(host)
    label = base.split(".")[0] if base else host
    return label.replace("-", " ").title() or host


def topic_for(title: str | None, text: str | None,
              meta: dict | None = None) -> tuple[str, list[str]]:
    """Return (topic, matched_keywords). Deterministic keyword scoring."""
    meta = meta or {}
    # weight the title + declared keywords/description more heavily than body
    strong = " ".join([
        title or "",
        meta.get("keywords", ""),
        meta.get("description", ""),
        meta.get("og:title", ""),
    ]).lower()
    body = (text or "").lower()

    best_topic = DEFAULT_TOPIC
    best_score = 0.0
    best_hits: list[str] = []
    for topic, markers in TOPIC_KEYWORDS.items():
        hits = []
        score = 0.0
        for kw in markers:
            in_strong = kw in strong
            in_body = kw in body
            if in_strong:
                score += 3.0
                hits.append(kw)
            elif in_body:
                score += 1.0
                hits.append(kw)
        if score > best_score:
            best_score = score
            best_topic = topic
            best_hits = hits
    return best_topic, best_hits
