# 6. Source Discovery

**Purpose.** Continuously discover candidate public sources, register them canonically,
deduplicate them, and prioritize them for acquisition — without acquiring restricted or
private material.

## 6.1 What it discovers

Websites · domains · subdomains · web pages · sitemaps · RSS/Atom feeds · public REST
APIs · GraphQL endpoints · public datasets · documentation · repositories · public file
indexes · public archives · public data portals · public cloud objects · public research
repositories · public code repositories · public metadata catalogs · public media
indexes · public machine-readable feeds.

## 6.2 Sub-components

| Sub-component | Responsibility |
|---------------|----------------|
| Seed management | Curated & operator-supplied seeds; seed lists per source class. |
| URL discovery | Extract candidate URLs from fetched pages, feeds, sitemaps. |
| Link extraction | Parse anchors/links from HTML/markdown/docs (respecting `rel=nofollow` as a *signal*, `robots` as a *rule*). |
| Sitemap discovery | `robots.txt` → `Sitemap:` directives; `/sitemap.xml`; sitemap indexes. |
| Feed discovery | `<link rel="alternate" type="application/rss+xml">`, well-known feed paths. |
| Repository discovery | Public repo catalogs/APIs; org/user public repo listings. |
| Dataset discovery | Data portal catalogs (DCAT), dataset landing pages, well-known dataset registries. |
| API discovery | OpenAPI/Swagger docs, GraphQL introspection *where publicly enabled*, `.well-known` endpoints. |
| Source expansion | Controlled breadth expansion from a source's link neighborhood. |
| Duplicate source detection | Canonicalization + host/content signals to avoid re-registering the same source. |
| Source prioritization | Compute a priority score from freshness, authority-neutral signals, and coverage gaps. |
| Source health tracking | Track availability, latency, failure counts over time. |

## 6.3 Discovery flow

```
seeds ──▶ candidate URLs ──▶ canonicalize ──▶ policy pre-check (allowed?) ──▶
   ├─ duplicate? ──▶ merge into existing SOURCE (add discovery evidence)
   └─ new ──▶ register SOURCE (status=discovered) ──▶ enqueue authorization eval
```

Discovery **never** acquires body content beyond what is required to discover more
sources and only from locations already permitted (e.g., a public sitemap). The policy
engine ([`docs/19-security-privacy-policy.md`](19-security-privacy-policy.md)) gates the
transition from *discovered* to *authorized*.

## 6.4 Canonical `SOURCE` object

```json
{
  "source_id": "src_01J9Z8...",            // ULID/UUID, stable identity
  "source_type": "website|api|graphql|rss|atom|sitemap|git|dataset|doc_repo|object_store|feed|file_index|archive|portal|media_index|custom",
  "canonical_location": "https://example.org/data/",
  "domain": "example.org",
  "protocol": "https",
  "discovery_method": "seed|link|sitemap|feed|repo_catalog|dataset_catalog|api_doc|expansion|operator",
  "discovery_timestamp": "2026-09-13T12:00:00Z",
  "first_seen": "2026-09-13T12:00:00Z",
  "last_seen": "2026-09-13T12:00:00Z",
  "last_modified": "2026-09-10T08:00:00Z",  // from source (Last-Modified/feed)
  "etag": "\"a1b2c3\"",
  "content_hash": "sha256:...",             // last observed representation hash
  "crawl_policy": {
    "respect_robots": true,
    "max_depth": 3,
    "allowed_paths": ["/data/"],
    "disallowed_paths": ["/private/"],
    "user_agent": "ImmanuelBot/1.0 (+https://.../botinfo)"
  },
  "authorization_state": "allowed|restricted|requires_authorization|temporarily_unavailable|disallowed|unknown",
  "rate_limit": { "requests_per_min": 20, "concurrency": 2, "crawl_delay_s": 3 },
  "crawl_frequency": "adaptive|PT10M|P1D|P30D",
  "priority": 0.74,                          // 0..1
  "availability": 0.998,                      // rolling
  "failure_count": 0,
  "provenance": { "discovered_from": "src_...", "evidence": ["sitemap", "link"] },
  "status": "discovered|authorized|active|paused|blocked|retired"
}
```

**Keys/indexes:** PK `source_id`; unique on `(domain, canonical_location)` after
canonicalization; indexes on `status`, `authorization_state`, `priority`,
`next_crawl_at` (derived).

## 6.5 Canonicalization rules [PROPOSED]

- Lowercase scheme/host; strip default ports; resolve `.`/`..`; sort query params by an
  allowlist (drop known tracking params); normalize trailing slashes per source class;
  apply `rel=canonical` and `og:url` when present and same-origin.
- Maintain a **host → canonical host** table for known aliases (e.g., `www` vs apex),
  built only from observed redirects, never guessed.

## 6.6 Prioritization signals (authority-neutral)

Priority is deliberately **not** "authority = truth". Signals:

- Coverage gap (domains/subdomains under-represented in the corpus).
- Observed change frequency (volatile sources that we can lawfully track).
- Discovery corroboration (independently discovered via multiple methods).
- Structural richness (sitemaps/feeds/APIs present → cheap, reliable acquisition).
- Health/availability (reliable sources score higher operationally).

## 6.7 State, failure modes, observability

- **State:** the SOURCE registry (PostgreSQL) is the source of truth; discovery emits
  `source.discovered` / `source.updated` events.
- **Failure modes:** discovery loops (cycle detection via visited-set + depth caps);
  source explosion (per-domain and global registration budgets); alias thrash (canonical
  host table + cooldown); poisoned discovery (a source injecting thousands of fake links →
  per-source expansion budget + reputation decay).
- **Observability:** metrics `sources_discovered_total`, `sources_registered_total`,
  `discovery_dedup_ratio`, `expansion_budget_exhausted_total`, `discovery_queue_depth`.
- **Scaling:** discovery workers are stateless; shard by domain hash; the visited-set is a
  scalable KV/Bloom structure. See [`docs/18-scalability.md`](18-scalability.md).
- **Recovery:** discovery is fully replayable from seeds + fetched sitemaps/feeds in the
  raw lake; the registry can be rebuilt from provenance events.

## 6.8 Security considerations

- Discovery output is untrusted input: URLs are validated (scheme allowlist, no
  `file:`/`ftp:` unless explicitly enabled, SSRF protections — block link-local, RFC1918,
  metadata IPs unless whitelisted).
- Discovery never follows a link that resolves to internal infrastructure (SSRF guard).
