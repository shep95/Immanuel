"""Domain firehose via Certificate Transparency (crt.sh).

Every publicly-trusted TLS certificate is logged to public Certificate
Transparency logs. Querying them surfaces a continuous stream of domains and
subdomains registered across the whole web — the closest lawful approximation to
"find every www.domain out there" without guessing or port-scanning.

We turn each discovered hostname into candidate root URLs (https + www) that the
crawler then treats as normal sources (robots.txt still respected). This is
best-effort: crt.sh can be slow or rate-limit, so failures are swallowed.

Enable with ENABLE_CT_DISCOVERY=true. It is OFF by default because it can
discover domains extremely fast — far more than a single node can crawl.
"""
from __future__ import annotations

import json

import httpx

CRT_SH = "https://crt.sh/"


def parse_ct_domains(payload: str, limit: int = 200) -> list[str]:
    """Parse a crt.sh JSON response into a de-duplicated list of hostnames."""
    try:
        rows = json.loads(payload)
    except Exception:
        return []
    seen, out = set(), []
    for row in rows:
        name = (row.get("name_value") or "") if isinstance(row, dict) else ""
        for host in name.splitlines():
            host = host.strip().lower().lstrip("*.")
            if not host or " " in host or "." not in host:
                continue
            if host in seen:
                continue
            seen.add(host)
            out.append(host)
            if len(out) >= limit:
                return out
    return out


def hosts_to_urls(hosts: list[str]) -> list[str]:
    urls: list[str] = []
    for h in hosts:
        urls.append(f"https://{h}/")
        if not h.startswith("www."):
            urls.append(f"https://www.{h}/")
    return urls


async def fetch_domain_batch(client: httpx.AsyncClient, query: str = "%",
                             limit: int = 200) -> list[str]:
    """Pull a batch of recently-logged hostnames from crt.sh.

    `query` is a crt.sh identity match; "%" is the broadest wildcard. Returns
    candidate root URLs (https + www variants).
    """
    params = {"q": query, "output": "json", "limit": str(min(limit * 3, 1000))}
    try:
        resp = await client.get(CRT_SH, params=params, timeout=40.0)
        resp.raise_for_status()
        hosts = parse_ct_domains(resp.text, limit=limit)
    except Exception:
        return []
    return hosts_to_urls(hosts)
