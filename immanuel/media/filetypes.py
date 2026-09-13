"""Classify any URL / file into a media bucket so it can be routed to its own
public channel: image · audio · video · document · archive · other.

Deterministic: extension first, then content-type, then a declared hint from the
extractor. This is what lets "all file types" (pdf, docx, zip, mp3, …) — not just
images — get their own category, even when the bytes are never downloaded.
"""
from __future__ import annotations

from urllib.parse import urlparse

IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "gif", "svg", "tiff", "tif", "bmp",
             "heic", "heif", "ico", "avif"}
AUDIO_EXT = {"mp3", "wav", "flac", "aac", "ogg", "oga", "m4a", "opus", "wma",
             "aiff", "mid", "midi"}
VIDEO_EXT = {"mp4", "mkv", "mov", "avi", "webm", "mpeg", "mpg", "m4v", "flv",
             "wmv", "3gp", "ogv"}
DOCUMENT_EXT = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv",
                "tsv", "rtf", "odt", "ods", "odp", "epub", "md", "json", "xml",
                "yaml", "yml"}
ARCHIVE_EXT = {"zip", "tar", "gz", "tgz", "bz2", "xz", "rar", "7z", "iso", "dmg",
               "jar", "war"}

BUCKETS = ("image", "audio", "video", "document", "archive", "other")

_EXT_BUCKET = {}
for _b, _exts in (("image", IMAGE_EXT), ("audio", AUDIO_EXT), ("video", VIDEO_EXT),
                  ("document", DOCUMENT_EXT), ("archive", ARCHIVE_EXT)):
    for _e in _exts:
        _EXT_BUCKET[_e] = _b


def file_ext(url: str) -> str:
    path = urlparse(url).path.lower()
    last = path.rsplit("/", 1)[-1]
    return last.rsplit(".", 1)[-1] if "." in last else ""


def classify_media(url: str, content_type: str | None = None,
                   declared: str | None = None) -> str:
    """Return the media bucket for a url. Extension → content-type → declared."""
    ext = file_ext(url)
    if ext in _EXT_BUCKET:
        return _EXT_BUCKET[ext]

    ct = (content_type or "").lower()
    if ct:
        top = ct.split("/", 1)[0]
        if top in ("image", "audio", "video"):
            return top
        if any(k in ct for k in ("pdf", "msword", "officedocument", "text/plain",
                                 "csv", "rtf", "epub", "json", "xml")):
            return "document"
        if any(k in ct for k in ("zip", "x-tar", "gzip", "x-7z", "x-rar",
                                 "x-bzip", "iso")):
            return "archive"

    d = (declared or "").lower()
    if d in ("image", "audio", "video"):
        return d
    if d in ("document", "archive"):
        return d
    return "other"


def is_file_link(url: str) -> bool:
    """True if a plain <a href> points at a downloadable file (not a web page)."""
    return file_ext(url) in _EXT_BUCKET
