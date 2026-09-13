# 31. Frontend Integration

**Purpose.** A **separate** frontend application consumes Immanuel through the API/BFF.
The frontend **never** needs to know how crawling works.

## 31.1 Architecture

```
frontend (SPA/SSR)
   └─▶ API gateway / BFF (backend-for-frontend)
          └─▶ search / knowledge / graph services
                 └─▶ storage & indexes
```

- The **BFF** shapes API responses for UI needs (aggregation, projection) without leaking
  internal structure; it is part of the distribution plane, not the frontend.
- The frontend holds **no crawling/processing logic** and **no direct store access**.

## 31.2 Frontend capabilities

search · advanced search · domain explorer · source explorer · document viewer ·
knowledge graph viewer · timeline · entity pages · claim pages · provenance viewer ·
pattern explorer · system statistics.

## 31.3 Example user flows

### Flow A — Search → document → provenance
```
1. User searches "quantum tunneling".
2. Frontend → GET /v1/search?q=quantum+tunneling&facets=domain,date
3. Results show docs, claims, entities with SEPARATED scores (relevance, evidence,
   source, recency, confidence, independent_sources).
4. User opens a document → GET /v1/documents/{id} (structure + versions).
5. User clicks "provenance" → GET /v1/provenance/{object_id}
   → sees claim ← segment ← document ← source ← acquisition ← pipeline version.
```

### Flow B — Concept exploration
```
1. Domain explorer → GET /v1/domains/physics (tree navigation).
2. Concept page "quantum tunneling":
   → claims (with status/contradictions), documents, sources, versions,
     relationships, patterns.
3. User expands the graph → GET /v1/graph/traverse?node=concept:quantum_tunneling&depth=2
   (bounded, budgeted traversal).
```

### Flow C — Contradiction inspection
```
1. Claim page shows status = "unresolved_contradiction".
2. Frontend → GET /v1/claims/{id}/contradictions
3. UI shows both sides, dimensions examined, independent-source counts, evidence.
   No side is presented as "the truth".
```

### Flow D — Timeline
```
1. Timeline view → GET /v1/versions?subject=concept:X&from=2024&to=2026
2. Shows what was known when, which claims appeared/disappeared, source changes.
```

## 31.4 Design invariants

- **Epistemic honesty in the UI:** claims show status/evidence/confidence; contradictions
  show both sides; ranking sub-scores are visible/inspectable; copies vs independent
  sources are distinguished.
- **Provenance is always reachable** from any knowledge object (one click away).
- **Graph exploration is bounded** (depth/edge budgets) so the UI can't trigger a DoS
  (§66).

## 31.5 Non-responsibilities

- The frontend does not schedule crawls, does not write to stores, and does not implement
  policy — it only reads through the API/BFF. This keeps the UI replaceable and the core
  insulated from UI churn.
