"""Polite HTTP fetcher with per-domain rate limiting and size caps."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    ok: bool
    error: str | None = None


class Fetcher:
    def __init__(self, user_agent: str, timeout: float = 20.0,
                 max_bytes: int = 5_000_000, per_domain_delay: float = 2.0):
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.per_domain_delay = per_domain_delay
        self._last_hit: dict[str, float] = {}
        self._domain_locks: dict[str, asyncio.Lock] = {}
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "Fetcher":
        self._client = httpx.AsyncClient(
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Fetcher must be used as an async context manager")
        return self._client

    def _lock_for(self, domain: str) -> asyncio.Lock:
        lock = self._domain_locks.get(domain)
        if lock is None:
            lock = asyncio.Lock()
            self._domain_locks[domain] = lock
        return lock

    async def _throttle(self, domain: str) -> None:
        last = self._last_hit.get(domain, 0.0)
        wait = self.per_domain_delay - (time.time() - last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_hit[domain] = time.time()

    async def fetch(self, url: str) -> FetchResult:
        domain = urlparse(url).netloc
        if not domain:
            return FetchResult(url, url, 0, "", b"", False, "invalid url")
        async with self._lock_for(domain):
            await self._throttle(domain)
            try:
                async with self.client.stream("GET", url) as resp:
                    content_type = resp.headers.get("content-type", "")
                    chunks, total = [], 0
                    async for chunk in resp.aiter_bytes():
                        total += len(chunk)
                        if total > self.max_bytes:
                            break
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    ok = 200 <= resp.status_code < 300
                    return FetchResult(
                        url=url,
                        final_url=str(resp.url),
                        status=resp.status_code,
                        content_type=content_type,
                        body=body,
                        ok=ok,
                        error=None if ok else f"HTTP {resp.status_code}",
                    )
            except Exception as e:  # network/timeout/etc.
                return FetchResult(url, url, 0, "", b"", False, str(e))
