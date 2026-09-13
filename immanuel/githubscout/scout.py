"""24/7 GitHub tool scout — runs alongside the crawler and the Pattern Forge.

Every ``github_scout_interval_seconds`` it runs one pass: for each tool family it
queries the public GitHub search API, classifies each repo deterministically, and
stores + emits the ones that are useful software/algorithms. It walks pages
across passes (persisted cursor) so, over time, it reaches deep/forgotten repos
rather than only the first page. Keyless by default; uses a token if one is
already present in the environment (higher rate limit).

The raw code is never downloaded — only public repo metadata is used.
"""
from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable

from .classify import classify_repo

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
# GitHub search only paginates the first 1000 results per query.
_MAX_RESULTS = 1000

# One curated query per family (the classifier still filters what comes back).
CATEGORY_QUERIES: dict[str, str] = {
    "osint": 'osint OR reconnaissance OR "information gathering" OR footprinting',
    "cyber-security": 'cybersecurity OR "security tool" OR vulnerability-scanner OR dfir',
    "hacking": 'hacking-tool OR pentesting OR exploit OR "penetration testing"',
    "surveillance": 'surveillance OR tracking OR monitoring OR geolocation',
    "red-team": '"red team" OR adversary-emulation OR post-exploitation OR c2',
}

# search_fn(category, page) -> list of raw GitHub repo items
SearchFn = Callable[[str, int], Awaitable[list[dict]]]


class GitHubScout:
    def __init__(self, db, config, emit=None,
                 search_fn: SearchFn | None = None,
                 shutdown: "asyncio.Event | None" = None):
        self.db = db
        self.config = config
        self._emit = emit                       # callable(event: dict) or None
        self._search_fn = search_fn             # injectable for tests / offline
        self._shutdown = shutdown or asyncio.Event()
        self.passes = 0
        self.last_summary: dict | None = None
        self.last_run_at: float | None = None

    # ------------------------------------------------------------- snapshot
    def snapshot(self) -> dict:
        return {
            "enabled": self.config.enable_github_scout,
            "passes": self.passes,
            "last_run_at": self.last_run_at,
            "repos_total": self.db.count_github_repos(),
            "by_category": self.db.github_category_counts(),
            "has_token": bool(self.config.github_token),
            "last_summary": self.last_summary,
        }

    # ------------------------------------------------------------- one pass
    async def run_once(self) -> dict:
        categories = list(self.config.github_categories) or list(CATEGORY_QUERIES)
        per_cat = max(1, int(self.config.github_per_category))
        budget = max(1, int(self.config.github_max_per_pass))
        seen = new = useful = 0
        by_cat: dict[str, int] = {}

        for category in categories:
            if budget <= 0:
                break
            page = self._next_page(category, per_cat)
            try:
                items = await self._search(category, page)
            except Exception as e:  # never let one bad query kill the pass
                self.db.set_state("github_scout_error", f"{type(e).__name__}: {e}")
                continue
            for raw in items:
                if budget <= 0:
                    break
                budget -= 1
                seen += 1
                repo = self._normalize(raw)
                if not repo.get("full_name"):
                    continue
                if repo.get("stars", 0) < self.config.github_min_stars:
                    continue
                cls = classify_repo(repo)
                if cls is None:
                    continue
                useful += 1
                repo.update(category=cls.category, how_useful=cls.how_useful,
                            matched=cls.matched, score=cls.score)
                if self.db.add_github_repo(repo):
                    new += 1
                    by_cat[cls.category] = by_cat.get(cls.category, 0) + 1
                    self._publish(repo)

        self.passes += 1
        self.last_run_at = time.time()
        self.last_summary = {"seen": seen, "useful": useful, "new": new,
                             "by_category": by_cat}
        self.db.set_state("github_scout_last", str(int(self.last_run_at)))
        return self.last_summary

    # ------------------------------------------------------- page cursor
    def _next_page(self, category: str, per_page: int) -> int:
        key = f"gh_page_{category}"
        page = int(self.db.get_state(key, "1") or "1")
        if page < 1:
            page = 1
        # advance for next pass; wrap before GitHub's 1000-result ceiling
        nxt = page + 1
        if nxt * per_page > _MAX_RESULTS:
            nxt = 1
        self.db.set_state(key, str(nxt))
        return page

    # --------------------------------------------------------- normalize
    @staticmethod
    def _normalize(raw: dict) -> dict:
        return {
            "full_name": raw.get("full_name"),
            "name": raw.get("name"),
            "html_url": raw.get("html_url")
            or (f"https://github.com/{raw.get('full_name')}"
                if raw.get("full_name") else None),
            "description": raw.get("description"),
            "language": raw.get("language"),
            "stars": int(raw.get("stargazers_count", raw.get("stars", 0)) or 0),
            "topics": list(raw.get("topics") or []),
            "pushed_at": raw.get("pushed_at"),
        }

    # ------------------------------------------------------------- search
    async def _search(self, category: str, page: int) -> list[dict]:
        if self._search_fn is not None:
            return await self._search_fn(category, page)
        import httpx

        query = CATEGORY_QUERIES.get(category, category)
        query = f"{query} stars:>={self.config.github_min_stars}"
        params = {
            "q": query,
            "sort": "updated",
            "order": "desc",
            "per_page": max(1, int(self.config.github_per_category)),
            "page": page,
        }
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": self.config.user_agent,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.config.github_token:
            headers["Authorization"] = f"Bearer {self.config.github_token}"
        timeout = self.config.request_timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(GITHUB_SEARCH_URL, params=params, headers=headers)
            if resp.status_code != 200:
                # rate-limited / transient — record and yield nothing this pass
                self.db.set_state("github_scout_error",
                                  f"search {category} -> HTTP {resp.status_code}")
                return []
            data = resp.json()
        return data.get("items", []) or []

    # ------------------------------------------------------------- publish
    def _publish(self, repo: dict) -> None:
        if self._emit is None:
            return
        try:
            self._emit({"kind": "github", "repo": repo})
        except Exception:
            pass

    # ------------------------------------------------------------- 24/7 loop
    async def run_forever(self) -> None:
        if not self.config.enable_github_scout:
            return
        interval = max(30.0, self.config.github_scout_interval_seconds)
        # small initial delay so startup isn't hammered
        try:
            await asyncio.wait_for(self._shutdown.wait(), timeout=min(interval, 20.0))
        except asyncio.TimeoutError:
            pass
        while not self._shutdown.is_set():
            try:
                await self.run_once()
            except Exception as e:  # never let the scout kill the process
                self.db.set_state("github_scout_error", f"{type(e).__name__}: {e}")
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    def request_shutdown(self) -> None:
        self._shutdown.set()
