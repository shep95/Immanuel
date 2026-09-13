# 7. Acquisition Engine · 8. Connector System

## 7. Acquisition engine

**Purpose.** Turn authorized SOURCEs into acquired bytes, safely, politely, and
efficiently — with persistent job identity and full retry/backoff/circuit-breaking.

### 7.1 Components

| Component | Responsibility |
|-----------|----------------|
| Scheduler | Decides *when* each source is due (adaptive; see [`docs/…51`](27-mvp-roadmap.md)/[`51 Continuous crawling`](#) below). |
| Priority queue | Orders due jobs by priority + fairness (per-domain politeness). |
| Worker pool | Horizontally-scaled fetch workers, stateless. |
| Fetcher | Executes the connector-specific fetch. |
| HTTP client | Conditional requests, connection pooling, TLS verification. |
| API connectors | Typed clients for REST/GraphQL/feed endpoints. |
| File downloader | Streaming download to quarantine with size caps. |
| Stream processor | Bounded consumption of streaming/WebSocket sources where lawful. |
| Retry manager | Retry policy per error class. |
| Backoff manager | Exponential backoff + jitter; respects `Retry-After`. |
| Timeout manager | Connect/read/total timeouts. |
| Circuit breaker | Trips per-source/per-host on sustained failure. |
| Rate limiter | Token-bucket per source & per host (politeness). |
| Source health tracker | Feeds availability/latency back to scheduler & registry. |

### 7.2 Job lifecycle (persistent identity)

Every job has a durable `job_id` and is idempotent (keyed by `source_id` + planned
`content_hash`/etag window).

```
queued ─▶ assigned ─▶ fetching ─▶ downloaded ─▶ quarantined ─▶ validated ─▶ processed ─▶ completed
   │          │           │            │              │
   ├──────────┴───────────┴────────────┴──────────────┴────▶ failed
   │
   ├─▶ retrying   (transient error, within budget)
   ├─▶ deferred   (rate limit / politeness / not-yet-due)
   ├─▶ blocked    (policy: disallowed / requires authorization)
   ├─▶ expired    (source gone / permanently 4xx)
   └─▶ cancelled  (operator or superseded)
```

State transitions are recorded to the `job` table and emitted as
`acquisition.started` / `acquisition.completed` / `acquisition.failed` events.

### 7.3 Bandwidth optimization (see §52 requirement)

Before downloading, the fetcher attempts cheap change detection:

1. `If-None-Match` (ETag) and `If-Modified-Since` (Last-Modified).
2. HEAD request where the source supports it (compare `Content-Length`, `ETag`).
3. On 304 Not Modified → job completes with `unchanged`, no body stored, `last_seen`
   updated, scheduler notified (slow down).
4. On changed body → hash the payload; if `content_hash` equals the last stored object,
   record a duplicate observation (dedup L1) instead of a new raw object.
5. Delta detection for large text sources that expose ranges/diffs.

**Result:** unchanged content is not re-downloaded or re-stored when reliable change
detection exists.

### 7.4 Adaptive scheduling (statistical, non-AI) (see §51 requirement)

The scheduler learns each source's behavior with simple statistics — **no ML required**:

- Track inter-change interval samples `Δ₁…Δₙ` (time between observed content changes).
- Estimate the next-due interval as a smoothed statistic (e.g., EWMA of Δ, clamped to
  `[min_interval, max_interval]`), adjusted by:
  - failure rate (raise interval on repeated failures),
  - availability (back off unavailable sources),
  - priority (raise frequency for high-priority coverage gaps),
  - politeness caps (never exceed `rate_limit`).
- A source changing ~every 10 min is scheduled ~every 10 min; a source changing monthly
  is scheduled ~monthly. Bounds prevent runaway frequency.

```
next_crawl_at = now + clamp( EWMA(Δ) * failure_penalty * priority_factor,
                             min_interval(source_class),
                             max_interval(source_class) )
```

### 7.5 Politeness & rate limiting

- Token-bucket per `(source_id)` and per `(host)`; the stricter wins.
- Global concurrency cap per host regardless of how many sources share it.
- Honor `Crawl-delay` and `Retry-After`.
- Distinct, honest, contactable `User-Agent`.

### 7.6 Failure modes & recovery

- Transient (5xx, timeouts, connection reset) → retry with backoff (2s,4s,8s,16s… capped).
- Persistent 4xx (except 429) → `expired`/`blocked` as appropriate, source health decays.
- Circuit breaker open → defer all jobs for that host, probe with a single canary later.
- Worker crash mid-fetch → job returns to `queued` after visibility timeout; idempotency
  key prevents double-processing.
- Poison/oversize → capped download, moved to quarantine, never to raw lake until validated.

### 7.7 Security considerations

- SSRF guards (as in discovery); TLS verification always on (proxy CA bundle honored).
- Download size/time caps enforced at the stream level (fail fast on oversize).
- All acquired bytes are **untrusted** until validated in quarantine.

---

## 8. Universal connector system

**Principle:** *do not build one scraper for everything.* A **connector framework** with
a common interface lets every source type emit the same normalized `IngestionObject`.

### 8.1 Connector classes

`http` · `html` · `rest` · `graphql` · `rss` · `atom` · `sitemap` · `git` ·
`public_dataset` · `document_repository` · `object_storage` · `file_download` · `stream` ·
`websocket` (where legitimately accessible) · `custom`.

### 8.2 Standard connector interface [PROPOSED]

```python
class Connector(Protocol):
    connector_type: str
    def can_handle(self, source: Source) -> bool: ...
    def plan(self, source: Source, job: Job) -> FetchPlan:
        """Produce conditional-request headers, endpoints, pagination plan."""
    def fetch(self, plan: FetchPlan, limits: ResourceLimits) -> RawPayload:
        """Stream bytes to quarantine; enforce size/time caps; return metadata."""
    def to_ingestion(self, payload: RawPayload, source: Source, job: Job) -> IngestionObject:
        """Normalize connector-specific result into the universal IngestionObject."""
    def next_sources(self, payload: RawPayload) -> list[SourceCandidate]:
        """Optional: emit discovered sources (links, feed items, repo files)."""
    def healthcheck(self, source: Source) -> HealthReport: ...
```

### 8.3 Connector lifecycle

```
register ─▶ can_handle? ─▶ plan ─▶ fetch (→quarantine) ─▶ validate ─▶ to_ingestion ─▶ emit
                                                     └─ next_sources ─▶ discovery
```

### 8.4 The universal `IngestionObject`

Every connector, regardless of source type, emits this:

```json
{
  "ingestion_id": "ing_01J9...",
  "job_id": "job_01J9...",
  "source_id": "src_01J9...",
  "acquisition_id": "acq_01J9...",
  "fetched_at": "2026-09-13T12:00:05Z",
  "connector_type": "html",
  "raw_ref": "s3://immanuel-raw/sha256/ab/cd/abcd...bin",
  "content_hash": "sha256:abcd...",
  "declared_media_type": "text/html; charset=utf-8",
  "size_bytes": 48213,
  "transport_metadata": { "status": 200, "etag": "\"a1b2\"", "last_modified": "..." },
  "authorization_state": "allowed",
  "provenance": { "source_version": "srcv_...", "pipeline_version": "acq@1.4.2" }
}
```

Downstream stages never need to know *how* it was fetched — only this contract.

### 8.5 Per-connector notes

- **git**: shallow clone / fetch of public repos; treat repo as a tree of files; emit one
  IngestionObject per file (or a manifest) with commit provenance.
- **rest/graphql**: typed pagination plan; store raw responses; respect documented rate
  limits and only use publicly-enabled introspection.
- **dataset/object_storage**: enumerate public listings (DCAT, bucket indexes) only where
  listing is public; stream large files with caps.
- **stream/websocket**: bounded, time-boxed consumption; never a persistent private feed.

### 8.6 Extensibility

New source types are added by implementing `Connector` and registering it — **no change to
the acquisition engine, queues, or downstream planes.** This is the primary
"replace/upgrade a component without redesign" seam on the acquisition side.
