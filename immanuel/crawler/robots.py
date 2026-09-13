"""robots.txt evaluation.

We respect robots.txt by default (spec: never bypass source restrictions). The
checker fetches and caches robots.txt per origin and answers allow/deny for a
given URL + user-agent using the stdlib parser.
"""
from __future__ import annotations

import time
import urllib.robotparser
from urllib.parse import urlparse, urlunparse

import httpx


class RobotsCache:
    def __init__(self, user_agent: str, ttl_seconds: float = 3600.0,
                 respect: bool = True):
        self.user_agent = user_agent
        self.ttl = ttl_seconds
        self.respect = respect
        # origin -> (parser, fetched_at). parser is None if robots was absent.
        self._cache: dict[str, tuple[urllib.robotparser.RobotFileParser | None, float]] = {}

    @staticmethod
    def _origin(url: str) -> str:
        p = urlparse(url)
        return urlunparse((p.scheme, p.netloc, "", "", "", ""))

    async def allowed(self, url: str, client: httpx.AsyncClient) -> bool:
        if not self.respect:
            return True
        origin = self._origin(url)
        if not origin:
            return False
        entry = self._cache.get(origin)
        now = time.time()
        if entry is None or (now - entry[1]) > self.ttl:
            parser = await self._load(origin, client)
            self._cache[origin] = (parser, now)
        else:
            parser = entry[0]
        if parser is None:
            # No robots.txt (or unreachable) -> allowed by convention.
            return True
        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception:
            return True

    async def _load(self, origin: str,
                    client: httpx.AsyncClient) -> urllib.robotparser.RobotFileParser | None:
        robots_url = origin.rstrip("/") + "/robots.txt"
        try:
            resp = await client.get(robots_url, timeout=10.0)
        except Exception:
            return None
        if resp.status_code != 200 or not resp.text:
            return None
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(resp.text.splitlines())
        return parser
