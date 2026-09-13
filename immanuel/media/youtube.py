"""YouTube: turn videos into transcripts and import thumbnails (best-effort).

- Video-id detection is pure regex (deterministic, no network).
- Thumbnail URLs are constructed directly from the id (no network to build).
- Transcript fetching uses ``youtube-transcript-api`` if installed; otherwise the
  transcript is simply omitted (the thumbnail + id are still captured).
"""
from __future__ import annotations

import re

_YT_ID = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/|v/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})"
)


def video_id(url: str) -> str | None:
    m = _YT_ID.search(url or "")
    return m.group(1) if m else None


def is_youtube(url: str) -> bool:
    return video_id(url) is not None


def thumbnail_urls(vid: str) -> list[str]:
    """Ordered candidate thumbnails (highest quality first)."""
    return [
        f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg",
        f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
        f"https://img.youtube.com/vi/{vid}/0.jpg",
    ]


def fetch_transcript(vid: str, langs: list[str] | None = None) -> str | None:
    """Return the transcript text for a video id, or None if unavailable."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
    except Exception:
        return None
    langs = langs or ["en"]
    try:
        segments = YouTubeTranscriptApi.get_transcript(vid, languages=langs)
    except Exception:
        try:
            segments = YouTubeTranscriptApi.get_transcript(vid)
        except Exception:
            return None
    parts = [s.get("text", "") for s in segments if s.get("text")]
    text = " ".join(parts).strip()
    return text or None


def process_youtube(url: str, langs: list[str] | None = None) -> dict | None:
    """Return {video_id, thumbnail, transcript?} for a YouTube URL, else None."""
    vid = video_id(url)
    if not vid:
        return None
    out = {
        "video_id": vid,
        "thumbnail": thumbnail_urls(vid)[0],
        "thumbnail_candidates": thumbnail_urls(vid),
        "watch_url": f"https://www.youtube.com/watch?v={vid}",
    }
    transcript = fetch_transcript(vid, langs)
    if transcript:
        out["transcript"] = transcript
    return out
