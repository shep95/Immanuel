"""Acquisition pipeline: fetch → robots-gate → extract → classify → store → discover."""
from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urlparse

from ..classifier import classify
from ..db import Database
from .extract import extract
from .fetcher import Fetcher
from .robots import RobotsCache


@dataclass
class ProcessResult:
    url: str
    stored: bool
    skipped: bool
    reason: str = ""
    category: str | None = None
    discovered: int = 0


async def process_url(
    url: str,
    fetcher: Fetcher,
    robots: RobotsCache,
    db: Database,
    max_links: int = 20,
    collector: str = "live",
    discover: bool = True,
) -> ProcessResult:
    """Fetch and fully process a single URL. Returns what happened."""
    if not url.startswith(("http://", "https://")):
        return ProcessResult(url, False, True, "unsupported scheme")

    allowed = await robots.allowed(url, fetcher.client)
    if not allowed:
        return ProcessResult(url, False, True, "blocked by robots.txt")

    res = await fetcher.fetch(url)
    if not res.ok:
        return ProcessResult(url, False, True, res.error or "fetch failed")

    ex = extract(res.final_url, res.content_type, res.body)
    content_hash = ex.content_hash

    if db.item_exists(content_hash):
        stored_id = None
    else:
        cls = classify(ex.title, ex.text)
        item = {
            "content_hash": content_hash,
            "url": res.final_url,
            "source_domain": urlparse(res.final_url).netloc,
            "title": ex.title,
            "content": ex.text,
            "excerpt": ex.excerpt,
            "media": ex.media,
            "timeline_ts": ex.timeline_ts,
            "collector": collector,
            "fetched_at": time.time(),
            **cls.as_dict(),
        }
        stored_id = db.add_item(item)

    # Discovery: register new links as future sources (bounded).
    discovered = 0
    if discover and ex.links:
        for link in ex.links[:max_links]:
            if link.startswith(("http://", "https://")):
                if db.add_source(link, kind="discovered",
                                 domain=urlparse(link).netloc):
                    discovered += 1

    if stored_id is None and db.item_exists(content_hash):
        # existed already (duplicate) — not an error
        return ProcessResult(res.final_url, False, True, "duplicate",
                             discovered=discovered)

    category = None
    if stored_id is not None:
        # re-read category cheaply from the just-built classification
        category = item["category"]  # type: ignore[name-defined]
    return ProcessResult(
        url=res.final_url,
        stored=stored_id is not None,
        skipped=stored_id is None,
        reason="" if stored_id is not None else "not stored",
        category=category,
        discovered=discovered,
    )
