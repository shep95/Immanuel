"""Agent swarm: a new crawler-agent per discovered page (non-AI).

Instead of a fixed worker pool, the swarm spawns a fresh lightweight *agent*
(an asyncio task) for every URL it discovers. Each agent fetches its page,
classifies + versions it, then discovers new links — each of which spawns
another agent. This fans out massively and continuously.

Safety (this is the runaway-spawn risk the spec warns about):
- A global semaphore caps concurrent agents at MAX_AGENTS (so "one agent per
  page" never becomes millions of live tasks at once — pages queue in a
  bounded frontier and spawn as capacity frees).
- Per-domain politeness is still enforced by the shared Fetcher (agents hitting
  the same host serialize; different hosts run in parallel).
- A visited map with a recrawl window prevents re-spawning the same URL until
  it's due for an update check; its size is capped to bound memory.
- The frontier queue is bounded; overflow links are still persisted as DB
  sources, so nothing is lost — they're picked up by the re-seed loop later.
"""
from __future__ import annotations

import asyncio
import time

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
            # evict the oldest ~10% to bound memory
            victims = sorted(self.visited, key=self.visited.get)[: self.config.visited_max // 10]
            for k in victims:
                self.visited.pop(k, None)

    def enqueue(self, url: str) -> bool:
        if not self._should_visit(url):
            return False
        try:
            self.frontier.put_nowait(url)
            return True
        except asyncio.QueueFull:
            return False  # persisted as a DB source instead; re-seeded later

    def _reseed(self) -> int:
        """Push DB sources that are new or due for a recrawl into the frontier."""
        due = self.db.due_sources(self.config.frontier_max,
                                  self.config.recrawl_interval_seconds)
        n = 0
        for s in due:
            if self.enqueue(s["url"]):
                n += 1
        return n

    def stats(self) -> dict:
        return {
            "agents_active": self.active,
            "agents_spawned": self.spawned,
            "peak_agents": self.peak,
            "frontier_size": self.frontier.qsize(),
            "visited_size": len(self.visited),
        }

    # ---------------------------------------------------------------- agent
    async def _agent(self, url: str) -> None:
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
            ok = res.stored or res.unchanged or res.is_new_page or res.is_update
            self.db.mark_url_crawled(url, ok=ok)
            # fan out: each discovered link spawns a future agent
            if self.engine.state == "running":
                for link in res.links:
                    self.enqueue(link)
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

            while not self.engine._shutdown.is_set():
                if self.engine.state != "running":
                    await asyncio.sleep(0.5)
                    continue

                if time.time() - last_reseed > cfg.cycle_interval_seconds:
                    self._reseed()
                    last_reseed = time.time()
                    self.engine.stats["cycles"] += 1

                try:
                    url = await asyncio.wait_for(self.frontier.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                if not self._should_visit(url):
                    continue
                self._mark(url)

                # acquire a slot BEFORE spawning -> caps concurrent agents
                await self.sem.acquire()
                if self.engine.state != "running" or self.engine._shutdown.is_set():
                    self.sem.release()
                    continue
                task = asyncio.create_task(self._agent(url))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

            # shutdown: let in-flight agents settle, then cancel stragglers
            for _ in range(20):
                if not self._tasks:
                    break
                await asyncio.sleep(0.1)
            for t in list(self._tasks):
                t.cancel()

    async def drain_once(self) -> None:
        """Test helper: reseed, then process the current frontier to completion."""
        cfg = self.config
        async with Fetcher(cfg.user_agent, timeout=cfg.request_timeout_seconds,
                           max_bytes=cfg.max_content_bytes,
                           per_domain_delay=cfg.crawl_delay_seconds) as fetcher:
            self._fetcher = fetcher
            self._robots = RobotsCache(cfg.user_agent, respect=cfg.respect_robots)
            self._reseed()
            while not self.frontier.empty() or self._tasks:
                while not self.frontier.empty():
                    url = self.frontier.get_nowait()
                    if not self._should_visit(url):
                        continue
                    self._mark(url)
                    await self.sem.acquire()
                    task = asyncio.create_task(self._agent(url))
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)
                if self._tasks:
                    await asyncio.wait(self._tasks, return_when=asyncio.FIRST_COMPLETED)
