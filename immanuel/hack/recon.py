"""Deterministic, non-AI reconnaissance — the always-works /hack engine.

Observational only: it looks at what a target already tells anyone who visits
(response headers, HTML, robots/sitemap, exposed secrets). No exploitation, no
payloads, no auth bypass — findings are defensive posture, matching Immanuel's
existing senior/elite silent-audit lens. Reuses the crawler's Fetcher, extract,
and secret scanner so it stays consistent with the rest of the system.
"""
from __future__ import annotations

from urllib.parse import urlparse

from ..crawler.extract import extract
from ..crawler.fetcher import Fetcher
from ..crawler.robots import RobotsCache
from ..crawler.secrets import scan_secrets

# Security response headers we expect a hardened site to set.
_SEVERITY_ORDER = {"high": 3, "medium": 2, "low": 1, "info": 0}


def normalize_target(target: str) -> str:
    """Turn a bare domain / ip into a URL; leave URLs untouched."""
    t = (target or "").strip()
    if t.startswith(("http://", "https://")):
        return t
    return "https://" + t.lstrip("/")


def _registrable(host: str) -> str:
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _header_findings(url: str, headers: dict) -> list[dict]:
    h = {k.lower(): v for k, v in (headers or {}).items()}
    https = url.startswith("https://")
    csp = h.get("content-security-policy", "")
    out: list[dict] = []

    if https and "strict-transport-security" not in h:
        out.append({"severity": "medium", "kind": "missing-header",
                    "title": "Missing HSTS (Strict-Transport-Security)",
                    "detail": "No HSTS header — connections can be downgraded to HTTP."})
    if "content-security-policy" not in h:
        out.append({"severity": "low", "kind": "missing-header",
                    "title": "Missing Content-Security-Policy",
                    "detail": "No CSP — reduces defense-in-depth against XSS/injection."})
    if "x-frame-options" not in h and "frame-ancestors" not in csp.lower():
        out.append({"severity": "low", "kind": "clickjacking",
                    "title": "No clickjacking protection",
                    "detail": "Neither X-Frame-Options nor CSP frame-ancestors is set."})
    if h.get("x-content-type-options", "").lower() != "nosniff":
        out.append({"severity": "info", "kind": "missing-header",
                    "title": "Missing X-Content-Type-Options: nosniff",
                    "detail": "MIME-sniffing is not disabled."})
    if "referrer-policy" not in h:
        out.append({"severity": "info", "kind": "missing-header",
                    "title": "Missing Referrer-Policy",
                    "detail": "Referrer information may leak to third parties."})
    if "permissions-policy" not in h:
        out.append({"severity": "info", "kind": "missing-header",
                    "title": "Missing Permissions-Policy",
                    "detail": "Browser features are not explicitly restricted."})

    # Tech / version disclosure via headers.
    for hdr in ("server", "x-powered-by", "x-aspnet-version", "x-generator"):
        if h.get(hdr):
            out.append({"severity": "info", "kind": "tech-disclosure",
                        "title": f"Technology disclosure: {hdr}",
                        "detail": f"{hdr}: {h[hdr]}", "evidence": h[hdr]})

    # Cookie flags.
    cookie = h.get("set-cookie", "")
    if cookie:
        low = cookie.lower()
        if "secure" not in low:
            out.append({"severity": "low", "kind": "cookie-flags",
                        "title": "Cookie set without Secure flag",
                        "detail": "A Set-Cookie is missing the Secure attribute."})
        if "httponly" not in low:
            out.append({"severity": "low", "kind": "cookie-flags",
                        "title": "Cookie set without HttpOnly flag",
                        "detail": "A Set-Cookie is missing the HttpOnly attribute."})
    return out


def _tech_fingerprint(headers: dict, meta: dict) -> dict:
    h = {k.lower(): v for k, v in (headers or {}).items()}
    tech = {}
    for hdr in ("server", "x-powered-by", "x-aspnet-version"):
        if h.get(hdr):
            tech[hdr] = h[hdr]
    if meta.get("generator"):
        tech["generator"] = meta["generator"]
    return tech


