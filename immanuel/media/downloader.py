"""Download media files, extract open metadata, and store them content-addressed.

- Downloads image/audio/video assets referenced on a page (bounded by size,
  count, and per-domain politeness via the shared Fetcher).
- Extracts *open* metadata only (dimensions, EXIF for images) — no private data.
- Stores bytes on disk keyed by sha256 (dedup) and records the asset + metadata.

Pillow is optional; without it, images are still stored with basic metadata.
"""
from __future__ import annotations

import hashlib
import os
from urllib.parse import urlparse

_EXT_FOR_TYPE = {"image": ".img", "audio": ".aud", "video": ".vid",
                 "document": ".doc", "archive": ".arc", "other": ".bin"}


def _guess_ext(url: str, content_type: str, media_type: str) -> str:
    path = urlparse(url).path
    if "." in path.rsplit("/", 1)[-1]:
        return "." + path.rsplit(".", 1)[-1][:8]
    if "/" in content_type:
        sub = content_type.split("/", 1)[1].split(";")[0].strip()
        if sub:
            return "." + sub[:8]
    return _EXT_FOR_TYPE.get(media_type, ".bin")


def _image_metadata(data: bytes) -> dict:
    """Best-effort open image metadata (dimensions + EXIF). Pillow optional."""
    try:
        import io

        from PIL import ExifTags, Image  # type: ignore
    except Exception:
        return {}
    meta: dict = {}
    try:
        with Image.open(io.BytesIO(data)) as im:
            meta["width"], meta["height"] = im.size
            meta["format"] = im.format
            meta["mode"] = im.mode
            exif = getattr(im, "_getexif", lambda: None)()
            if exif:
                tags = {}
                for tag_id, value in exif.items():
                    name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    if name in ("MakerNote",):
                        continue
                    try:
                        tags[name] = str(value)[:200]
                    except Exception:
                        continue
                if tags:
                    meta["exif"] = tags
                    # surface GPS presence for the intel report (open metadata)
                    if "GPSInfo" in tags:
                        meta["has_gps"] = True
    except Exception:
        return meta
    return meta


async def download_media(fetcher, robots, db, config, page_url: str,
                         media_list: list[dict]) -> list[dict]:
    """Download allowed media from ``media_list``; return stored-asset records."""
    if not config.download_media or not media_list:
        return []
    os.makedirs(config.media_store_path, exist_ok=True)
    stored: list[dict] = []
    count = 0
    for m in media_list:
        if count >= config.max_media_per_page:
            break
        mtype = m.get("type")
        url = m.get("url")
        if not url or mtype not in config.media_types:
            continue
        if not url.startswith(("http://", "https://")):
            continue
        try:
            if not await robots.allowed(url, fetcher.client):
                continue
        except Exception:
            pass
        res = await fetcher.fetch(url)
        if not res.ok or not res.body:
            continue
        if len(res.body) > config.max_media_bytes:
            continue
        sha = "sha256:" + hashlib.sha256(res.body).hexdigest()
        count += 1
        if db.media_exists(sha):
            continue
        meta = _image_metadata(res.body) if mtype == "image" else {}
        meta["bytes"] = len(res.body)
        ext = _guess_ext(res.final_url or url, res.content_type, mtype)
        shard = sha.split(":", 1)[1][:2]
        folder = os.path.join(config.media_store_path, shard)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, sha.split(":", 1)[1] + ext)
        try:
            with open(path, "wb") as fh:
                fh.write(res.body)
        except Exception:
            path = None
        db.add_media_asset(sha, url, page_url, mtype, res.content_type,
                           len(res.body), path, meta)
        stored.append({
            "sha256": sha, "source_url": url, "media_type": mtype,
            "content_type": res.content_type, "bytes": len(res.body),
            "stored_path": path, "meta": meta,
        })
    return stored
