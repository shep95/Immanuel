"""Environment-driven configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

try:  # optional; .env is convenient locally, not required on Railway
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip())
    except (TypeError, ValueError):
        return default


def _csv(name: str) -> list[str]:
    raw = os.getenv(name, "") or ""
    return [x.strip() for x in raw.split(",") if x.strip()]


@dataclass
class Config:
    # Discord
    discord_token: str = ""
    discord_guild_id: int | None = None
    master_admin_ids: set[int] = field(default_factory=set)

    # Storage
    database_path: str = "./data/immanuel.db"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    public_base_url: str = ""

    # Crawler
    user_agent: str = "ImmanuelBot/1.0 (+https://github.com/shep95/Immanuel)"
    # "swarm" = spawn a new crawler-agent per discovered page (dynamic, fastest);
    # "cycle" = fixed worker pool draining per-cycle batches (steadier).
    crawler_mode: str = "swarm"
    max_agents: int = 50                # max concurrent crawler-agents (swarm cap)
    frontier_max: int = 20000           # max URLs waiting to be picked up
    visited_max: int = 200000           # in-memory recently-seen URL cap
    num_crawlers: int = 8               # parallel workers (cycle mode)
    crawl_concurrency: int = 4          # legacy alias; num_crawlers wins if larger
    crawl_delay_seconds: float = 2.0
    max_pages_per_cycle: int = 25
    cycle_interval_seconds: float = 30.0
    recrawl_interval_seconds: float = 3600.0  # revisit pages to detect updates
    max_links_per_page: int = 20
    request_timeout_seconds: float = 20.0
    max_content_bytes: int = 5_000_000
    respect_robots: bool = True
    autostart_crawler: bool = False
    seed_urls: list[str] = field(default_factory=list)

    # Auto source discovery (zero-config: it finds its own domains/sources)
    auto_discover: bool = True          # load built-in firehose seeds on start
    max_hops: int = 3                   # follow links up to N hops from each root
    # Certificate-Transparency domain firehose (discovers domains across the web)
    enable_ct_discovery: bool = False
    ct_batch_size: int = 200            # domains pulled per CT poll
    ct_poll_seconds: float = 120.0      # how often to pull a new domain batch

    # Discovery (subdomains / non-SEO)
    enable_subdomain_probe: bool = False

    # Discord publishing (host data on your server)
    publish_to_discord: bool = True

    # Wayback / timeline
    enable_wayback: bool = False
    wayback_max_snapshots: int = 25

    # --- Deep acquisition (scrape text + metadata + code + media, not just links) ---
    deep_extract: bool = True            # capture full page metadata + code assets
    scan_secrets: bool = True            # detect exposed API keys / tokens on public pages
    build_intel_report: bool = True      # aggregate open metadata into an intel report

    # --- Media download & import (download files, not just reference them) ---
    download_media: bool = False         # download+store media bytes (uses disk)
    media_store_path: str = "./data/media"
    max_media_bytes: int = 25_000_000    # per-file cap when downloading media
    max_media_per_page: int = 20
    media_types: set[str] = field(default_factory=lambda: {
        "image", "audio", "video", "document", "archive"})
    # Publish every file type + youtube transcripts into their own public channels
    # (works even without downloading bytes — references are still categorized).
    publish_media: bool = True
    publish_transcripts: bool = True
    # YouTube: convert videos -> transcripts, import thumbnails (optional deps)
    enable_youtube: bool = True
    youtube_langs: list[str] = field(default_factory=lambda: ["en"])

    # --- Organization: per-company / per-topic channels & categories ---
    # "epistemic" (default 5 buckets) | "topic" | "company"
    organize_by: str = "epistemic"
    max_dynamic_channels: int = 180      # guardrail (Discord: 500/guild, 50/category)

    # --- Pattern Forge (second, non-AI algorithm that learns patterns 24/7) ---
    enable_pattern_forge: bool = True
    pattern_forge_interval_seconds: float = 300.0   # how often the forge runs a pass
    pattern_min_evidence: int = 3        # observations before a candidate is testable
    pattern_min_confidence: float = 0.6  # promote CANDIDATE -> VALIDATED at/above this
    skills_export_path: str = "./data/skills"

    # --- GitHub tool scout (find useful osint/cyber/hacking/surveillance/red-team repos) ---
    enable_github_scout: bool = True
    github_token: str = ""               # optional; higher rate limits (zero-touch if present)
    github_scout_interval_seconds: float = 900.0     # how often it runs a search pass
    # which tool families to hunt for (each becomes its own search + label)
    github_categories: list[str] = field(default_factory=lambda: [
        "osint", "cyber-security", "hacking", "surveillance", "red-team"])
    github_min_stars: int = 5            # ignore near-empty repos
    github_per_category: int = 30        # results pulled per category per pass
    github_max_per_pass: int = 60        # hard cap on repos classified per pass

    @classmethod
    def from_env(cls) -> "Config":
        guild = os.getenv("DISCORD_GUILD_ID", "").strip()
        return cls(
            discord_token=os.getenv("DISCORD_TOKEN", "").strip(),
            discord_guild_id=int(guild) if guild.isdigit() else None,
            master_admin_ids={int(x) for x in _csv("MASTER_ADMIN_IDS") if x.isdigit()},
            database_path=os.getenv("DATABASE_PATH", "./data/immanuel.db").strip(),
            api_host=os.getenv("API_HOST", "0.0.0.0").strip(),
            # Railway injects PORT; fall back to API_PORT then 8000.
            api_port=_int("PORT", _int("API_PORT", 8000)),
            public_base_url=os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/"),
            user_agent=os.getenv(
                "IMMANUEL_USER_AGENT",
                "ImmanuelBot/1.0 (+https://github.com/shep95/Immanuel)",
            ).strip(),
            crawler_mode=os.getenv("CRAWLER_MODE", "swarm").strip().lower() or "swarm",
            max_agents=_int("MAX_AGENTS", 50),
            frontier_max=_int("FRONTIER_MAX", 20000),
            visited_max=_int("VISITED_MAX", 200000),
            num_crawlers=_int("NUM_CRAWLERS", 8),
            crawl_concurrency=_int("CRAWL_CONCURRENCY", 4),
            crawl_delay_seconds=float(_int("CRAWL_DELAY_SECONDS", 2)),
            max_pages_per_cycle=_int("MAX_PAGES_PER_CYCLE", 25),
            cycle_interval_seconds=float(_int("CYCLE_INTERVAL_SECONDS", 30)),
            recrawl_interval_seconds=float(_int("RECRAWL_INTERVAL_SECONDS", 3600)),
            max_links_per_page=_int("MAX_LINKS_PER_PAGE", 20),
            request_timeout_seconds=float(_int("REQUEST_TIMEOUT_SECONDS", 20)),
            max_content_bytes=_int("MAX_CONTENT_BYTES", 5_000_000),
            respect_robots=_bool("RESPECT_ROBOTS", True),
            autostart_crawler=_bool("AUTOSTART_CRAWLER", False),
            seed_urls=_csv("SEED_URLS"),
            auto_discover=_bool("AUTO_DISCOVER", True),
            max_hops=_int("MAX_HOPS", 3),
            enable_ct_discovery=_bool("ENABLE_CT_DISCOVERY", False),
            ct_batch_size=_int("CT_BATCH_SIZE", 200),
            ct_poll_seconds=float(_int("CT_POLL_SECONDS", 120)),
            enable_subdomain_probe=_bool("ENABLE_SUBDOMAIN_PROBE", False),
            publish_to_discord=_bool("PUBLISH_TO_DISCORD", True),
            enable_wayback=_bool("ENABLE_WAYBACK", False),
            wayback_max_snapshots=_int("WAYBACK_MAX_SNAPSHOTS", 25),
            deep_extract=_bool("DEEP_EXTRACT", True),
            scan_secrets=_bool("SCAN_SECRETS", True),
            build_intel_report=_bool("BUILD_INTEL_REPORT", True),
            download_media=_bool("DOWNLOAD_MEDIA", False),
            media_store_path=os.getenv("MEDIA_STORE_PATH", "./data/media").strip(),
            max_media_bytes=_int("MAX_MEDIA_BYTES", 25_000_000),
            max_media_per_page=_int("MAX_MEDIA_PER_PAGE", 20),
            media_types=set(_csv("MEDIA_TYPES")) or {
                "image", "audio", "video", "document", "archive"},
            publish_media=_bool("PUBLISH_MEDIA", True),
            publish_transcripts=_bool("PUBLISH_TRANSCRIPTS", True),
            enable_youtube=_bool("ENABLE_YOUTUBE", True),
            youtube_langs=_csv("YOUTUBE_LANGS") or ["en"],
            organize_by=(os.getenv("ORGANIZE_BY", "epistemic").strip().lower()
                         or "epistemic"),
            max_dynamic_channels=_int("MAX_DYNAMIC_CHANNELS", 180),
            enable_pattern_forge=_bool("ENABLE_PATTERN_FORGE", True),
            pattern_forge_interval_seconds=float(
                _int("PATTERN_FORGE_INTERVAL_SECONDS", 300)),
            pattern_min_evidence=_int("PATTERN_MIN_EVIDENCE", 3),
            pattern_min_confidence=float(_int("PATTERN_MIN_CONFIDENCE_PCT", 60)) / 100.0,
            skills_export_path=os.getenv("SKILLS_EXPORT_PATH", "./data/skills").strip(),
            enable_github_scout=_bool("ENABLE_GITHUB_SCOUT", True),
            # zero-touch: use a token if the environment already provides one
            github_token=(os.getenv("GITHUB_TOKEN", "")
                          or os.getenv("GH_TOKEN", "")).strip(),
            github_scout_interval_seconds=float(
                _int("GITHUB_SCOUT_INTERVAL_SECONDS", 900)),
            github_categories=(_csv("GITHUB_CATEGORIES") or
                               ["osint", "cyber-security", "hacking",
                                "surveillance", "red-team"]),
            github_min_stars=_int("GITHUB_MIN_STARS", 5),
            github_per_category=_int("GITHUB_PER_CATEGORY", 30),
            github_max_per_pass=_int("GITHUB_MAX_PER_PASS", 60),
        )
