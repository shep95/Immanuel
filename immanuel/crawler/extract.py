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
    meta: dict = field(default_factory=dict)   # full page metadata
    code: list[dict] = field(default_factory=list)  # code assets found on the page
    lang: str | None = None

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

    # ---- metadata (harvest BEFORE stripping scripts/styles) ----------------
    meta: dict[str, str] = {}
    for m in soup.find_all("meta"):
        key = m.get("name") or m.get("property") or m.get("itemprop") or m.get("http-equiv")
        content = m.get("content")
        if key and content:
            meta.setdefault(key.strip().lower(), content.strip()[:600])
        if m.get("charset"):
            meta.setdefault("charset", m.get("charset").strip())
    html_tag = soup.find("html")
    lang = (html_tag.get("lang") if html_tag else None) or meta.get("og:locale")
    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        meta["canonical"] = urljoin(url, canonical["href"])

    # ---- code assets (scripts, stylesheets, inline JS, JSON-LD) ------------
    code: list[dict] = []
    for s in soup.find_all("script"):
        src = s.get("src")
        stype = (s.get("type") or "").lower()
        if src:
            code.append({"type": "js", "url": urljoin(url, src)})
        elif "ld+json" in stype:
            snippet = (s.string or s.get_text() or "").strip()
            if snippet:
                code.append({"type": "json-ld", "snippet": snippet[:4000]})
        elif "json" in stype:
            snippet = (s.string or s.get_text() or "").strip()
            if snippet:
                code.append({"type": "json", "snippet": snippet[:4000]})
        else:
            snippet = (s.string or s.get_text() or "").strip()
            if snippet:
                code.append({"type": "inline-js", "snippet": snippet[:4000]})
    for link in soup.find_all("link", href=True):
        rels = " ".join(link.get("rel") or []).lower()
        if "stylesheet" in rels:
            code.append({"type": "css", "url": urljoin(url, link["href"])})

    # ---- media references (img/video/audio/source + og/twitter images) -----
    media: list[dict] = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src:
            media.append({"type": "image", "url": urljoin(url, src),
                          "alt": (img.get("alt") or "")[:200]})
        for cand in (img.get("srcset") or "").split(","):
            u = cand.strip().split(" ")[0]
            if u:
                media.append({"type": "image", "url": urljoin(url, u)})
    for tag in soup.find_all(["video", "audio", "source"]):
        src = tag.get("src")
        if src:
            mt = tag.name if tag.name in ("video", "audio") else "media"
            media.append({"type": mt, "url": urljoin(url, src)})
    for prop in ("og:image", "og:image:url", "twitter:image", "og:video"):
        if meta.get(prop):
            mt = "video" if "video" in prop else "image"
            media.append({"type": mt, "url": urljoin(url, meta[prop])})

    # ---- title, timeline, and clean text (now strip non-content tags) ------
    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)
    if not title:
        title = meta.get("og:title")

    timeline_ts = (meta.get("article:published_time") or meta.get("date")
                   or meta.get("og:updated_time") or meta.get("last-modified"))

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)

    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        if href.startswith(("http://", "https://")):
            links.append(href)

    # de-dup links + media preserving order
    def _dedup(seq, key):
        seen, out = set(), []
        for it in seq:
            k = key(it)
            if k and k not in seen:
                seen.add(k)
                out.append(it)
        return out

    return Extracted(
        title=title,
        text=text[:50000],
        links=_dedup(links, lambda x: x),
        media=_dedup(media, lambda x: x["url"])[:80],
        kind="html",
        timeline_ts=timeline_ts,
        meta=meta,
        code=_dedup(code, lambda x: x.get("url") or x.get("snippet"))[:60],
        lang=(lang.strip()[:20] if lang else None),
    )
