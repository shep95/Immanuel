# 1. Executive Architecture · 5. Complete Architecture

## 1. Executive architecture

Immanuel is a **deterministic data-and-knowledge infrastructure**, not a model. It is
built as an ecosystem of loosely-coupled services connected by **durable queues** and an
**event bus**, coordinating around a set of purpose-specific stores. No single service
owns the whole pipeline; each stage is independently deployable, independently scalable,
and independently recoverable.

The system is organized into **seven planes**:

1. **Acquisition plane** — discovery, policy evaluation, scheduling, fetching, quarantine.
2. **Processing plane** — format detection, parsing, extraction, normalization,
   deduplication, compression, segmentation.
3. **Knowledge plane** — metadata, ontology, classification, entities, claims,
   relationships, provenance, contradictions, temporal versioning.
4. **Retrieval plane** — indexing, search, ranking, graph query.
5. **Distribution plane** — public/internal/admin APIs, Discord gateway, frontend BFF.
6. **Pattern plane** — a separate, governed layer *above* the data infrastructure.
7. **Platform plane** — event bus, queues, storage, security, observability, admin,
   disaster recovery.

### Key architectural commitments

- **Separation of concerns by data category.** Raw, normalized, derived, metadata,
  claims, knowledge, relationships, patterns, and inferences live in distinct stores
  with distinct write paths. Conversion between categories is always an explicit,
  logged, reversible-in-lineage operation.
- **Immutable raw lake.** Acquired bytes are written once and never overwritten. A new
  version of a source produces a new immutable object.
- **Content-addressed everything.** Cryptographic content hashes (`sha256`) are the
  backbone of deduplication, idempotency, and integrity verification.
- **Idempotent, replayable processing.** Any worker can crash and be re-run without
  producing duplicate knowledge, because operations key off deterministic IDs derived
  from content and job identity.
- **Provenance is not optional.** Every derived object carries a lineage edge back to
  the acquisition event and pipeline version that produced it.
- **Policy before acquisition.** Nothing is fetched before the policy engine evaluates
  authorization state. Restrictions are respected, never bypassed.

### Recommended baseline architecture [PROPOSED]

A **distributed pipeline of modular services** (not a monolith, not fine-grained
microservices) with **polyglot persistence**:

- Object storage (raw lake, cold tiers) — S3-compatible.
- Relational DB (source registry, jobs, claims, provenance, audit) — PostgreSQL.
- Document store (normalized documents, structure trees) — PostgreSQL JSONB at small
  scale; a document DB at large scale.
- Graph DB (knowledge graph) — start as adjacency tables in PostgreSQL; migrate to a
  dedicated graph engine at scale.
- Search engine (inverted + vector-optional indexes) — OpenSearch/Elasticsearch family.
- Queue/stream (work distribution + event bus) — Kafka/Redpanda for the bus; a
  work-queue (SQS-like / Redis Streams / RabbitMQ) for job queues.
- Cache — Redis.

Rationale and alternatives: [`docs/26-technology-comparison.md`](26-technology-comparison.md).

## 5. Complete architecture (overview)

