"""Content extraction for many media types.

Turns raw bytes + content-type into a normalized record: title, text, links,
and media references (images/audio/video/other). Handles HTML, RSS/Atom feeds,
JSON, plain text, and records metadata for binary media.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

try:
    import feedparser
except Exception:  # pragma: no cover
    feedparser = None


IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".tiff", ".bmp", ".heic"}
AUDIO_EXT = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".opus"}
VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".mpeg", ".mpg"}


@dataclass
class Extracted:
    title: str | None = None
    text: str = ""
    links: list[str] = field(default_factory=list)
    media: list[dict] = field(default_factory=list)
    kind: str = "unknown"        # html|feed|json|text|media|binary
    timeline_ts: str | None = None

    @property
    def content_hash(self) -> str:
        h = hashlib.sha256()
        h.update((self.title or "").encode("utf-8", "ignore"))
        h.update(b"\x00")
        h.update(self.text.encode("utf-8", "ignore"))
        return "sha256:" + h.hexdigest()

    @property
    def excerpt(self) -> str:
        return (self.text or "").strip()[:500]


def _media_type_for(url: str) -> str | None:
    path = urlparse(url).path.lower()
    ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
    if ext in IMAGE_EXT:
        return "image"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in VIDEO_EXT:
        return "video"
    return None


def extract(url: str, content_type: str, body: bytes) -> Extracted:
    ct = (content_type or "").lower()

    # Binary media served directly.
    media_kind = _media_type_for(url)
    if media_kind or any(x in ct for x in ("image/", "audio/", "video/")):
        kind = media_kind or ct.split("/")[0]
        return Extracted(
            title=urlparse(url).path.rsplit("/", 1)[-1] or url,
            text="",
            media=[{"type": kind, "url": url, "content_type": ct, "bytes": len(body)}],
            kind="media",
        )

    # Feeds
    if "xml" in ct or "rss" in ct or "atom" in ct or url.endswith((".rss", ".atom", ".xml")):
        parsed = _try_feed(url, body)
        if parsed is not None:
            return parsed

    # JSON
    if "json" in ct or url.endswith(".json"):
        try:
            data = json.loads(body.decode("utf-8", "ignore"))
            text = json.dumps(data, ensure_ascii=False, indent=2)[:20000]
            return Extracted(title=url, text=text, kind="json")
        except Exception:
            pass

    # HTML
    if "html" in ct or b"<html" in body[:2000].lower() or b"<!doctype html" in body[:200].lower():
        return _extract_html(url, body)

    # Plain text fallback
    text = body.decode("utf-8", "ignore")
    return Extracted(title=url, text=text[:20000], kind="text")


def _try_feed(url: str, body: bytes) -> Extracted | None:
    if feedparser is None:
        return None
    feed = feedparser.parse(body)
    if not getattr(feed, "entries", None):
        return None
    title = getattr(feed.feed, "title", None) or url
    parts, links = [], []
    latest_ts = None
    for e in feed.entries[:50]:
        etitle = getattr(e, "title", "")
        summary = getattr(e, "summary", "")
        link = getattr(e, "link", "")
        parts.append(f"{etitle}\n{summary}")
        if link:
            links.append(link)
        if getattr(e, "published", None) and latest_ts is None:
            latest_ts = e.published
    return Extracted(
        title=title,
        text="\n\n".join(parts)[:20000],
        links=links,
        kind="feed",
        timeline_ts=latest_ts,
    )


def _extract_html(url: str, body: bytes) -> Extracted:
    soup = BeautifulSoup(body, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

    # publication time from common meta tags
    timeline_ts = None
    for sel in [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"name": "date"}),
        ("meta", {"property": "og:updated_time"}),
    ]:
        tag = soup.find(*sel[:1], attrs=sel[1])
        if tag and tag.get("content"):
            timeline_ts = tag["content"]
            break

    text = soup.get_text(separator=" ", strip=True)

    links, media = [], []
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        if href.startswith(("http://", "https://")):
            links.append(href)
    for img in soup.find_all("img", src=True):
        media.append({"type": "image", "url": urljoin(url, img["src"])})
    for source in soup.find_all(["video", "audio"]):
        src = source.get("src")
        if src:
            media.append({"type": source.name, "url": urljoin(url, src)})

    # de-dup links preserving order
    seen, uniq = set(), []
    for l in links:
        if l not in seen:
            seen.add(l)
            uniq.append(l)

    return Extracted(
        title=title,
        text=text[:50000],
        links=uniq,
        media=media[:50],
        kind="html",
        timeline_ts=timeline_ts,
    )
