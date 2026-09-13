"""The crawler engine: 24/7 control loop with a multi-worker crawler pool.

- Multiple crawler workers process sources in parallel (config NUM_CRAWLERS).
- Pages are re-crawled on an interval; content changes produce timestamped
  versions with diffs (see crawler/pipeline.py + crawler/diffing.py).
- New items and updates are pushed onto a publish queue so the Discord bot can
  host the data in your server's channels.
"""
from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

from .config import Config
from .crawler.discovery import candidate_sources_for
from .crawler.fetcher import Fetcher
from .crawler.pipeline import process_url
from .crawler.robots import RobotsCache
from .crawler.wayback import list_snapshots
from .db import Database

STOPPED, RUNNING, PAUSED = "stopped", "running", "paused"


class Engine:
    def __init__(self, db: Database, config: Config,
                 publish_queue: "asyncio.Queue | None" = None):
        self.db = db
        self.config = config
        self.publish_queue = publish_queue
        self.state = STOPPED
        self._shutdown = asyncio.Event()
        self._wake = asyncio.Event()
        self.started_at: float | None = None
        self.swarm = None  # set when running in swarm mode
        self.stats = {
            "cycles": 0,
            "processed": 0,
            "stored": 0,
            "new_pages": 0,
            "updated": 0,
            "unchanged": 0,
            "errors": 0,
            "discovered": 0,
            "agents_spawned": 0,
            "last_cycle_at": None,
        }

    @property
    def num_workers(self) -> int:
        return max(1, self.config.num_crawlers, self.config.crawl_concurrency)

    # ------------------------------------------------------------- seeding
    async def seed(self) -> int:
        added = 0
        seeds = list(self.config.seed_urls)
        if self.config.auto_discover:
            # built-in firehose sources so it finds its own domains, zero-config
            from .crawler.bootstrap import bootstrap_seeds
            seeds = bootstrap_seeds() + seeds
        for url in seeds:
            if self.db.add_source(url, kind="seed", domain=urlparse(url).netloc):
                added += 1
            if self.config.enable_subdomain_probe:
                for cand in candidate_sources_for(url):
                    if self.db.add_source(cand, kind="probe",
                                          domain=urlparse(cand).netloc):
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

    # ------------------------------------------------------------- controls
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
        snap = {
            "state": self.state,
            "mode": self.config.crawler_mode,
            "workers": self.num_workers,
            "uptime_seconds": round(self.uptime_seconds(), 1),
            "items_total": self.db.count_items(),
            "versions_total": self.db.count_versions(),
            "updates_total": self.db.count_updates(),
            "by_category": self.db.counts_by_category(),
            "sources_total": self.db.count_sources(),
            "sources_active": self.db.count_sources("active"),
            "domains_total": self.db.count_domains(),
            "max_hops": self.config.max_hops,
            "stats": dict(self.stats),
        }
        if self.swarm is not None:
            snap["swarm"] = self.swarm.stats()
        return snap

    def _emit(self, event: dict) -> None:
        if self.publish_queue is None:
            return
        try:
            self.publish_queue.put_nowait(event)
        except asyncio.QueueFull:
            pass  # drop rather than block the crawl loop / grow memory

    # ---------------------------------------------------------------- loop
    async def run_forever(self) -> None:
        prior = self.db.get_state("engine_state")
        if prior == RUNNING or self.config.autostart_crawler:
            self.start()

        if self.config.crawler_mode == "swarm":
            from .crawler.swarm import AgentSwarm
            self.swarm = AgentSwarm(self)
            await self.swarm.run()
            return

        # ---- cycle mode: fixed worker pool draining per-cycle batches ----
        while not self._shutdown.is_set():
            if self.state != RUNNING:
                try:
                    await asyncio.wait_for(self._wake.wait(),
                                           timeout=self.config.cycle_interval_seconds)
                except asyncio.TimeoutError:
                    pass
                self._wake.clear()
                continue

            try:
                await self._run_cycle()
            except Exception as e:
                self.stats["errors"] += 1
                self.db.set_state("last_error", f"{type(e).__name__}: {e}")

            try:
                await asyncio.wait_for(self._shutdown.wait(),
                                       timeout=self.config.cycle_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def _run_cycle(self) -> None:
        cfg = self.config
        due = self.db.due_sources(cfg.max_pages_per_cycle,
                                  min_interval_seconds=cfg.recrawl_interval_seconds)
        if not due:
            return

        robots = RobotsCache(cfg.user_agent, respect=cfg.respect_robots)
        queue: asyncio.Queue = asyncio.Queue()
        for src in due:
            queue.put_nowait(src)

        async with Fetcher(cfg.user_agent, timeout=cfg.request_timeout_seconds,
                           max_bytes=cfg.max_content_bytes,
                           per_domain_delay=cfg.crawl_delay_seconds) as fetcher:

            async def worker() -> None:
                while self.state == RUNNING:
                    try:
                        src = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    try:
                        collector = "wayback" if src.get("kind") == "wayback" else "live"
                        res = await process_url(
                            src["url"], fetcher, robots, self.db,
                            max_links=cfg.max_links_per_page, collector=collector,
                            config=cfg,
                        )
                        self.stats["processed"] += 1
                        self.stats["discovered"] += res.discovered
                        if res.is_new_page:
                            self.stats["new_pages"] += 1
                        if res.is_update:
                            self.stats["updated"] += 1
                        if res.unchanged:
                            self.stats["unchanged"] += 1
                        if res.stored:
                            self.stats["stored"] += 1
                        # publish new pages and updates to Discord
                        if cfg.publish_to_discord and (res.is_new_page or res.is_update):
                            self._emit(res.event())
                        if cfg.publish_to_discord and res.secrets:
                            self._emit({"kind": "secrets", "url": res.url,
                                        "domain": res.domain, "secrets": res.secrets})
                        if (cfg.publish_to_discord and (res.is_new_page or res.is_update)):
                            if getattr(cfg, "publish_media", True) and res.media_items:
                                self._emit(res.media_event())
                            if getattr(cfg, "publish_transcripts", True) and res.transcript:
                                self._emit(res.transcript_event())
                        ok = res.stored or res.unchanged or res.is_new_page or res.is_update
                        self.db.mark_source_crawled(src["id"], ok=ok)
                    except Exception:
                        self.stats["errors"] += 1
                        self.db.mark_source_crawled(src["id"], ok=False)
                    finally:
                        queue.task_done()

            await asyncio.gather(*(worker() for _ in range(self.num_workers)))

        self.stats["cycles"] += 1
        self.stats["last_cycle_at"] = time.time()

    def request_shutdown(self) -> None:
        self._shutdown.set()
        self._wake.set()
