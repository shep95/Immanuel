"""The crawler engine: 24/7 control loop with start / pause / stop.

Owns run state, seeds sources, runs acquisition cycles at a configurable
interval, and exposes live stats for the Discord `/updates` command and the API
`/health` + `/v1/status` endpoints.
"""
from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

from .config import Config
from .crawler.fetcher import Fetcher
from .crawler.pipeline import process_url
from .crawler.robots import RobotsCache
from .crawler.wayback import list_snapshots
from .db import Database

STOPPED, RUNNING, PAUSED = "stopped", "running", "paused"


class Engine:
    def __init__(self, db: Database, config: Config):
        self.db = db
        self.config = config
        self.state = STOPPED
        self._shutdown = asyncio.Event()
        self._wake = asyncio.Event()
        self.started_at: float | None = None
        self.stats = {
            "cycles": 0,
            "processed": 0,
            "stored": 0,
            "duplicates": 0,
            "errors": 0,
            "discovered": 0,
            "last_cycle_at": None,
        }

    # ------------------------------------------------------------- controls
    async def seed(self) -> int:
        """Register configured seed URLs (and optional Wayback history)."""
        added = 0
        for url in self.config.seed_urls:
            if self.db.add_source(url, kind="seed", domain=urlparse(url).netloc):
                added += 1
        if self.config.enable_wayback and self.config.seed_urls:
            added += await self._expand_wayback(self.config.seed_urls)
        return added

    async def _expand_wayback(self, urls: list[str]) -> int:
        added = 0
        async with Fetcher(self.config.user_agent,
                           timeout=self.config.request_timeout_seconds,
                           max_bytes=self.config.max_content_bytes,
                           per_domain_delay=self.config.crawl_delay_seconds) as f:
            for url in urls:
                snaps = await list_snapshots(url, f.client,
                                             limit=self.config.wayback_max_snapshots)
                for s in snaps:
                    if self.db.add_source(s["capture_url"], kind="wayback",
                                          domain="web.archive.org"):
                        added += 1
        return added

    def start(self) -> str:
        if self.state == RUNNING:
            return "already running"
        was = self.state
        self.state = RUNNING
        if self.started_at is None:
            self.started_at = time.time()
        self.db.set_state("engine_state", self.state)
        self._wake.set()
        return f"started (was {was})"

    def pause(self) -> str:
        if self.state != RUNNING:
            return f"not running (state={self.state})"
        self.state = PAUSED
        self.db.set_state("engine_state", self.state)
        return "paused"

    def stop(self) -> str:
        self.state = STOPPED
        self.db.set_state("engine_state", self.state)
        return "stopped"

    def uptime_seconds(self) -> float:
        return (time.time() - self.started_at) if self.started_at else 0.0

    def snapshot(self) -> dict:
        return {
            "state": self.state,
            "uptime_seconds": round(self.uptime_seconds(), 1),
            "items_total": self.db.count_items(),
            "by_category": self.db.counts_by_category(),
            "sources_total": self.db.count_sources(),
            "sources_active": self.db.count_sources("active"),
            "stats": dict(self.stats),
        }

    # ---------------------------------------------------------------- loop
    async def run_forever(self) -> None:
        """Main loop; run as a background task for the life of the process."""
        # Restore prior state if the process restarted.
        prior = self.db.get_state("engine_state")
        if prior == RUNNING or self.config.autostart_crawler:
            self.start()

        while not self._shutdown.is_set():
            if self.state != RUNNING:
                # sleep until woken (start) or shutdown
                try:
                    await asyncio.wait_for(self._wake.wait(),
                                           timeout=self.config.cycle_interval_seconds)
                except asyncio.TimeoutError:
                    pass
                self._wake.clear()
                continue

            try:
                await self._run_cycle()
            except Exception as e:  # never let the loop die
                self.stats["errors"] += 1
                self.db.set_state("last_error", f"{type(e).__name__}: {e}")

            # interruptible sleep between cycles
            try:
                await asyncio.wait_for(self._shutdown.wait(),
                                       timeout=self.config.cycle_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def _run_cycle(self) -> None:
        cfg = self.config
        due = self.db.due_sources(cfg.max_pages_per_cycle,
                                  min_interval_seconds=cfg.cycle_interval_seconds)
        if not due:
            return
        robots = RobotsCache(cfg.user_agent, respect=cfg.respect_robots)
        sem = asyncio.Semaphore(cfg.crawl_concurrency)

        async with Fetcher(cfg.user_agent, timeout=cfg.request_timeout_seconds,
                           max_bytes=cfg.max_content_bytes,
                           per_domain_delay=cfg.crawl_delay_seconds) as fetcher:

            async def worker(src: dict) -> None:
                async with sem:
                    if self.state != RUNNING:
                        return
                    collector = "wayback" if src.get("kind") == "wayback" else "live"
                    res = await process_url(
                        src["url"], fetcher, robots, self.db,
                        max_links=cfg.max_links_per_page, collector=collector,
                    )
                    self.stats["processed"] += 1
                    self.stats["discovered"] += res.discovered
                    if res.stored:
                        self.stats["stored"] += 1
                    elif res.reason == "duplicate":
                        self.stats["duplicates"] += 1
                    ok = res.stored or res.reason in ("duplicate", "not stored")
                    self.db.mark_source_crawled(src["id"], ok=ok)

            await asyncio.gather(*(worker(s) for s in due))

        self.stats["cycles"] += 1
        self.stats["last_cycle_at"] = time.time()

    def request_shutdown(self) -> None:
        self._shutdown.set()
        self._wake.set()
