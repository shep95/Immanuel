"""Per-page intel data-report (deterministic aggregation of open signals).

Collects, for a single crawled page, the open/lawful signals worth keeping as an
intelligence record: page metadata, the entities/topic it maps to, referenced +
downloaded media with their open metadata, exposed-secret *fingerprints* (masked
only), code assets, and the outbound link graph (the N-hop connective tissue).

Pure functions — easy to test, no I/O. The pipeline persists the result.
"""
from __future__ import annotations

import time
from urllib.parse import urlparse


def _domains_of(links: list[str]) -> list[str]:
    seen, out = set(), []
    for l in links:
        d = urlparse(l).netloc
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def build_intel_report(
    *,
    url: str,
    title: str | None,
    category: str | None,
    company: str | None,
    topic: str | None,
    lang: str | None,
    meta: dict,
    links: list[str],
    media_refs: list[dict],
    media_assets: list[dict],
    secrets: list[dict],
    code: list[dict],
    timeline_ts: str | None = None,
) -> tuple[dict, int, int, int]:
    """Return (report, media_count, secrets_count, links_count)."""
    domain = urlparse(url).netloc
    linked_domains = _domains_of(links)

    # open media metadata (dimensions/exif/gps presence) from downloaded assets
    media_meta = []
    gps_hits = 0
    for a in media_assets:
        m = a.get("meta") or {}
        if m.get("has_gps"):
            gps_hits += 1
        media_meta.append({
            "type": a.get("media_type"),
            "source_url": a.get("source_url"),
            "bytes": a.get("bytes"),
            "content_type": a.get("content_type"),
            "meta": m,
        })

    report = {
        "url": url,
        "domain": domain,
        "title": title,
        "category": category,
        "company": company,
        "topic": topic,
        "lang": lang,
        "timeline_ts": timeline_ts,
        "generated_at": time.time(),
        "page_metadata": {k: v for k, v in (meta or {}).items()},
        "counts": {
            "outbound_links": len(links),
            "linked_domains": len(linked_domains),
            "media_referenced": len(media_refs),
            "media_downloaded": len(media_assets),
            "code_assets": len(code),
            "secrets_exposed": len(secrets),
            "media_with_gps": gps_hits,
        },
        "linked_domains": linked_domains[:100],
        "media": media_meta[:50],
        "media_referenced": [
            {"type": m.get("type"), "url": m.get("url")} for m in media_refs[:50]
        ],
        "code_assets": [
            {"type": c.get("type"), "url": c.get("url")}
            for c in code if c.get("url")
        ][:50],
        # secrets are already masked upstream (no raw values ever)
        "secrets_exposed": [
            {"type": s.get("type"), "masked": s.get("masked"),
             "severity": s.get("severity"), "fingerprint": s.get("fingerprint")}
            for s in secrets
        ],
    }
    return report, len(media_assets or media_refs), len(secrets), len(links)
