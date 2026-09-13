# 2. Objectives · 3. Non-objectives · 4. System Boundaries

## 2. System objectives

Immanuel's mandate is to **continuously and lawfully** build and maintain a
provenance-preserving knowledge infrastructure over public digital information.

### Primary functional objectives

1. **Discover** public sources across many source types (sites, APIs, datasets, repos,
   feeds, archives, documentation, portals, public object stores).
2. **Evaluate authorization** for every source before acquisition.
3. **Acquire** content efficiently, respecting rate limits and change-detection signals.
4. **Preserve raw content immutably** with integrity guarantees.
5. **Normalize** heterogeneous inputs into standardized structures without destroying
   original representations.
6. **Deduplicate** across four levels (byte / normalized / near-duplicate / lineage).
7. **Compress** losslessly, reporting real storage savings.
8. **Extract metadata, structure, entities, claims, and relationships** deterministically.
9. **Organize** knowledge in a tree (ontology) **and** a graph (cross-domain relations).
10. **Preserve provenance** end-to-end.
11. **Detect contradictions** and represent them explicitly.
12. **Version everything important** temporally.
13. **Index and search** across many facets with bounded, safe query cost.
14. **Expose** knowledge via versioned APIs, a Discord distribution layer, and a frontend.
15. **Observe, self-audit, and recover** continuously.

### Non-functional objectives (with target posture) [PROPOSED]

| Objective | Target posture |
|-----------|----------------|
| Correctness of processing | Deterministic; identical input → identical output for a pipeline version. |
| Provenance integrity | 100% of derived objects trace to an acquisition event. |
| Idempotency | Reprocessing never creates duplicate knowledge objects. |
| Availability (read path) | Search/API degrade gracefully; reads survive write-path outages. |
| Fault isolation | No single parser/source/worker failure halts the system. |
| Scalability | Horizontal at every plane; documented behavior at 10³→10⁸ sources. |
| Recoverability | Indexes and graph fully reconstructable from raw lake + provenance. |
| Security & privacy | Least privilege, isolation, data minimization by default. |
| Extensibility | New formats/connectors/relationship-types added without redesign. |

## 3. Non-objectives

Explicitly **out of scope** (to keep the core honest and focused):

- **Not an AI model.** No model training, inference, or generation is required for the
  core to function. AI/ML is an *optional future* enrichment layer only.
- **Not a bypass tool.** No defeating of authentication, paywalls, encryption, access
  controls, CAPTCHAs, or `robots`/ToS restrictions. Restricted content stays restricted.
- **Not a private-data harvester.** Private, credentialed, or non-public data is never a
  target, even when technically reachable.
- **Not a summarizer that discards originals.** Semantic summarization is never treated
  as compression; originals are preserved.
- **Not a truth oracle.** Immanuel reports evidence, provenance, and contradictions — it
  does not adjudicate ultimate truth or equate source authority with truth.
- **Not the frontend.** The UI is a separate application consuming the API.
- **Not a general compute platform.** It does not execute acquired code; code is analyzed
  statically, never run (except inside strictly isolated, resource-capped sandboxes for
  *parsing*, never for *executing acquired programs*).
- **Not a real-time messaging backend.** Discord is a distribution/notification/ops layer,
  never the primary datastore.

## 4. System boundaries

### 4.1 What the system is responsible for

Internet discovery · source acquisition · file ingestion · data processing · storage ·
knowledge organization · graph construction · search · API access · Discord distribution ·
frontend access (via API) · security · observability · administration · pattern analysis.

### 4.2 What belongs outside the system

- The **frontend application** (consumes the public API/BFF).
- **End-user identity providers** (integrated, not owned).
- **The Discord platform** itself.
- **Third-party source systems** (owned by their operators).
- **Cloud infrastructure primitives** (object store, DB engines, message brokers) —
  consumed as managed dependencies.
- **AI/ML model providers**, if ever added as an optional layer.

### 4.3 Boundary diagram

```
                    ┌───────────────────────── ADMINISTRATIVE BOUNDARY ─────────────────────────┐
                    │                                                                            │
  EXTERNAL          │            SYSTEM BOUNDARY (Immanuel)                                      │
  SYSTEMS           │   ┌────────────────────────────────────────────────────────────────┐     │
  ┌───────────┐     │   │  TRUST BOUNDARY: untrusted ingress                               │     │
  │ Internet  │─────┼──▶│  ┌───────────────┐   quarantine/sandbox                          │     │
  │ sources   │  (net)  │  │ Crawler + Conn │──────────────┐                               │     │
  └───────────┘     │   │  └───────────────┘              ▼                                │     │
                    │   │        DATA BOUNDARY: raw lake (immutable) ──▶ processing         │     │
  ┌───────────┐     │   │                                     │                            │     │
  │ Frontend  │◀────┼───│  ┌───────────────┐   SECURITY BOUNDARY: internal services        │     │
  │ app       │ (api)   │  │ API Gateway   │◀── knowledge/search/graph stores              │     │
  └───────────┘     │   │  └───────────────┘                                               │     │
                    │   │  ┌───────────────┐                                               │     │
  ┌───────────┐     │   │  │ Discord GW    │──▶ Discord platform (external)                │     │
  │ Discord   │◀────┼───│  └───────────────┘                                               │     │
  └───────────┘     │   └────────────────────────────────────────────────────────────────┘     │
                    │                                                                            │
  ┌───────────┐     │   Admin console + secrets + policy config live inside the admin boundary   │
  │ Operators │─────┼──▶ (separate authn, MFA, audit).                                            │
  └───────────┘     └────────────────────────────────────────────────────────────────────────┘
```

### 4.4 Boundary classes (explicit)

- **System boundary** — the deployable services and stores Immanuel owns/operates.
- **External systems** — internet sources, frontend, Discord, IdPs, cloud primitives.
- **Trust boundaries** — (a) untrusted internet ingress → quarantine; (b) quarantine →
  trusted processing (only validated bytes cross); (c) public API → internal services.
- **Data boundaries** — raw ↔ normalized ↔ derived ↔ knowledge; each crossing is an
  explicit, logged transformation with provenance.
- **Security boundaries** — network segmentation between acquisition, processing,
  knowledge, and distribution; secrets isolated; per-plane least-privilege identities.
- **Administrative boundary** — operator/admin surfaces (config, policy, secrets, dashboards)
  separated with independent authn/MFA and full audit.

### 4.5 Assumptions & unknowns

- **[ASSUMED]** Public cloud primitives (object store, managed PostgreSQL, a message
  broker) are available; on-prem equivalents can substitute.
- **[ASSUMED]** Legal review defines jurisdictional policy inputs; the policy engine
  enforces, it does not decide law.
- **[UNKNOWN]** Exact upper bound of "maximum accessible" coverage — treated as an
  ever-moving target measured by coverage metrics, not a fixed goal.
