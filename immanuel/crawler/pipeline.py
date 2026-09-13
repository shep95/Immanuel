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
from .secrets import scan_secrets


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
    links: list = field(default_factory=list)   # http(s) links found on the page
    # deep-acquisition extras
    company: str | None = None
    topic: str | None = None
    lang: str | None = None
    secrets: list = field(default_factory=list)      # masked findings only
    media_assets: list = field(default_factory=list)  # downloaded assets
    code: list = field(default_factory=list)
    intel: bool = False

    def event(self) -> dict:
        """A compact record for the Discord publisher / event queue."""
        return {
            "kind": "update" if self.is_update else "new",
            "url": self.url,
            "domain": self.domain,
            "title": self.title,
            "category": self.category,
            "company": self.company,
            "topic": self.topic,
            "version_no": self.version_no,
            "diff_summary": self.diff_summary,
            "added_text": self.added_text,
            "excerpt": self.excerpt,
            "fetched_at": self.fetched_at,
            "timeline_ts": self.timeline_ts,
            "media": self.media,
            "secrets_count": len(self.secrets),
            "media_downloaded": len(self.media_assets),
        }


async def _fetch(fetcher, url, extra_headers):
    """Fetch with optional conditional-GET headers; fall back if unsupported."""
    if extra_headers:
        try:
            return await fetcher.fetch(url, extra_headers=extra_headers)
        except TypeError:
            pass
    return await fetcher.fetch(url)


async def process_url(
    url: str,
    fetcher: Fetcher,
    robots: RobotsCache,
    db: Database,
    max_links: int = 20,
    collector: str = "live",
    discover: bool = True,
    config=None,
) -> ProcessResult:
    """Fetch and fully process a single URL.

    When ``config`` is provided, deep-acquisition runs: full metadata + code
    capture, exposed-secret scanning, company/topic organization, YouTube
    transcript + thumbnail import, media download, and an intel data-report.
    Without ``config`` the classic behavior (extract → classify → version →
    store → discover) is preserved unchanged.
    """
    if not url.startswith(("http://", "https://")):
        return ProcessResult(url, skipped=True, reason="unsupported scheme")

    if not await robots.allowed(url, fetcher.client):
        return ProcessResult(url, skipped=True, reason="blocked by robots.txt")

    # conditional GET so a restarted crawler doesn't re-download unchanged pages
    extra_headers = None
    if config is not None:
        cache = db.get_http_cache(url)
        if cache:
            hdrs = {}
            if cache.get("etag"):
                hdrs["If-None-Match"] = cache["etag"]
            if cache.get("last_modified"):
                hdrs["If-Modified-Since"] = cache["last_modified"]
            extra_headers = hdrs or None

    res = await _fetch(fetcher, url, extra_headers)
    if config is not None and getattr(res, "status", 0) == 304:
        return ProcessResult(url, skipped=True, unchanged=True, reason="not modified (304)")
    if not res.ok:
        return ProcessResult(url, skipped=True, reason=res.error or "fetch failed")

    final_url = res.final_url
    ex = extract(final_url, res.content_type, res.body)

    # --- YouTube: fold transcript into text, capture thumbnail (before hash) --
    if config is not None and getattr(config, "enable_youtube", False):
        from ..media.youtube import is_youtube, process_youtube
        if is_youtube(final_url):
            yt = process_youtube(final_url, getattr(config, "youtube_langs", ["en"]))
            if yt:
                if yt.get("transcript"):
                    ex.text = (ex.text + "\n\n[youtube transcript]\n"
                               + yt["transcript"])[:200000]
                ex.media.append({"type": "image", "url": yt["thumbnail"],
                                 "role": "youtube-thumbnail"})
                ex.meta.setdefault("youtube_video_id", yt["video_id"])

    content_hash = ex.content_hash
    fetched_at = time.time()
    domain = urlparse(final_url).netloc

    cls = classify(ex.title, ex.text)

    # --- deep acquisition: organize + secrets (computed before store) --------
    company = topic = None
    secrets_found: list[dict] = []
    if config is not None:
        from ..organize import company_for, topic_for
        company = company_for(final_url, ex.meta)
        topic, _hits = topic_for(ex.title, ex.text, ex.meta)
        if getattr(config, "scan_secrets", False):
            blob = ex.text + "\n" + "\n".join(
                c.get("snippet", "") for c in ex.code if c.get("snippet"))
            for s in scan_secrets(blob):
                secrets_found.append(s.as_dict())

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
            "company": company,
            "topic": topic,
            "meta": ex.meta,
            "code": ex.code,
            "secrets_count": len(secrets_found),
            "lang": ex.lang,
            **cls.as_dict(),
        }
        stored = db.add_item(item) is not None

    # --- persist exposed-secret findings (admin-only surface) ---------------
    if config is not None and secrets_found:
        for s in secrets_found:
            db.add_secret(final_url, domain, s["type"], s["masked"],
                          s["fingerprint"], s["context"], s["severity"])

    # --- discovery (links + subdomains as future sources) -------------------
    discovered = 0
    found_links: list[str] = []
    if ex.links:
        for link in ex.links[:max_links]:
            if link.startswith(("http://", "https://")):
                found_links.append(link)
                if discover and db.add_source(link, kind="discovered",
                                              domain=urlparse(link).netloc):
                    discovered += 1

    # --- media download + intel report (deep acquisition only) --------------
    media_assets: list[dict] = []
    intel_built = False
    if config is not None:
        if getattr(config, "download_media", False):
            try:
                from ..media.downloader import download_media
                media_assets = await download_media(
                    fetcher, robots, db, config, final_url, ex.media)
            except Exception:
                media_assets = []
        if getattr(config, "build_intel_report", False):
            try:
                from ..intel import build_intel_report
                report, mc, sc, lc = build_intel_report(
                    url=final_url, title=ex.title, category=cls.category,
                    company=company, topic=topic, lang=ex.lang, meta=ex.meta,
                    links=found_links, media_refs=ex.media,
                    media_assets=media_assets, secrets=secrets_found, code=ex.code,
                    timeline_ts=ex.timeline_ts)
                db.upsert_intel_report(final_url, domain, report, mc, sc, lc)
                intel_built = True
            except Exception:
                intel_built = False
        # remember validators so an unchanged page can be skipped next time
        try:
            db.set_http_cache(final_url, getattr(res, "etag", None),
                              getattr(res, "last_modified", None), content_hash)
        except Exception:
            pass

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
        links=found_links,
        company=company,
        topic=topic,
        lang=ex.lang,
        secrets=secrets_found,
        media_assets=media_assets,
        code=ex.code,
        intel=intel_built,
    )