```
                                  ┌──────────────────────────────────────────────┐
                                  │                 THE INTERNET                  │
                                  │  (public sites, APIs, datasets, repos, feeds) │
                                  └───────────────┬──────────────────────────────┘
                                                  │ (lawful, authorized access only)
   ACQUISITION PLANE                              ▼
   ┌──────────────┐   ┌───────────────┐   ┌───────────────┐   ┌──────────────┐
   │   Source     │──▶│    Policy     │──▶│   Scheduler   │──▶│   Crawler    │
   │  Discovery   │   │    Engine     │   │  (adaptive)   │   │  Worker Pool │
   └──────────────┘   └───────────────┘   └───────────────┘   └──────┬───────┘
          │  SOURCE registry (PostgreSQL)                             │ fetch
          ▼                                                           ▼
   ┌──────────────┐                                          ┌──────────────┐
   │  Connector   │◀─────────────────────────────────────────│  Quarantine  │
   │  Framework   │  (http/html/rest/graphql/rss/git/…)       │  (sandbox)   │
   └──────┬───────┘                                          └──────┬───────┘
          │ normalized IngestionObject                              │ safe bytes
          ▼                                                         ▼
   PROCESSING PLANE                                          ┌──────────────┐
   ┌──────────────┐  ┌───────────────┐  ┌───────────────┐   │   RAW LAKE   │
   │ Format Detect│─▶│    Parsers    │─▶│  Extraction   │   │ (immutable,  │
   │  + Registry  │  │ (per format)  │  │  + Segment    │   │ object store)│
   └──────────────┘  └───────────────┘  └──────┬────────┘   └──────────────┘
                                               │
   ┌──────────────┐  ┌───────────────┐  ┌──────▼────────┐  ┌──────────────┐
   │ Compression  │◀─│ Deduplication │◀─│ Normalization │  │  Metadata    │
   │   Engine     │  │  (L1–L4)      │  │    Engine     │─▶│   Engine     │
   └──────────────┘  └───────────────┘  └───────────────┘  └──────────────┘
                                               │
   KNOWLEDGE PLANE                             ▼
   ┌──────────────┐  ┌───────────────┐  ┌───────────────┐  ┌──────────────┐
   │   Ontology   │◀─│ Domain / Sub- │◀─│ Entity/Claim/ │─▶│  Provenance  │
   │  (tree)      │  │  domain class │  │ Relationship  │  │    Graph     │
   └──────┬───────┘  └───────────────┘  └──────┬────────┘  └──────────────┘
          │                                    ▼
          │              ┌───────────────┐  ┌───────────────┐  ┌──────────────┐
          └─────────────▶│   Knowledge   │─▶│ Contradiction │  │   Temporal   │
                         │  Graph (graph)│  │    Engine     │  │  Versioning  │
                         └──────┬────────┘  └───────────────┘  └──────────────┘
                                │
   RETRIEVAL PLANE              ▼
   ┌──────────────┐  ┌───────────────┐  ┌───────────────┐
   │  Indexing    │─▶│  Search Index │─▶│   Ranking     │
   │  Pipeline    │  │ (inverted)    │  │   Engine      │
   └──────────────┘  └───────────────┘  └──────┬────────┘
                                               │
   DISTRIBUTION PLANE                          ▼
   ┌──────────────┐  ┌───────────────┐  ┌───────────────┐  ┌──────────────┐
   │  API Gateway │◀─│ Public/Intern/│─▶│ Discord       │  │  Frontend    │
   │              │  │  Admin APIs   │  │  Gateway      │  │  BFF         │
   └──────────────┘  └───────────────┘  └───────────────┘  └──────────────┘

   PATTERN PLANE (governed, above the data infra)
   ┌───────────────────────────────────────────────────────────────────────┐
   │  discover → create → evaluate → retain/quarantine/reject → retrieve →   │
   │  compose → adapt → evolve      (novel pattern = hypothesis until tested) │
   └───────────────────────────────────────────────────────────────────────┘

   PLATFORM PLANE (cross-cutting)
   Event Bus · Durable Queues · Storage Tiers (hot/warm/cold) · Security ·
   Privacy · Observability · Administration · Disaster Recovery
```

Detailed data-flow vs control-flow diagrams: [`docs/31-final-architecture.md`](31-final-architecture.md).

### Why this shape

- The **queue + event bus** spine means any plane can absorb a burst or a failure of a
  downstream plane without data loss (backpressure + dead-letter queues).
- **Fault isolation**: a parser crash quarantines one object; it does not stall the
  crawler or the search API.
- **Independent scaling**: crawler workers scale with source volume; parser workers with
  document volume; index workers with query volume — each on its own curve
  ([`docs/18-scalability.md`](18-scalability.md)).
- **Replaceability**: because interfaces are defined at plane boundaries (IngestionObject,
  NormalizedDocument, KnowledgeObject, events, API contracts), any single component can
  be swapped without redesigning the system.
