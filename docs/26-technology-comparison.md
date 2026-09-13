# 50. Technology Comparison & Selection · 69. Architecture Tradeoff Analysis

**Principle.** *Do not blindly choose technologies.* For each subsystem: candidate options,
selection criteria, and — for recommendations — why, what it handles, what it does not,
scaling limits, failure modes, and migration path.

## 69. Architecture-shape tradeoffs

### Deployment shape

| Option | Advantages | Disadvantages | Failure modes | Verdict |
|--------|-----------|---------------|---------------|---------|
| Monolith | simple, fast to start | poor fault isolation, hard to scale planes independently | one bug stalls all | ❌ |
| Modular monolith | simple deploy, clear modules | shared fate at runtime | resource contention | ✅ **MVP** |
| Microservices | independent scale/deploy | operational overhead, distributed-systems complexity | cascading failures if coupled | ⚠️ overkill early |
| **Distributed pipeline of modular services** | scale/fault-isolate per plane; queue-decoupled | needs good queue/event discipline | mitigated by DLQ/backpressure | ✅ **target** |

**Recommendation:** start as a **modular monolith** (MVP), evolve into a **distributed
pipeline of modular services** (target). Not fine-grained microservices unless a plane
genuinely needs it.

### Database shape

| Option | Strengths | Weaknesses | Verdict |
|--------|-----------|-----------|---------|
| Relational only | transactions, integrity, joins | graph traversal + full-text weak at scale | ✅ core SoR |
| Document only | flexible schemas | weak cross-entity integrity | partial (documents) |
| Graph only | traversal | poor for bulk/relational SoR, ops maturity varies | partial (graph index) |
| **Hybrid (polyglot)** | right tool per category | more moving parts | ✅ **chosen** (§35) |

### Search & queue shape

| Question | Options | Verdict |
|----------|---------|---------|
| Single index vs specialized indexes | one big index / per-facet indexes | **specialized indexes** (§28) |
| Centralized vs distributed queues | one broker / partitioned per-stage | **partitioned per-stage** (§34) |

For each, weigh: advantages · disadvantages · failure modes · cost · complexity ·
scalability · operational burden — then choose by **requirements, not fashion**.

## 50. Per-subsystem candidate technologies

> Recommendations are **[PROPOSED]**; equivalents are acceptable. Selection criteria:
> maturity, operational burden, scaling ceiling, failure behavior, ecosystem, cost, and
> avoiding lock-in where the component is a system of record.

### Object storage (raw lake, cold tiers)
- **Candidates:** S3, GCS, Azure Blob, MinIO (self-host), Ceph.
- **Recommend:** S3-compatible (MinIO for on-prem). *Handles:* immutable, content-addressed,
  WORM (Object Lock), lifecycle tiering, huge scale. *Doesn't:* query/search. *Scale limit:*
  effectively unbounded; watch request/prefix hot-spots (mitigated by hash fan-out).
  *Migration:* S3 API portability keeps lock-in low.

### Relational DB (source registry, jobs, claims, provenance, metadata, audit)
- **Candidates:** PostgreSQL, MySQL, CockroachDB, Cloud Spanner.
- **Recommend:** **PostgreSQL** (JSONB, strong SQL, PITR, partitioning; extensions for
  full-text, trigram, vector-optional). *Doesn't:* horizontal write scaling natively →
  partition/shard or move to CockroachDB/Spanner at stage 3. *Failure:* single-primary →
  replicas + PITR. *Migration:* Postgres-wire compatibility (CockroachDB) eases growth.

### Document store (normalized documents at large scale)
- **Candidates:** PostgreSQL JSONB (small), MongoDB, Couchbase.
- **Recommend:** start in PostgreSQL JSONB; move hot document bodies to object storage +
  metadata in Postgres; adopt a document DB only if access patterns demand it.

### Graph database (knowledge graph)
- **Candidates:** PostgreSQL adjacency (small), Neo4j, JanusGraph, Dgraph, TigerGraph,
  Amazon Neptune.
- **Recommend:** PostgreSQL adjacency for MVP; migrate the **hot graph** to a dedicated
  engine (Neo4j/JanusGraph) at scale, keeping relational adjacency as the SoR so the graph
  DB is a rebuildable index. *Watch:* traversal DoS (budgets §66), write amplification.

### Search engine
- **Candidates:** OpenSearch/Elasticsearch, Apache Solr, Vespa, Typesense/Meilisearch (small),
  Tantivy/Lucene (embedded).
- **Recommend:** **OpenSearch/Elasticsearch family** (faceting, scaling, ecosystem). Vespa
  if tight ranking + optional vectors later. *Doesn't:* be a system of record → always
  rebuildable from SoR.

### Queue / event bus
- **Candidates (bus):** Kafka, Redpanda, Pulsar. **(work queue):** SQS, RabbitMQ, Redis
  Streams, NATS JetStream.
- **Recommend:** **Kafka/Redpanda** for the durable, replayable event bus; a work-queue
  (SQS-like or RabbitMQ) for job queues with visibility timeouts + DLQ. *Failure:*
  replication factor ≥ 3; consumers idempotent.

### Cache
- **Recommend:** **Redis** (query/facet cache, rate-limit counters, sessions). Ephemeral;
  never a system of record.

### Scheduler
- **Recommend:** custom adaptive scheduler (statistical, §51) backed by Postgres +
  leader election; or a workflow engine (Temporal) for complex orchestration at scale.

### Container runtime / orchestration
- **Recommend:** containers + **Kubernetes** (HPA per worker pool; node pools per risk
  class — untrusted-processing nodes isolated). Nomad is a lighter alternative.

### Observability
- **Recommend:** Prometheus/VictoriaMetrics (metrics), Loki/ELK (logs), OpenTelemetry +
  Tempo/Jaeger (traces), Grafana (dashboards), Alertmanager (alerts).

### API gateway / CDN
- **Recommend:** an API gateway (Kong/Envoy/managed) for authn/rate-limit/routing; a CDN in
  front of the public read API/frontend for cacheable responses.

### Frontend communication
- **Recommend:** REST (OpenAPI) for stability + a BFF; GraphQL optional at the BFF for
  flexible UI queries (with complexity limits, §62).

### Sandboxing (untrusted processing)
- **Recommend:** gVisor/Firecracker microVMs or hardened containers (seccomp, dropped caps,
  no egress, cgroup limits) on dedicated node pools.

## Selection summary (target)

```
Object store: S3-compatible · Relational: PostgreSQL (→shard/CockroachDB) ·
Graph: PG adjacency → Neo4j/JanusGraph · Search: OpenSearch/ES ·
Bus: Kafka/Redpanda · Queue: RabbitMQ/SQS-like · Cache: Redis ·
Orchestration: Kubernetes · Observability: Prometheus+OTel+Grafana ·
Sandbox: gVisor/Firecracker
```

Every choice preserves the invariant that **systems of record avoid hard lock-in** and
**derived stores are freely replaceable/rebuildable**.
