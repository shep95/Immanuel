# 55. Final Architecture Diagram · 80. System Map · 84. Architectural Audit

## 80 / 55. Final system map

### Data flow (what moves through the system)

```
                                    ┌──────────────────────────────┐
                                    │          INTERNET            │
                                    │ sites·APIs·datasets·repos·   │
                                    │ feeds·archives (public only) │
                                    └───────────────┬──────────────┘
                                                    │
             ┌──────────────────────────┐          │
             │     SOURCE DISCOVERY      │──────────┤ (discover candidates)
             └───────────┬──────────────┘          │
                         ▼                          │
             ┌──────────────────────────┐          │
             │       POLICY ENGINE       │ (authorized? else STOP)
             └───────────┬──────────────┘          │
                         ▼                          │
             ┌──────────────────────────┐          │
             │    SCHEDULER (adaptive)   │          │
             └───────────┬──────────────┘          │
                         ▼                          ▼
             ┌──────────────────────────┐   ┌──────────────┐
             │   CRAWLER + CONNECTORS    │──▶│  QUARANTINE  │ (sandbox, limits)
             └───────────┬──────────────┘   └──────┬───────┘
                         │ IngestionObject          │ validated bytes
                         ▼                          ▼
                                            ┌──────────────┐
                                            │   RAW LAKE   │ (immutable, content-addressed)
                                            └──────┬───────┘
                                                   ▼
   ┌───────────── PROCESSING ─────────────────────────────────────────────────┐
   │ format detect ▶ parse ▶ extract/segment ▶ NORMALIZE ▶ DEDUP(L1–L4) ▶       │
   │ COMPRESS ▶ METADATA(tamper-aware) ▶ doc/code/dataset/media processing      │
   └───────────────────────────────┬──────────────────────────────────────────┘
                                    ▼
   ┌───────────── KNOWLEDGE ──────────────────────────────────────────────────┐
   │ ONTOLOGY(tree) + classification ▶ entities/CLAIMS/relationships ▶          │
   │ KNOWLEDGE GRAPH ▶ PROVENANCE GRAPH ▶ CONTRADICTION ENGINE ▶ TEMPORAL       │
   └───────────────────────────────┬──────────────────────────────────────────┘
                                    ▼
   ┌───────────── RETRIEVAL ──────────────────────────────────────────────────┐
   │ INDEXING ▶ SEARCH INDEXES(inverted/facet/entity/claim/graph) ▶ RANKING     │
   └───────────────────────────────┬──────────────────────────────────────────┘
                                    ▼
   ┌───────────── DISTRIBUTION ───────────────────────────────────────────────┐
   │ API GATEWAY ▶ public/internal/admin APIs ── DISCORD GATEWAY ── FRONTEND BFF│
   └───────────────────────────────┬──────────────────────────────────────────┘
                                    ▼
                           consumers: Frontend · Discord · external API clients

   ┌──── PATTERN LAYER (above data infra) ────┐   ┌──── PLATFORM (cross-cutting) ────┐
   │ discover▶create▶evaluate▶retain/quar/rej │   │ Event Bus · Queues · Storage      │
   │ ▶retrieve▶compose▶adapt▶evolve            │   │ Tiers · Security · Privacy ·      │
   │ (novel = hypothesis until tested)        │   │ Observability · Admin · DR        │
   └──────────────────────────────────────────┘   └───────────────────────────────────┘
```

### Control flow (what governs the system)

```
Admin/Operators ─▶ Admin API ─▶ { policy config, source config, taxonomy governance,
                                  pattern governance, reprocessing, queue/DLQ ops }
                                        │
Event Bus ◀── every service emits facts ─┘ ──▶ { self-audit, root-cause engine,
                                                 Discord notifications, dashboards, alerts }

Scheduler ◀── source health + change stats ── Crawler        (feedback loop: adapt frequency)
Ranking   ◀── independence/provenance/recency signals ── Knowledge plane
Backpressure ◀── queue depth/lag ── all stages              (feedback loop: protect stores)
```

**Data flow vs control flow are separated:** data moves left-to-right through the planes;
control (config, policy, governance, feedback, observability) is orthogonal and mediated by
the admin surface and the event bus.

### The replaceability seams (upgrade without redesign)

