"""Deterministic classifier: is a GitHub repo useful software/algorithm for one
of the five tool families, and if so, which one and why.

No AI. Given a repo's public metadata (name, description, topics, language) it
scores each family by counting distinct signal keywords that appear (topic hits
count double, since a maintainer-declared topic is a stronger signal than a word
in prose). The winning family must clear a minimum score, and the repo must look
like actual software/algorithm code (a real programming language, or a tool-ish
topic) rather than a docs/awesome-list.

The output is fully reproducible: same repo in -> same classification out.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Ordered so ties resolve deterministically (earlier family wins on equal score).
CATEGORY_SIGNALS: dict[str, tuple[str, ...]] = {
    "osint": (
        "osint", "open-source-intelligence", "reconnaissance", "recon",
        "information-gathering", "footprinting", "maltego", "spiderfoot",
        "theharvester", "username", "email-lookup", "people-search", "dork",
        "google-dork", "dorking", "subdomain-enumeration", "threat-intelligence",
        "social-media-intelligence", "sherlock", "geoint", "socmint",
    ),
    "cyber-security": (
        "security", "cybersecurity", "cyber-security", "infosec",
        "vulnerability", "vulnerability-scanner", "malware", "malware-analysis",
        "threat-detection", "siem", "incident-response", "forensics",
        "dfir", "detection", "intrusion-detection", "ids", "ips",
        "hardening", "security-tools", "blue-team", "yara",
    ),
    "hacking": (
        "hacking", "hacking-tool", "hacktools", "ethical-hacking", "exploit",
        "exploitation", "pentest", "pentesting", "penetration-testing",
        "payload", "reverse-engineering", "privilege-escalation", "bruteforce",
        "brute-force", "fuzzing", "fuzzer", "rce", "sqli", "sql-injection",
        "xss", "metasploit",
    ),
    "surveillance": (
        "surveillance", "tracking", "monitoring", "spyware", "stalkerware",
        "geolocation", "location-tracking", "cctv", "camera", "webcam",
        "wiretap", "interception", "keylogger", "phone-tracking",
        "ip-tracker", "osint-tracking", "person-tracking",
    ),
    "red-team": (
        "red-team", "redteam", "red-teaming", "adversary-emulation",
        "adversary-simulation", "c2", "command-and-control", "cobalt-strike",
        "implant", "post-exploitation", "lateral-movement", "evasion",
        "av-evasion", "edr-evasion", "offensive-security", "offensive",
        "mitre-attack", "att-ck", "beacon",
    ),
}

# What each family is good for (base sentence; matched signals + facts appended).
_USEFULNESS = {
    "osint": ("collects or analyzes open-source intelligence — useful for "
              "reconnaissance, footprinting, and mapping a target's public "
              "footprint from open sources"),
    "cyber-security": ("supports defensive security — useful for detection, "
                       "hardening, vulnerability analysis, forensics, or "
                       "monitoring of systems you own or protect"),
    "hacking": ("an offensive / penetration-testing tool — useful for probing, "
                "exploiting, or testing the security of a target you are "
                "authorized to assess"),
    "surveillance": ("supports monitoring / surveillance workflows — useful for "
                     "tracking activity, signals, or network/physical "
                     "observation"),
    "red-team": ("supports red-team operations — useful for adversary "
                 "emulation, command-and-control, post-exploitation, or evasion "
                 "during authorized engagements"),
}

# Languages that mean "docs/markup", not software/algorithm code.
_DOC_LANGS = {"", "markdown", "html", "text", "tex", "css", "restructuredtext",
              "roff", "rich text format"}

# Tool-ish topics that qualify a repo as software even if GitHub reports no
# primary language (e.g. shell-only or config-driven tools).
_TOOL_TOPICS = {
    "tool", "tools", "cli", "framework", "scanner", "automation", "toolkit",
    "script", "scripts", "bot", "engine", "library",
}


@dataclass
class RepoClassification:
    category: str
    score: int
    matched: list[str] = field(default_factory=list)
    how_useful: str = ""

    def as_dict(self) -> dict:
        return {
            "category": self.category,
            "score": self.score,
            "matched": list(self.matched),
            "how_useful": self.how_useful,
        }


def _haystack(repo: dict) -> tuple[str, set[str]]:
    name = str(repo.get("full_name") or repo.get("name") or "").lower()
    desc = str(repo.get("description") or "").lower()
    topics = {str(t).lower() for t in (repo.get("topics") or [])}
    # normalize separators so "red_team"/"red team" match the "red-team" signal
    text = f"{name} {desc} {' '.join(sorted(topics))}"
    for ch in ("_", "/", ".", ",", ":", "  "):
        text = text.replace(ch, " ")
    norm_text = " " + text.replace("-", "-") + " "
    return norm_text, topics


def is_software(repo: dict) -> bool:
    """True if the repo looks like actual software/algorithm code, not docs."""
    lang = str(repo.get("language") or "").strip().lower()
    if lang and lang not in _DOC_LANGS:
        return True
    topics = {str(t).lower() for t in (repo.get("topics") or [])}
    if topics & _TOOL_TOPICS:
        return True
    return False


def _signal_hits(signal: str, text: str, topics: set[str]) -> int:
    """0 = no hit, 1 = prose hit, 2 = declared-topic hit (stronger)."""
    if signal in topics:
        return 2
    # word-ish containment: signals may be multi-word joined by '-'
    needle = signal.replace("-", " ")
    if f" {needle} " in text or f" {signal} " in text:
        return 1
    # allow hyphenated signal to match hyphenated occurrence in text
    if signal in text and "-" in signal:
        return 1
    return 0


def classify_repo(repo: dict, min_score: int = 2) -> RepoClassification | None:
    """Return the best-fitting family (or None if not a useful tool).

    ``min_score`` of 2 means: at least one declared topic, OR two prose signals.
    """
    text, topics = _haystack(repo)
    best: RepoClassification | None = None
    for category, signals in CATEGORY_SIGNALS.items():
        matched: list[str] = []
        score = 0
        for sig in signals:
            hit = _signal_hits(sig, text, topics)
            if hit:
                matched.append(sig)
                score += hit
        if score <= 0:
            continue
        # strictly-greater keeps the earlier (higher-priority) family on ties
        if best is None or score > best.score:
            best = RepoClassification(category, score, sorted(set(matched)))
    if best is None or best.score < min_score:
        return None
    if not is_software(repo):
        return None
    best.how_useful = _useful_text(best, repo)
    return best


def _useful_text(cls: RepoClassification, repo: dict) -> str:
    base = _USEFULNESS.get(cls.category, "a security-related tool")
    facts = []
    lang = repo.get("language")
    if lang:
        facts.append(f"written in {lang}")
    stars = repo.get("stars")
    if stars:
        facts.append(f"{stars}★")
    tail = f" ({', '.join(facts)})" if facts else ""
    signals = ", ".join(cls.matched[:6])
    why = f" matched on: {signals}." if signals else "."
    return f"{base}{tail}.{why}"
