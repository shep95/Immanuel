"""Agent swarm: a new crawler-agent per discovered page (non-AI), hop-bounded.

Every discovered page/link spawns its own lightweight agent (asyncio task) that
fetches, classifies, versions it, then discovers more links — each spawning
another agent. Fan-out is bounded by a **hop depth** (MAX_HOPS, default 3): a
root/domain is hop 0, its links are hop 1, their links hop 2, and so on; links
beyond MAX_HOPS are not followed. That is the "3-way hop across the domains it
finds and the domains connected to those pages".

Safety (avoids runaway spawning / resource exhaustion):
- global semaphore caps concurrent agents at MAX_AGENTS
- per-domain politeness enforced by the shared Fetcher
- visited map with a recrawl window prevents re-spawning a URL until due
- bounded frontier; overflow links persist as DB sources, re-seeded later
- optional Certificate-Transparency domain firehose feeds fresh domains (hop 0)
  in batches when ENABLE_CT_DISCOVERY is on
"""
from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse

from .domain_firehose import fetch_domain_batch
from .fetcher import Fetcher
from .pipeline import process_url
from .robots import RobotsCache


class AgentSwarm:
    def __init__(self, engine):
        self.engine = engine
        self.db = engine.db
        self.config = engine.config
        cfg = self.config
        self.frontier: asyncio.Queue = asyncio.Queue(maxsize=cfg.frontier_max)
        self.sem = asyncio.Semaphore(cfg.max_agents)
        self.visited: dict[str, float] = {}
        self.active = 0
        self.spawned = 0
        self.peak = 0
        self.ct_domains_found = 0
        self._tasks: set[asyncio.Task] = set()
        self._fetcher: Fetcher | None = None
        self._robots: RobotsCache | None = None

    # -------------------------------------------------------------- helpers
    def _should_visit(self, url: str) -> bool:
        if not url.startswith(("http://", "https://")):
            return False
        last = self.visited.get(url)
        if last is not None and (time.time() - last) < self.config.recrawl_interval_seconds:
            return False
        return True

    def _mark(self, url: str) -> None:
        self.visited[url] = time.time()
        if len(self.visited) > self.config.visited_max:
            victims = sorted(self.visited, key=self.visited.get)[: self.config.visited_max // 10]
            for k in victims:
                self.visited.pop(k, None)

    def enqueue(self, url: str, depth: int) -> bool:
        """Enqueue a URL at a given hop depth (0 = root). Beyond MAX_HOPS: skip."""
        if depth > self.config.max_hops:
            return False
        if not self._should_visit(url):
            return False
        try:
            self.frontier.put_nowait((url, depth))
            return True
        except asyncio.QueueFull:
            return False  # persisted as a DB source instead; re-seeded later

    def _reseed(self) -> int:
        """Push DB sources (roots, hop 0) that are new or due for a recrawl."""
        due = self.db.due_sources(self.config.frontier_max,
                                  self.config.recrawl_interval_seconds)
        n = 0
        for s in due:
            if self.enqueue(s["url"], 0):
                n += 1
        return n

    async def _pull_ct_domains(self) -> int:
        """Pull a batch of domains from Certificate Transparency; enqueue as roots."""
        if not self.config.enable_ct_discovery or self._fetcher is None:
            return 0
        urls = await fetch_domain_batch(self._fetcher.client,
                                        limit=self.config.ct_batch_size)
        n = 0
        for u in urls:
            if self.db.add_source(u, kind="ct", domain=urlparse(u).netloc):
                n += 1
            self.enqueue(u, 0)
        self.ct_domains_found += n
        return n

    def stats(self) -> dict:
        return {
            "agents_active": self.active,
            "agents_spawned": self.spawned,
            "peak_agents": self.peak,
            "frontier_size": self.frontier.qsize(),
            "visited_size": len(self.visited),
            "ct_domains_found": self.ct_domains_found,
            "max_hops": self.config.max_hops,
        }

    # ---------------------------------------------------------------- agent
    async def _agent(self, url: str, depth: int) -> None:
        self.active += 1
        self.spawned += 1
        if self.active > self.peak:
            self.peak = self.active
        st = self.engine.stats
        st["agents_spawned"] = self.spawned
        try:
            res = await process_url(
                url, self._fetcher, self._robots, self.db,
                max_links=self.config.max_links_per_page, discover=True,
                config=self.config,
            )
            st["processed"] += 1
            st["discovered"] += res.discovered
            if res.is_new_page:
                st["new_pages"] += 1
            if res.is_update:
                st["updated"] += 1
            if res.unchanged:
                st["unchanged"] += 1
            if res.stored:
                st["stored"] += 1
            if self.config.publish_to_discord and (res.is_new_page or res.is_update):
                self.engine._emit(res.event())
            if self.config.publish_to_discord and res.secrets:
                self.engine._emit({"kind": "secrets", "url": res.url,
                                   "domain": res.domain, "secrets": res.secrets})
            ok = res.stored or res.unchanged or res.is_new_page or res.is_update
            self.db.mark_url_crawled(url, ok=ok)
            # fan out one more hop, if within the hop budget
            if self.engine.state == "running" and depth < self.config.max_hops:
                for link in res.links:
                    self.enqueue(link, depth + 1)
        except Exception:
            st["errors"] += 1
            self.db.mark_url_crawled(url, ok=False)
        finally:
            self.active -= 1
            self.sem.release()

    # ----------------------------------------------------------------- loop
    async def run(self) -> None:
        cfg = self.config
        async with Fetcher(cfg.user_agent, timeout=cfg.request_timeout_seconds,
                           max_bytes=cfg.max_content_bytes,
                           per_domain_delay=cfg.crawl_delay_seconds) as fetcher:
            self._fetcher = fetcher
            self._robots = RobotsCache(cfg.user_agent, respect=cfg.respect_robots)
            last_reseed = 0.0
            last_ct = 0.0

            while not self.engine._shutdown.is_set():
                if self.engine.state != "running":
                    await asyncio.sleep(0.5)
                    continue

                now = time.time()
                if now - last_reseed > cfg.cycle_interval_seconds:
                    self._reseed()
                    last_reseed = now
                    self.engine.stats["cycles"] += 1
                if cfg.enable_ct_discovery and now - last_ct > cfg.ct_poll_seconds:
                    await self._pull_ct_domains()
                    last_ct = now

                try:
                    url, depth = await asyncio.wait_for(self.frontier.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                if not self._should_visit(url):
                    continue
                self._mark(url)

                await self.sem.acquire()
                if self.engine.state != "running" or self.engine._shutdown.is_set():
                    self.sem.release()
                    continue
                task = asyncio.create_task(self._agent(url, depth))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

            for _ in range(20):
                if not self._tasks:
                    break
                await asyncio.sleep(0.1)
            for t in list(self._tasks):
                t.cancel()

    async def drain_once(self) -> None:
        """Test helper: reseed, then process the frontier to completion."""
        cfg = self.config
        async with Fetcher(cfg.user_agent, timeout=cfg.request_timeout_seconds,
                           max_bytes=cfg.max_content_bytes,
                           per_domain_delay=cfg.crawl_delay_seconds) as fetcher:
            self._fetcher = fetcher
            self._robots = RobotsCache(cfg.user_agent, respect=cfg.respect_robots)
            self._reseed()
            while not self.frontier.empty() or self._tasks:
                while not self.frontier.empty():
                    url, depth = self.frontier.get_nowait()
                    if not self._should_visit(url):
                        continue
                    self._mark(url)
                    await self.sem.acquire()
                    task = asyncio.create_task(self._agent(url, depth))
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)
                if self._tasks:
                    await asyncio.wait(self._tasks, return_when=asyncio.FIRST_COMPLETED)