async def recon(config, target: str, *, fetcher=None, robots=None,
                on_line=None) -> dict:
    """Run deterministic recon on ``target``. Returns a report dict.

    A Fetcher/RobotsCache are created if not injected (tests inject fakes).
    """
    url = normalize_target(target)
    host = urlparse(url).netloc
    reg = _registrable(host)

    async def _emit(msg: str) -> None:
        if on_line:
            try:
                await on_line(msg)
            except Exception:
                pass

    owns_fetcher = fetcher is None
    if owns_fetcher:
        fetcher = Fetcher(config.user_agent,
                          timeout=config.request_timeout_seconds,
                          max_bytes=config.max_content_bytes,
                          per_domain_delay=config.crawl_delay_seconds)
        await fetcher.__aenter__()
    if robots is None:
        robots = RobotsCache(config.user_agent, respect=config.respect_robots)

    findings: list[dict] = []
    secrets_seen: set[str] = set()
    secret_findings: list[dict] = []
    pages: list[dict] = []
    tech: dict = {}
    final_url = url
    uncensored = getattr(config, "secrets_uncensored", False)

    try:
        await _emit(f"recon: fetching {url}")
        root = await fetcher.fetch(url)
        final_url = getattr(root, "final_url", url) or url
        if not root.ok and not root.body:
            findings.append({"severity": "info", "kind": "unreachable",
                             "title": f"Target returned {root.status or 'no response'}",
                             "detail": root.error or "no body"})
        else:
            findings.extend(_header_findings(final_url, getattr(root, "headers", {})))
            ex = extract(final_url, root.content_type, root.body)
            tech = _tech_fingerprint(getattr(root, "headers", {}), ex.meta)
            # secret scan on visible body + inline code snippets
            blob = ex.text + "\n" + "\n".join(
                c.get("snippet", "") for c in ex.code if c.get("snippet"))
            for s in scan_secrets(blob, keep_raw=uncensored):
                d = s.as_dict(include_raw=uncensored)
                if d["fingerprint"] in secrets_seen:
                    continue
                secrets_seen.add(d["fingerprint"])
                secret_findings.append(d)
            pages.append({"url": final_url, "status": root.status,
                          "title": ex.title, "links": len(ex.links)})

            # bounded same-host follow (hop depth) for a wider surface + secrets
            if config.hack_recon_hops > 0:
                budget = max(0, config.hack_max_recon_pages - 1)
                seen = {final_url}
                for link in ex.links:
                    if budget <= 0:
                        break
                    if _registrable(urlparse(link).netloc) != reg or link in seen:
                        continue
                    seen.add(link)
                    budget -= 1
                    try:
                        if not await robots.allowed(link, fetcher.client):
                            continue
                    except Exception:
                        pass
                    r = await fetcher.fetch(link)
                    if not r.ok or not r.body:
                        continue
                    px = extract(r.final_url or link, r.content_type, r.body)
                    for s in scan_secrets(px.text, keep_raw=uncensored):
                        d = s.as_dict(include_raw=uncensored)
                        if d["fingerprint"] in secrets_seen:
                            continue
                        secrets_seen.add(d["fingerprint"])
                        d["page"] = r.final_url or link
                        secret_findings.append(d)
                    pages.append({"url": r.final_url or link, "status": r.status,
                                  "title": px.title, "links": len(px.links)})

        # robots.txt / sitemap / security.txt presence (info-level surface)
        for probe, label in ((f"https://{host}/robots.txt", "robots.txt"),
                             (f"https://{host}/sitemap.xml", "sitemap.xml"),
                             (f"https://{host}/.well-known/security.txt",
                              "security.txt")):
            try:
                pr = await fetcher.fetch(probe)
            except Exception:
                continue
            if pr.ok and pr.body:
                findings.append({"severity": "info", "kind": "surface",
                                 "title": f"{label} present",
                                 "detail": probe})
    finally:
        if owns_fetcher:
            await fetcher.__aexit__(None, None, None)

    # fold secrets into findings (exposed secrets are the highest-value signal)
    for d in secret_findings:
        findings.append({
            "severity": d.get("severity") or "high",
            "kind": "exposed-secret",
            "title": f"Exposed secret: {d['type']} ({d.get('provider', '?')})",
            "detail": d.get("context", ""),
            "provider": d.get("provider"),
            "unlocks": d.get("unlocks"),
            "masked": d.get("masked"),
            "raw": d.get("raw"),          # present only when SECRETS_UNCENSORED
            "page": d.get("page", final_url),
        })

    findings.sort(key=lambda f: _SEVERITY_ORDER.get(f.get("severity"), 0),
                  reverse=True)
    counts: dict[str, int] = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    summary = (f"{len(pages)} page(s) · {len(secret_findings)} secret(s) · "
               + ", ".join(f"{n} {sev}" for sev, n in counts.items()) if findings
               else f"{len(pages)} page(s) · no notable findings")

    return {
        "engine": "recon",
        "status": "completed",
        "target": target,
        "final_url": final_url,
        "pages": len(pages),
        "pages_detail": pages,
        "secrets_count": len(secret_findings),
        "tech": tech,
        "findings": findings,
        "counts": counts,
        "summary": summary,
    }
