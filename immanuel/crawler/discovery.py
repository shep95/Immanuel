"""Subdomain / domain / page discovery — including non-indexed, non-SEO sites.

Immanuel does not rely on search engines or SEO. It reaches pages three ways:
  1. Direct link-following from any fetched page (covers unindexed/deep pages).
  2. Registering every http(s) link (including subdomains) as a future source.
  3. Optional probing of common subdomains and common paths for a domain, so we
     find hosts that are not linked or indexed anywhere.

All of this is ordinary lawful HTTP GET to *public* hosts; robots.txt is still
honored by the fetcher/pipeline.
"""
from __future__ import annotations

from urllib.parse import urlparse

# Common subdomains worth probing (public, conventional).
COMMON_SUBDOMAINS = [
    "www", "blog", "news", "docs", "developer", "developers", "api", "m",
    "mobile", "app", "apps", "help", "support", "wiki", "forum", "community",
    "shop", "store", "media", "static", "cdn", "data", "archive", "about",
    "en", "kb", "status", "press", "research", "labs", "download", "downloads",
]

# Common paths worth probing on a domain root (non-SEO discovery aids).
COMMON_PATHS = [
    "/", "/sitemap.xml", "/feed", "/rss", "/rss.xml", "/atom.xml",
    "/index.xml", "/about", "/blog", "/news", "/api", "/docs",
]


def registrable_domain(host: str) -> str:
    """Best-effort registrable domain (naive; good enough for discovery)."""
    host = host.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    # handle a few common two-part TLDs
    two_part = {"co.uk", "org.uk", "ac.uk", "com.au", "co.jp", "co.nz", "com.br"}
    if ".".join(labels[-2:]) in two_part and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def expand_subdomains(domain: str, scheme: str = "https") -> list[str]:
    """Return candidate root URLs for common subdomains of a domain."""
    base = registrable_domain(domain)
    urls = [f"{scheme}://{base}/", f"{scheme}://www.{base}/"]
    for sub in COMMON_SUBDOMAINS:
        if sub == "www":
            continue
        urls.append(f"{scheme}://{sub}.{base}/")
    # de-dup preserving order
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def expand_paths(url: str) -> list[str]:
    """Return candidate URLs for common paths on a URL's origin."""
    p = urlparse(url)
    if not p.scheme or not p.netloc:
        return []
    origin = f"{p.scheme}://{p.netloc}"
    return [origin + path for path in COMMON_PATHS]


def candidate_sources_for(url: str) -> list[str]:
    """All discovery candidates for a seed URL: subdomains + common paths."""
    host = urlparse(url).netloc
    out: list[str] = []
    if host:
        out.extend(expand_subdomains(host))
    out.extend(expand_paths(url))
    seen, uniq = set(), []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq
