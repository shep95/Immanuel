"""Deterministic 5-category epistemic classifier.

Classifies the *nature of a publicly-obtained claim* along two axes plus a
conspiracy flag, yielding one of:

    public_fact · public_rumor · private_fact · private_rumor · conspiracy

IMPORTANT (safety + spec alignment): Immanuel only ever acquires *public,
lawfully accessible* content. The "private" labels do NOT mean the system
fetched private data or bypassed any access control — they describe the
*subject matter / claim type* of publicly published text (e.g., a publicly
posted article that concerns a private/personal matter, or an "insider leak"
story). This is an epistemic label on public content, nothing more.

The classifier is fully deterministic and rule-based (no AI). It returns a
label, a confidence in [0,1], and the exact signals that fired, so every
decision is explainable and testable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# --- lexicons ---------------------------------------------------------------

# Language expressing certainty / official confirmation -> "fact" leaning.
FACT_MARKERS = [
    "confirmed", "official", "officially", "announced", "verified",
    "according to data", "study finds", "study shows", "research shows",
    "peer-reviewed", "court ruled", "ruling", "published in", "filing",
    "statement said", "press release", "documented", "evidence shows",
    "data shows", "report confirms", "on the record",
]

# Language expressing uncertainty / hearsay -> "rumor" leaning.
RUMOR_MARKERS = [
    "allegedly", "reportedly", "rumor", "rumour", "rumored", "unconfirmed",
    "sources say", "sources claim", "insider says", "anonymous source",
    "speculation", "speculated", "could be", "might be", "may have",
    "is said to", "claims without evidence", "we hear", "word is",
    "leaked", "purportedly", "supposedly", "hints at",
]

# Subject matter that is public / institutional -> "public" leaning.
PUBLIC_MARKERS = [
    "government", "parliament", "congress", "senate", "ministry", "agency",
    "public", "election", "policy", "law", "regulation", "company announced",
    "sec filing", "earnings", "market", "weather", "science", "university",
    "open dataset", "press conference", "public record", "gdp", "census",
]

# Subject matter that is private / personal -> "private" leaning.
PRIVATE_MARKERS = [
    "private", "personal life", "relationship", "divorce", "affair",
    "home address", "phone number", "medical record", "diagnosis",
    "salary of", "net worth of", "family of", "dating", "breakup",
    "leaked dm", "leaked messages", "insider", "behind closed doors",
    "off the record", "confidential", "internal memo",
]

# Conspiracy-theory markers -> "conspiracy" overrides the 2x2 grid.
CONSPIRACY_MARKERS = [
    "cover-up", "coverup", "cover up", "they don't want you to know",
    "wake up sheeple", "false flag", "deep state", "new world order",
    "secret cabal", "shadow government", "controlled by", "hoax",
    "crisis actor", "chemtrails", "flat earth", "the truth they hide",
    "globalist plot", "mind control", "staged", "plandemic", "microchip",
    "illuminati", "lizard people", "great reset conspiracy",
]

CATEGORIES = (
    "public_fact",
    "public_rumor",
    "private_fact",
    "private_rumor",
    "conspiracy",
)

DISPLAY = {
    "public_fact": "public-facts",
    "public_rumor": "public-rumors",
    "private_fact": "private-facts",
    "private_rumor": "private-rumors",
    "conspiracy": "conspiracies",
    "unknown": "unknown",
}


@dataclass
class Classification:
    category: str
    confidence: float
    signals: list[str]
    epistemic_status: str

    def as_dict(self) -> dict:
        return {
            "category": self.category,
            "category_confidence": round(self.confidence, 3),
            "signals": self.signals,
            "epistemic_status": self.epistemic_status,
        }


def _count_hits(text: str, markers: list[str]) -> list[str]:
    hits = []
    for m in markers:
        # word-ish boundary match, case-insensitive, phrase-safe
        pattern = r"(?<!\w)" + re.escape(m) + r"(?!\w)"
        if re.search(pattern, text):
            hits.append(m)
    return hits


def classify(title: str | None, text: str | None) -> Classification:
    """Classify a document into one of the five categories.

    Deterministic: identical input always yields identical output.
    """
    blob = f"{title or ''}\n{text or ''}".lower()

    if not blob.strip():
        return Classification("unknown", 0.0, [], "unknown")

    conspiracy_hits = _count_hits(blob, CONSPIRACY_MARKERS)
    fact_hits = _count_hits(blob, FACT_MARKERS)
    rumor_hits = _count_hits(blob, RUMOR_MARKERS)
    public_hits = _count_hits(blob, PUBLIC_MARKERS)
    private_hits = _count_hits(blob, PRIVATE_MARKERS)

    signals: list[str] = []
    signals += [f"conspiracy:{h}" for h in conspiracy_hits]
    signals += [f"fact:{h}" for h in fact_hits]
    signals += [f"rumor:{h}" for h in rumor_hits]
    signals += [f"public:{h}" for h in public_hits]
    signals += [f"private:{h}" for h in private_hits]

    # Conspiracy overrides the grid when strongly signalled.
    if len(conspiracy_hits) >= 2 or (
        conspiracy_hits and len(conspiracy_hits) >= len(fact_hits)
    ):
        conf = min(1.0, 0.5 + 0.15 * len(conspiracy_hits))
        return Classification("conspiracy", conf, signals, "hypothesis")

    # Axis 1: fact vs rumor. Default to fact when neither signals (declarative
    # public text is treated as a claimed observation, not a rumor).
    if rumor_hits and len(rumor_hits) > len(fact_hits):
        axis_fr = "rumor"
        fr_strength = len(rumor_hits) - len(fact_hits)
    else:
        axis_fr = "fact"
        fr_strength = max(1, len(fact_hits) - len(rumor_hits))

    # Axis 2: public vs private. Default to public (Immanuel acquires public
    # sources; a claim is "private-typed" only when its subject clearly is).
    if private_hits and len(private_hits) > len(public_hits):
        axis_pp = "private"
        pp_strength = len(private_hits) - len(public_hits)
    else:
        axis_pp = "public"
        pp_strength = max(1, len(public_hits) - len(private_hits))

    category = f"{axis_pp}_{axis_fr}"

    # Confidence: base 0.5, scaled by how decisively each axis leaned.
    total = len(signals) if signals else 0
    lean = fr_strength + pp_strength
    confidence = min(0.99, 0.5 + 0.08 * lean + 0.02 * total)
    if total == 0:
        confidence = 0.4  # nothing fired -> weak default (public_fact)

    epistemic = "observation" if axis_fr == "fact" else "hypothesis"
    return Classification(category, confidence, signals, epistemic)
