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
    num_crawlers: int = 8               # parallel crawler workers
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

    # Discovery (subdomains / non-SEO)
    enable_subdomain_probe: bool = False

    # Discord publishing (host data on your server)
    publish_to_discord: bool = True

    # Wayback / timeline
    enable_wayback: bool = False
    wayback_max_snapshots: int = 25

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
            enable_subdomain_probe=_bool("ENABLE_SUBDOMAIN_PROBE", False),
            publish_to_discord=_bool("PUBLISH_TO_DISCORD", True),
            enable_wayback=_bool("ENABLE_WAYBACK", False),
            wayback_max_snapshots=_int("WAYBACK_MAX_SNAPSHOTS", 25),
        )
