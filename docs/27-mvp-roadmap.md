# 51. MVP · 52. Development Roadmap · 53. Future Evolution

## 51. Minimum viable system

The smallest realistic build that is genuinely useful and grows into the full architecture
without rework.

### 51.1 MVP scope

web acquisition · source registry · raw storage · HTML parsing · document normalization ·
hash deduplication (L1) · metadata · basic ontology · search · API · Discord notifications.

### 51.2 MVP architecture (modular monolith)

```
seeds ─▶ [discovery] ─▶ source registry (PostgreSQL)
                             │
[policy gate] ◀──────────────┘
   │ allowed
   ▼
[scheduler] ─▶ [acquisition (HTTP + conditional requests)] ─▶ RAW LAKE (S3-compatible)
                                                                 │
   [HTML parser] ─▶ [normalization] ─▶ [L1 dedup by sha256] ─▶ [metadata]
                                                                 │
   [basic domain classification] ─▶ documents/claims in PostgreSQL
                                                                 │
                          [indexing] ─▶ search index (OpenSearch)
                                                                 │
                     [API (/v1/search, /documents, /sources)] ─▶ [Discord notifications]
```

- One deployable app with clear internal modules + a durable work queue (RabbitMQ/Redis)
  and a minimal event log (can start as a table/topic).
- Stores: PostgreSQL + S3-compatible object store + OpenSearch + Redis.
- **Invariants preserved from day one:** immutable raw lake, content-addressing,
  provenance events, epistemic tags, separation of raw/normalized/derived. These are cheap
  to add early and expensive to retrofit.

### 51.3 MVP exit criteria

- Can discover + register web sources, respect policy/robots, and crawl politely.
- Stores raw immutably; L1-dedups; normalizes HTML; extracts metadata; classifies to a
  basic ontology.
- Search + API return provenance-tagged results; Discord posts aggregated digests.
- Determinism + idempotency tests pass; basic security (SSRF guard, size caps, sandboxed
  parsing) in place.

### 51.4 How the MVP evolves into the full system

| MVP piece | Evolves into |
|-----------|--------------|
| HTML parser | Full format registry + all connectors/parsers (§8–§10, §16–§19) |
| L1 dedup | L2–L4 (normalized, near-dup, lineage) (§13) |
| Basic ontology | Full ontology + dynamic taxonomy governance (§20–§22) |
| Documents/claims in PG | Knowledge graph + provenance graph + contradictions (§23–§27) |
| Single search index | Specialized indexes + multi-signal ranking (§28–§29) |
| Modular monolith | Distributed pipeline of modular services (§26, §36) |
| Discord notifications | Full Discord gateway + commands + templates (§32–§34) |
| — | Pattern layer (§42–§43), added last, above a stable data infra |

---

## 52. Development roadmap (phases)

For each phase: objectives · components · dependencies · deliverables · tests · failure
conditions · exit criteria. (Condensed table; each row is a milestone.)

| Phase | Objective | Key components | Depends on | Exit criteria |
|-------|-----------|----------------|------------|---------------|
| 0 | Architecture & schemas | schemas, event/API contracts, ontology skeleton | — | schemas reviewed; contract tests scaffolded |
| 1 | Source registry | SOURCE model, canonicalization, dedup-of-sources | 0 | register/dedupe sources; policy fields present |
| 2 | Crawler | scheduler, acquisition, connectors (http/html), politeness | 1 | polite, conditional-request crawling; job lifecycle |
| 3 | Raw storage | immutable lake, content-addressing, integrity | 2 | write-once + verify + scrub |
| 4 | Parsing | format registry, HTML/doc parsers, sandbox | 3 | sandboxed parsing; fallback path; fuzz-safe |
| 5 | Normalization | encoding/date/structure normalization | 4 | deterministic normalized docs |
| 6 | Deduplication | L1→L4 | 5 | near-dup + lineage clustering; independence counts |
| 7 | Metadata | extraction + integrity + anomalies | 5 | epistemic-tagged, tamper-aware metadata |
| 8 | Ontology | tree + classification | 5 | ranked multi-domain classification |
| 9 | Knowledge graph | entities/claims/relationships + provenance + contradictions | 7,8 | provenance-complete graph; contradictions detected |
| 10 | Search engine | indexes + ranking | 9 | faceted search; separated ranking scores |
| 11 | API | public/internal/admin APIs | 10 | versioned API; error envelope; budgets |
| 12 | Discord integration | gateway, templates, commands | 11 | aggregated digests; commands; degraded-mode |
| 13 | Frontend | BFF + UI flows | 11 | search/explorer/provenance views |
| 14 | Pattern engine | pattern layer + transfer | 9 | governed pattern lifecycle; quarantine gates |
| 15 | Security hardening | full controls, DR drills | all | pen-test/adversarial suite green; DR tested |
| 16 | Distributed scaling | split services, shard stores | 11 | per-plane scaling; cell readiness |
| 17 | Advanced optimization | tiering, cost tuning, LTR-optional | 16 | cost/latency targets met |

Failure conditions per phase (examples): Phase 2 — impolite crawling / SSRF leak; Phase 6 —
false-merge rate above threshold; Phase 9 — any provenance gap; Phase 11 — unbounded query
cost. Any failure condition blocks the phase's exit.

---

## 53. Future evolution

- **Optional AI/ML layer** — augment (never replace) deterministic classification,
  near-dup detection, ranking (LTR), entity/claim extraction, media transcription/vision.
  Always downstream of the same test/quarantine/provenance gates; never a core dependency.
- **Cellular / federated architecture** — per-domain/region cells with federated search &
  graph for extreme scale (§36 stage 4).
- **Richer connectors** — more source classes via the connector framework (no redesign).
- **Deeper temporal analytics** — trend/change analysis over the temporal knowledge base.
- **Community/centrality graph analytics** — bounded, budgeted (§66).
- **Formal policy DSL** — richer, testable access-policy expression (§39).

Each future item plugs into an existing seam (connector interface, index family, event
type, pattern gate) so components can be **replaced or upgraded without redesigning the
system** — the core design goal.
