"""Internet Archive Wayback Machine collector (historical timeline).

Uses the public CDX API to enumerate historical captures of a URL — "from when
the site was founded to present". This is a lawful public API; we simply list
snapshots and turn them into reconstructed capture URLs the crawler can fetch.
Forward-in-time ("future days") coverage is handled by the 24/7 live crawler.
"""
from __future__ import annotations

import httpx

CDX_API = "https://web.archive.org/cdx/search/cdx"


async def list_snapshots(url: str, client: httpx.AsyncClient,
                         limit: int = 25) -> list[dict]:
    """Return up to `limit` historical snapshots for `url`, oldest first.

    Each snapshot: {timestamp, original, capture_url}.
    """
    params = {
        "url": url,
        "output": "json",
        "fl": "timestamp,original,statuscode",
        "filter": "statuscode:200",
        "collapse": "timestamp:6",   # ~monthly granularity to spread coverage
        "limit": str(max(1, min(limit, 200))),
    }
    try:
        resp = await client.get(CDX_API, params=params, timeout=30.0)
        resp.raise_for_status()
        rows = resp.json()
    except Exception:
        return []
    if not rows or len(rows) < 2:
        return []
    header, *data = rows
    out = []
    for row in data:
        rec = dict(zip(header, row))
        ts = rec.get("timestamp")
        original = rec.get("original")
        if ts and original:
            out.append({
                "timestamp": ts,
                "original": original,
                # id_ = raw capture (no Wayback rewriting of links/assets)
                "capture_url": f"https://web.archive.org/web/{ts}id_/{original}",
            })
    return out
