"""Acquisition pipeline: fetch → robots-gate → extract → classify → version → store → discover.

Adds page-level versioning: every capture is timestamped; when a URL's content
changes between captures, a new version is recorded with exactly what was added
and removed, so the system can report "what updated and the new data, when".
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from ..classifier import classify
from ..db import Database
from .diffing import compute_diff
from .extract import extract
from .fetcher import Fetcher
from .robots import RobotsCache


@dataclass
class ProcessResult:
    url: str
    stored: bool = False          # new unique content blob stored
    skipped: bool = False
    reason: str = ""
    # versioning / timestamps
    is_new_page: bool = False     # first time we ever saw this URL (version 1)
    is_update: bool = False       # content changed vs last capture (version n>1)
    unchanged: bool = False
    version_no: int = 0
    diff_summary: str = ""
    added_text: str = ""
    fetched_at: float = 0.0
    timeline_ts: str | None = None
    # classification / display
    category: str | None = None
    title: str | None = None
    excerpt: str = ""
    domain: str = ""
    media: list = field(default_factory=list)
    discovered: int = 0

    def event(self) -> dict:
        """A compact record for the Discord publisher / event queue."""
        return {
            "kind": "update" if self.is_update else "new",
            "url": self.url,
            "domain": self.domain,
            "title": self.title,
            "category": self.category,
            "version_no": self.version_no,
            "diff_summary": self.diff_summary,
            "added_text": self.added_text,
            "excerpt": self.excerpt,
            "fetched_at": self.fetched_at,
            "timeline_ts": self.timeline_ts,
            "media": self.media,
        }


async def process_url(
    url: str,
    fetcher: Fetcher,
    robots: RobotsCache,
    db: Database,
    max_links: int = 20,
    collector: str = "live",
    discover: bool = True,
) -> ProcessResult:
    """Fetch and fully process a single URL."""
    if not url.startswith(("http://", "https://")):
        return ProcessResult(url, skipped=True, reason="unsupported scheme")

    if not await robots.allowed(url, fetcher.client):
        return ProcessResult(url, skipped=True, reason="blocked by robots.txt")

    res = await fetcher.fetch(url)
    if not res.ok:
        return ProcessResult(url, skipped=True, reason=res.error or "fetch failed")

    final_url = res.final_url
    ex = extract(final_url, res.content_type, res.body)
    content_hash = ex.content_hash
    fetched_at = time.time()
    domain = urlparse(final_url).netloc

    cls = classify(ex.title, ex.text)

    # --- versioning / timestamps --------------------------------------------
    latest = db.get_latest_version(final_url)
    is_new_page = is_update = unchanged = False
    diff_summary = ""
    added_text = ""

    if latest is None:
        version_no = 1
        is_new_page = True
        diff_summary = "initial capture"
        added_text = ex.excerpt
        db.add_page_version(
            final_url, version_no, content_hash, ex.title, ex.excerpt,
            diff_summary, ex.excerpt, "", len(ex.excerpt or ""),
            ex.timeline_ts, fetched_at,
        )
    elif latest["content_hash"] == content_hash:
        version_no = latest["version_no"]
        unchanged = True
    else:
        prev_text = db.get_item_content_by_hash(latest["content_hash"]) or ""
        diff = compute_diff(prev_text, ex.text)
        version_no = latest["version_no"] + 1
        is_update = True
        diff_summary = diff.summary
        added_text = diff.added_text
        db.add_page_version(
            final_url, version_no, content_hash, ex.title, ex.excerpt,
            diff.summary, diff.added_text, diff.removed_text, diff.changed_chars,
            ex.timeline_ts, fetched_at,
        )

    # --- store the content blob (content-addressed, dedup L1) ---------------
    stored = False
    if not db.item_exists(content_hash):
        item = {
            "content_hash": content_hash,
            "url": final_url,
            "source_domain": domain,
            "title": ex.title,
            "content": ex.text,
            "excerpt": ex.excerpt,
            "media": ex.media,
            "timeline_ts": ex.timeline_ts,
            "collector": collector,
            "fetched_at": fetched_at,
            **cls.as_dict(),
        }
        stored = db.add_item(item) is not None

    # --- discovery (links + subdomains as future sources) -------------------
    discovered = 0
    if discover and ex.links:
        for link in ex.links[:max_links]:
            if link.startswith(("http://", "https://")):
                if db.add_source(link, kind="discovered",
                                 domain=urlparse(link).netloc):
                    discovered += 1

    return ProcessResult(
        url=final_url,
        stored=stored,
        skipped=unchanged,
        reason="unchanged" if unchanged else "",
        is_new_page=is_new_page,
        is_update=is_update,
        unchanged=unchanged,
        version_no=version_no,
        diff_summary=diff_summary,
        added_text=added_text,
        fetched_at=fetched_at,
        timeline_ts=ex.timeline_ts,
        category=cls.category,
        title=ex.title,
        excerpt=ex.excerpt,
        domain=domain,
        media=ex.media,
        discovered=discovered,
    )
