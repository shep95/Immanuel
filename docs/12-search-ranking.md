# 28. Search Engine · 29. Ranking

## 28. Search engine

**Purpose.** High-performance retrieval across many facets, backed by purpose-built
indexes — **never** by scanning raw storage for ordinary queries.

### 28.1 Query types supported

keyword · phrase · boolean · metadata · domain · subdomain · entity · claim · source ·
date · version · relationship · graph traversal · document · code · dataset · pattern.

### 28.2 Components

```
indexing pipeline ─▶ query parser ─▶ retrieval engine ─▶ ranking engine ─▶
   filtering ─▶ faceting ─▶ result aggregation ─▶ pagination ─▶ caching ─▶ query logging ─▶ perf monitoring
```

| Component | Responsibility |
|-----------|----------------|
| Indexing pipeline | Consume `index.updated`-worthy changes; build/refresh inverted + facet indexes. |
| Query parser | Parse query DSL; validate; enforce complexity budget (§63). |
| Retrieval engine | Fetch candidate matches from the appropriate index. |
| Ranking engine | Score candidates (see §29). |
| Filtering | Apply facet/permission/date/domain filters. |
| Faceting | Aggregate counts per facet for the UI. |
| Result aggregation | Merge multi-index results (docs/claims/entities/code/datasets). |
| Pagination | Bounded, cursor-based (no unbounded deep pagination). |
| Caching | Cache hot queries/facets; invalidate on `index.updated`. |
| Query logging | Log queries (privacy-aware) for audit + relevance tuning. |
| Perf monitoring | Latency, budget breaches, cache hit rate. |

### 28.3 Index families

- **Inverted text index** (documents, code, claims) — BM25-class scoring.
- **Field/facet indexes** (domain, source, date, format, language, confidence, evidence
  quality, relationship type).
- **Entity index** (entities → mentions, pages).
- **Claim index** (subject/predicate/object + status).
- **Graph index** (adjacency for bounded traversal).
- **[OPTIONAL/EXPERIMENTAL] Vector index** — only if semantic search is added later; it is
  an *additional* index, never a core dependency, and never replaces provenance/evidence.

### 28.4 Indexing pipeline (idempotent)

```
knowledge/document change ─▶ event (e.g., document.normalized, claim.created) ─▶
   index worker ─▶ build index doc (deterministic from source of truth) ─▶
   upsert (keyed by stable id) ─▶ emit index.updated
```

Index docs are **derived** and fully rebuildable from the stores; the search engine is a
disposable/rebuildable index, never a system of record.

### 28.5 Failure modes & recovery

- Index corruption/loss → rebuild from PostgreSQL/graph/raw via the indexing pipeline
  (bounded, resumable). Reads degrade to primary stores for critical lookups meanwhile.
- Indexing lag → surfaced as `index_lag_seconds`; backpressure prevents unbounded queues.
- Hot shard → shard by domain/id hash; replicas for read scaling.

### 28.6 Search security (see §63)

- Query complexity budget (max clauses, max wildcards, max traversal depth/edges).
- Input size limits; injection-safe parsing (no passthrough to store query languages).
- Bounded pagination; per-client rate limits; expensive-query circuit breaker.

---

## 29. Ranking

**Purpose.** Combine multiple signals into a useful ordering while **keeping truth,
relevance, evidence, source quality, and recency separate**.

### 29.1 Signals combined

text relevance · source relevance · recency · domain relevance · document quality ·
**source independence** · provenance quality · metadata completeness · relationship
relevance · user-selected filters · exact vs partial matches.

### 29.2 Separation of scores (invariant)

The engine computes and **returns distinct scores** — it does not fold them into a single
opaque "truth" number:

```json
{
  "result_id": "doc_...",
  "scores": {
    "relevance": 0.88,            // how well it matches the query
    "evidence_quality": 0.61,     // strength/type of evidence
    "source_quality": 0.72,       // operational reliability, NOT truth
    "recency": 0.95,
    "confidence": 0.70,           // extraction/derivation confidence
    "independent_sources": 4      // NOT raw copy count
  },
  "rank_score": 0.83              // a transparent, documented combination for ordering
}
```

- **`source_quality` (authority) is explicitly not truth.** It contributes to *relevance/
  operational trust*, never to a claim's validity.
- The default `rank_score` is a documented, tunable weighting of the sub-scores; clients
  (and the frontend) can re-rank by any sub-score or filter.

### 29.3 Ranking method (deterministic, tunable)

- Text relevance from the inverted index (BM25-class).
- Other signals from stored, precomputed fields (recency from timestamps, independence from
  §27, provenance/metadata quality from completeness checks).
- Combination is a linear (or documented monotone) function with versioned weights →
  reproducible ordering per ranking version.
- **[EXPERIMENTAL]** Learning-to-rank could later tune weights from query logs; it would be
  optional and auditable, never obscuring the sub-scores.

### 29.4 Anti-manipulation

- Copy-flooding cannot inflate rank: evidence weight uses `independent_sources` (§27, §42).
- Source-authority gaming is bounded because authority ≠ truth and is only one signal.

### 29.5 Failure modes & observability

- Poor relevance → offline relevance test set (§48) + query-log analysis; reweight.
- Metrics: `search_latency_ms` (p50/p95/p99), `search_qps`, `cache_hit_ratio`,
  `query_budget_breaches_total`, `zero_result_rate`.
