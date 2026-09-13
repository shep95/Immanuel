# 36. Scalability · 54. Distributed Processing · 55. Idempotency

## 36. Scalability

Immanuel is designed to scale **horizontally at every plane**. Each stage is an
independently-scalable pool of stateless (or shard-local) workers fed by durable queues.

### 36.1 Scale stages

| Stage | Sources | Design posture |
|-------|---------|----------------|
| 1 | thousands | Single-region; modular monolith-ish deploy is acceptable; PostgreSQL for graph & documents; one search cluster. |
| 2 | millions | Full service separation; sharded queues; dedicated search cluster; graph moved toward dedicated engine; read replicas. |
| 3 | tens–hundreds of millions | Multi-region raw lake; sharded/partitioned stores; graph DB clustered; index tiering; aggressive dedup/cold-tiering. |
| 4 | extreme | Cellular architecture (independent cells by domain/region); federation of indexes; capacity planning + admission control. |

### 36.2 Per-stage dimensions

For each stage, plan: crawler workers · queue capacity · storage · database requirements ·
indexing · network bandwidth · processing throughput · expected latency · failure handling.

| Dimension | Stage 1 | Stage 2 | Stage 3 | Stage 4 |
|-----------|---------|---------|---------|---------|
| Crawler workers | 10s | 100s | 1000s | 10,000s (multi-region) |
| Queue capacity | single broker | partitioned topics | partitioned + tiered | federated brokers per cell |
| Raw storage | TBs | 100s TB | PBs | 10s PB, multi-region |
| Relational DB | single primary + replica | partitioned + replicas | sharded (by source/domain) | per-cell shards |
| Graph | PostgreSQL adjacency | graph DB single cluster | graph DB clustered/sharded | per-cell subgraphs + federation |
| Search | 1 cluster | dedicated cluster | sharded + tiered indexes | federated per cell/domain |
| Bandwidth | modest | high; regional egress mgmt | very high; peering/CDN | multi-region backbone |
| Throughput | docs/min | docs/sec | 1000s docs/sec | 10,000s docs/sec |
| Latency (search p95) | <300ms | <300ms | <500ms | <500ms (regional) |
| Failure handling | retries+DLQ | + circuit breakers | + cell isolation | + regional failover |

### 36.3 Architectural changes across stages

- **1→2:** split the modular deploy into per-plane services; introduce dedicated search
  cluster; add read replicas; partition queues by domain/host.
- **2→3:** shard relational stores; adopt a dedicated graph engine; multi-region raw lake;
  index tiering (hot/warm indexes); scheduler becomes distributed with global politeness
  coordination.
- **3→4:** move to **cells** (self-contained deployments per domain/region) to bound blast
  radius and coordination cost; federate search/graph across cells; add admission control
  to shed load gracefully.

### 36.4 Bottleneck order (first things to break) [ASSUMED]

1. Politeness-bounded crawl throughput (per-host limits) — mitigated by breadth (more
   sources), not by hammering hosts.
2. Graph write amplification & traversal cost — mitigated by graph engine + budgets.
3. Search indexing lag under write bursts — mitigated by backpressure + more index workers.
4. Relational hot tables (jobs, claims) — mitigated by partitioning/sharding.

See the full audit in [`docs/31-final-architecture.md`](31-final-architecture.md) and the
50 failure modes in [`docs/30-foreseeable-problems.md`](30-foreseeable-problems.md).

---

## 54. Distributed processing

- **Independently scalable worker pools:** crawler · parser · document · media · graph ·
  index workers — each scales on its own signal (queue depth/lag).
- **Fault isolation:** one pool failing degrades only its stage; queues buffer upstream
  work; downstream reads keep serving. A parser crash quarantines one object; the crawler
  and search API are unaffected.
- **Shard-local where needed:** graph/index workers may be shard-affine; crawler/parser
  workers are fully stateless.
- **No single point of failure** in the data path: brokers, stores, and gateways are
  replicated; the scheduler is leader-elected with standbys.

---

## 55. Idempotency

Every processing operation is **safely repeatable** — required because delivery is
at-least-once and workers can crash mid-operation.

### Mechanisms

- **Object IDs** derived from `content_hash` (+ lineage path for archive children).
- **Content hashes** as natural dedup/idempotency keys.
- **Job IDs** + **idempotency keys** per stage (`ing_…:parse:v1`).
- **Transaction boundaries** wrapping "produce output + record provenance + ack" where the
  store allows; otherwise the **outbox** pattern.
- **Provenance `inputs_hash`** lets a worker detect "this output already exists" and skip.

### Guarantee (worked example)

> A worker parses a document, writes the normalized doc, then crashes **before** acking the
> queue. The message is re-delivered. The worker recomputes the deterministic
> `document_id` from the raw `content_hash` + `normalization_version`, sees the row already
> exists (same `inputs_hash`), and **upserts identically** instead of creating a duplicate.
> Net effect: exactly-once knowledge, at-least-once delivery.
