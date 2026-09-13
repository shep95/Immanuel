# 33. Event Architecture · 34. Queue Architecture

> (Numbering note: the required output structure places "event architecture" at §33 and
> "queues" at §34. This document covers both the internal **event bus** and the **work
> queues**; the Discord layer is in [`docs/15-discord.md`](15-discord.md).)

## Event bus (internal event system)

**Purpose.** A durable, ordered-per-key event log that decouples producers from consumers
and lets many subsystems react to the same fact.

### Event catalog

```
source.discovered · source.updated · source.failed
document.acquired · document.parsed · document.normalized · document.deduplicated · document.compressed
entity.created · claim.created · relationship.created
contradiction.detected
pattern.created · pattern.updated
index.updated
discord.notification_required
system.failure · security.event
```

### Common event envelope

```json
{
  "event_id": "evt_01J9...",
  "type": "claim.created",
  "occurred_at": "2026-09-13T12:01:00Z",
  "producer": "extractor.claim@2.3.1",
  "partition_key": "domain:physics",     // ordering + routing
  "idempotency_key": "claim_...:v1",
  "schema_version": "1.0",
  "payload": { /* type-specific; see docs/28-schemas.md */ },
  "provenance_event_id": "prov_...",
  "trace_id": "trace_..."
}
```

### Example payloads

```json
// source.discovered
{ "source_id": "src_...", "source_type": "rss", "canonical_location": "https://…/feed",
  "discovery_method": "sitemap", "authorization_state": "unknown" }

// document.normalized
{ "document_id": "doc_...", "object_id": "obj_...", "format": "pdf",
  "language": "en", "normalization_version": "norm@3.2.0" }

// contradiction.detected
{ "contradiction_id": "contra_...", "claims": ["claim_a","claim_b"],
  "subject": "entity:material_x", "outcome": "unresolved" }
```

Full event schemas: [`docs/28-schemas.md`](28-schemas.md).

### Bus properties

- **Durable & replayable** — consumers can replay from an offset (rebuilds, new consumers).
- **Ordered per partition key** — e.g., per source or per domain.
- **At-least-once delivery** — consumers are idempotent (idempotency keys).
- **Schema-versioned** — payloads evolve via additive, versioned schemas (contract tests, §47).

### Producers/consumers (examples)

| Event | Produced by | Consumed by |
|-------|-------------|-------------|
| `document.normalized` | normalization svc | dedup, metadata, extraction, indexing |
| `claim.created` | claim extractor | contradiction engine, graph, indexing, Discord GW |
| `index.updated` | index workers | search cache invalidation, admin dashboard |
| `security.event` | any service | security monitor, Discord `#security-alerts` |

---

## Queue architecture (work queues)

**Purpose.** Distribute work to horizontally-scaled workers with retries, ordering-where-
needed, and backpressure. Queues are for *work*; the event bus is for *facts*. (They may
share a broker but are logically distinct.)

### Persistent queues (one per pipeline stage)

discovery · acquisition · parsing · normalization · deduplication · compression ·
metadata · entity_extraction · claim_extraction · graph_construction · indexing ·
discord_distribution · pattern_processing.

### Queue properties

| Property | Design |
|----------|--------|
| Priority | Multiple priority classes per queue; high-priority sources jump ahead fairly. |
| Retry | Per-message retry with exponential backoff + jitter; capped attempts. |
| Dead-letter queue (DLQ) | After max attempts → DLQ with full context for inspection/replay. |
| Visibility timeout | In-flight messages hidden; re-delivered if not acked (crash safety). |
| Idempotency | Idempotency keys + content-hash checks → safe re-delivery. |
| Job status | Persisted in the `job` table (queued/…/completed/failed). |
| Backpressure | Bounded queue depth; producers slow when consumers lag (protects stores). |

### Job/message shape

```json
{
  "job_id": "job_01J9...",
  "stage": "parsing",
  "priority": 5,
  "payload": { "ingestion_id": "ing_...", "raw_ref": "s3://…" },
  "attempts": 0,
  "max_attempts": 6,
  "idempotency_key": "ing_...:parse:v1",
  "enqueued_at": "2026-09-13T12:00:10Z",
  "visible_at": "2026-09-13T12:00:10Z"
}
```

### Idempotency & exactly-once *effects*

Delivery is at-least-once; **effects** are exactly-once because:

- Output object IDs derive from `content_hash` + job identity → duplicate work upserts the
  same row (no duplicate knowledge).
- Provenance `inputs_hash` detects already-produced outputs.
- Transaction boundaries wrap "write output + ack message" where the store supports it;
  otherwise the outbox pattern is used.

### Failure modes, observability, recovery

- **Poison message** → DLQ after cap; alert; operator replays after fix.
- **Consumer crash** → visibility timeout re-delivers; idempotency prevents dupes.
- **Broker outage** → producers apply backpressure; nothing acked-but-lost (durable).
- **Observability:** per-queue `queue_depth`, `oldest_message_age`, `dlq_depth`,
  `retry_rate`, `processing_latency_ms`, `throughput`.
- **Recovery:** DLQs are replayable; the event log lets consumers rebuild from an offset.