- `IngestionObject` (acquisition ↔ processing)
- `NormalizedDocument` / structure tree (processing ↔ knowledge)
- `KnowledgeObject` / claim / edge (knowledge ↔ retrieval)
- Event schemas (any producer ↔ any consumer)
- API/BFF contracts (system ↔ frontend/external)
- Connector interface, Format Registry, index families, pattern gates

Any single component behind a seam can be swapped independently.

---

## 84. Final architectural audit

Attacking the finished design; each answer names an architectural mitigation.

| Question | Answer / mitigation |
|----------|---------------------|
| What assumptions could break? | Cloud-primitive availability; legal inputs; determinism of libs → mitigations: on-prem substitutes, policy versioning, pinned/tested deterministic stages. |
| What becomes the bottleneck first? | Politeness-bounded crawl throughput, then graph traversal/write cost → scale breadth; graph budgets + dedicated engine. |
| Source volume 100×? | Partition registry + distributed scheduler + registration budgets (§36 stage 2–3). |
| Document volume 1000×? | Dedup + compression + tiering; autoscale parser pools; backpressure (§13/§14/§36). |
| Storage expensive? | Cold-tiering, aggressive dedup, columnar datasets, retention policy (§38/§49). |
| Search traffic 100×? | Caching + read replicas + CDN + horizontal search scaling (§28/§30). |
| Discord unavailable? | Durable queue + degraded mode; core unaffected; regenerate digests (§32). |
| API unavailable? | Stateless API redeploy; reads from cache; core pipeline keeps running (§30). |
| Graph enormous? | Traversal/edge budgets, partitioning, dedicated graph engine, rebuildable index (§23/§66). |
| Millions of duplicates? | Dedup L1–L4; independence counting; registration budgets (§13/§42). |
| Thousands publish same false claim? | Evidence weighted by `independent_source_count`, not copies; burst flag (§27/§42). |
| Metadata corrupted? | Tamper-aware metadata (hash/sign); anomalies; re-derive observed fields from raw (§40). |
| Parser compromised? | Strict sandbox, no egress, minimal creds, dedicated nodes; isolate + rebuild + patch (§41). |
| Queue loses messages? | Durable/replicated broker + outbox + replay from event log/offsets (§34). |
| Database fails? | Replicas + PITR; promote/restore; derived stores rebuildable (§46). |
| Region unavailable? | Multi-region raw lake + cells + failover; re-warm; verify provenance (§36/§46). |
| Ontology too large? | Governance gates + growth cap + merge/split + versioned rollback (§22). |
| System classifying incorrectly? | `classification_error_rate` audit; reweight + reclassify; `unclassified` bucket (§21/§44). |
| Pattern wrong but temporarily successful? | Quarantine + tests + falsifiers + usage/failure history + re-eval triggers (§42). |
| Pattern library poisoned? | Independence + tests before approval; versioned rollback; freeze approvals (§42). |
| Administrator config mistake? | Versioned config + validation + dual-control + rollback + audit (§45). |
| Internet changes unexpectedly? | Format Registry + connector framework + fallback path; add descriptor/connector, reprocess (§9/§11). |

### Standing invariants that carry the design

1. **Immutable raw + complete provenance ⇒ everything derived is rebuildable.**
2. **Independent sources ≠ copies ⇒ resistant to flooding/poisoning.**
3. **Sandbox + hard limits ⇒ safe under hostile input.**
4. **Budgets everywhere (query/graph/rate) ⇒ resistant to DoS and cost blowups.**
5. **Version everything + rollback ⇒ recoverable from human and software error.**
6. **Separate raw/derived, evidence/inference, relevance/truth, count/independence ⇒
   epistemic honesty end-to-end.**
7. **Deterministic core, AI optional ⇒ no hidden model dependency; runs 24/7 algorithmically.**

### Honest limits [UNKNOWN / EXPERIMENTAL]

- Exact scaling constants and cost figures are planning estimates until benchmarked (§48/§49).
- Near-duplicate/lineage thresholds and taxonomy-governance thresholds need empirical tuning.
- The pattern layer's auto-accept policies are conservative-by-default and unproven at
  scale — treated as experimental until validated.
- No untested part of this design is claimed as guaranteed; each is tagged and gated by the
  test/benchmark strategy (§47/§48) before being relied upon.
