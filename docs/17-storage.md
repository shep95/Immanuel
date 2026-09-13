# 35. Storage Architecture · 38. Hot/Warm/Cold Tiers

**Principle.** *Do not force everything into one database.* Use **polyglot persistence** —
each data category in the store that fits its access pattern, with the raw lake + provenance
as the durable backbone that makes everything else rebuildable.

## 35. Storage architecture

### 35.1 Store-by-data-category

| Data category | Store | Why |
|---------------|-------|-----|
| Raw objects | Object storage (S3-compatible), content-addressed, immutable | Cheap, durable, WORM, huge scale. |
| Normalized documents & structure trees | PostgreSQL JSONB (small) → document store (large) | Semi-structured, queried by id/facets. |
| Metadata | Relational (PostgreSQL) | Structured, integrity-checked, joined with sources/claims. |
| Structured records (datasets) | Columnar (Parquet in object store) + catalog in relational | Analytical scans, columnar compression. |
| Knowledge graph | Adjacency tables in PostgreSQL (small) → graph DB (large) | Traversal; relational copy stays system of record. |
| Search indexes | Search engine (OpenSearch/Elasticsearch family) | Inverted/faceted retrieval; rebuildable. |
| Time series (metrics) | TSDB (Prometheus/VictoriaMetrics) | Operational metrics. |
| Audit logs | Append-only store (relational + object archive) | Tamper-evident, immutable, retained. |
| Job state | PostgreSQL | Transactional job lifecycle. |
| Configuration | PostgreSQL + versioned config store | Hot-reloadable, audited. |
| Pattern library | PostgreSQL (records) + object store (artifacts) | Governed, versioned (§42/§47). |
| Cache | Redis | Hot queries, sessions, rate-limit counters. |
| Event log | Kafka/Redpanda (retained) | Durable, replayable facts. |

### 35.2 System-of-record vs derived (invariant)

- **Systems of record:** raw lake, source registry, jobs, claims, provenance, audit,
  pattern library, config.
- **Derived / rebuildable:** search indexes, graph store (as index), caches, columnar
  dataset copies, Discord delivery state.

If a derived store is lost, it is **reconstructed** from systems of record + provenance
(§46). This bounds blast radius and simplifies scaling (derived stores can be resharded/
rebuilt freely).

### 35.3 Consistency model [PROPOSED]

- **Strong consistency** within a store for systems of record (PostgreSQL transactions).
- **Eventual consistency** for derived stores (indexes/graph/cache), driven by the event
  bus; `index_lag_seconds` is measured and bounded.
- Cross-store atomicity via the **outbox pattern** (write state + outbox row in one tx;
  relay to the bus) — no distributed 2PC.

## 38. Hot / warm / cold tiers

### 38.1 Tiers

| Tier | Contents | Store/class | Access |
|------|----------|-------------|--------|
| Hot | Active documents, live indexes, frequently accessed knowledge, recent raw objects | SSD-backed DB/index; standard object storage | ms latency |
| Warm | Older documents, less-frequently accessed data, older raw objects | Infrequent-access object storage; smaller index replicas | higher latency OK |
| Cold | Historical raw data, archives, rarely accessed source versions | Archive-class object storage (e.g., Glacier-like) | minutes–hours restore |

### 38.2 Lifecycle movement

```
new raw object ─▶ HOT
   └─(age > A_h days AND access < T)─▶ WARM
        └─(age > A_w days AND access ≈ 0)─▶ COLD (archive)
             └─(legal/privacy retention expiry)─▶ delete per policy (tombstone + audit)
```

- Movement is driven by **age + access recency**, computed from object metadata and access
  logs; it is reversible (a cold object accessed → promoted/cached).
- **Cold-tiering is never deletion.** Deletion happens only via retention/privacy policy
  (§60), producing a tombstone + audit record, preserving lineage stubs.
- Indexes/graph reference objects by id regardless of tier; a cold read triggers a restore
  job (async) surfaced to the caller.

### 38.3 Failure modes, cost, observability

- **Failure:** cold restore latency surprises → mark cold results as "restoring"; caches
  keep hot data hot.
- **Cost:** tiering is the main storage-cost lever (§49); ratios tuned by access analytics.
- **Observability:** `storage_bytes{tier}`, `tier_migrations_total`,
  `cold_restore_latency_s`, `storage_growth_bytes_per_day`, `compression_ratio`,
  `dedup_savings_bytes`.

### 38.4 Recovery

- Object storage is replicated (multi-AZ; optionally multi-region for cold archives).
- Relational stores: PITR backups + replicas. Derived stores: rebuild from record stores.
- Full recovery sequence and RPO/RTO targets: [`docs/23-disaster-recovery.md`](23-disaster-recovery.md).
