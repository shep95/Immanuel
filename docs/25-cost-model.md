# 49. Cost Model

**Purpose.** A conceptual model of infrastructure requirements and how cost scales with the
system's drivers. Numbers are **[ASSUMED]** planning figures, not quotes — plug in real
provider prices.

## 49.1 Cost components

compute · storage (hot/warm/cold) · network (egress especially) · relational database ·
search cluster · object storage · queues/broker · monitoring · backup · Discord
integration · API traffic.

## 49.2 Cost drivers

| Driver | Primarily affects |
|--------|-------------------|
| # sources | crawler compute, scheduler, registry DB |
| # documents / objects | processing compute, storage, index size, graph size |
| bytes ingested | object storage, network egress, compression compute |
| crawl frequency | crawler compute, network, 304-savings (bandwidth §52) |
| # users / search requests | API + search compute, cache, egress |
| graph size | graph DB compute/storage, traversal cost |

## 49.3 Cost model (conceptual formulas)

```
storage_cost ≈ Σ_tier ( stored_bytes_tier × price_per_GB_tier )
   where stored_bytes ≈ ingested_bytes × (1 − dedup_savings) × compression_factor

compute_cost ≈ crawl_workers×w_c + parse_workers×w_p + index_workers×w_i
             + graph_workers×w_g + api_nodes×w_a   (each × instance price)

network_cost ≈ ingest_bytes × price_in  +  egress_bytes(users, api) × price_out
   (ingest reduced by 304/conditional requests and change detection, §52)

db_cost ≈ relational_instances + replicas + search_cluster_nodes + graph_cluster_nodes
```

**Dedup + compression + change-detection are the primary cost levers** — they reduce
storage, network, and downstream processing simultaneously.

## 49.4 Illustrative scaling (order-of-magnitude, [ASSUMED])

| Scale | Sources | Objects | Stored (post dedup+compress) | Dominant cost |
|-------|---------|---------|------------------------------|---------------|
| Stage 1 | 10³ | 10⁶ | ~TBs | compute (parsing) |
| Stage 2 | 10⁶ | 10⁹ | ~100s TB | storage + search |
| Stage 3 | 10⁸ | 10¹¹ | ~PBs | storage (cold) + network |
| Stage 4 | >10⁸ | >10¹¹ | 10s PB | network egress + graph |

Observations:
- Cold-tiering dominates savings at stage 3–4 (most raw data is rarely re-read).
- Search/API cost scales with **users**, largely independent of corpus size (given good
  indexes + caching).
- Graph cost can grow super-linearly if unbounded → traversal budgets + partitioning keep
  it in check (§66).

## 49.5 Cost controls

- Aggressive dedup (esp. L4 lineage) + lossless compression + columnar dataset storage.
- Conditional requests / change detection to cut ingest bandwidth (§52).
- Tiered storage lifecycle (§38); rarely-read raw data → cold archive.
- Caching (search/API) to cut repeat compute.
- Admission control + query budgets to prevent pathological cost spikes (§62/§63).
- Rebuildable derived stores → can be resized down and rebuilt rather than over-provisioned.

## 49.6 Tradeoff

More redundancy/replication and more indexes improve resilience and query speed but raise
cost; the design keeps **systems of record** well-protected (worth the cost) and **derived
stores** lean (rebuildable, so under-provisioning is acceptable). This is an explicit
efficiency-vs-redundancy tradeoff resolved per data category (§49/§20-tradeoffs).
