# 23. Knowledge Graph · 24. Provenance Graph · 25. Claim System

## 23. Knowledge graph

**Purpose.** Represent cross-domain relationships between knowledge objects as a graph
(complementing the ontology tree).

### 23.1 Node types

person · organization · location · concept · event · technology · document · dataset ·
repository · code · equation · process · theory · claim · source · pattern.

### 23.2 Relationship types (extensible)

Structural: `is_a` · `part_of` · `contains` · `composed_of` · `instantiates` ·
`special_case_of` · `generalizes` · `abstracts`.
Causal/functional: `requires` · `enables` · `inhibits` · `amplifies` · `reduces` ·
`causes` · `contributes_to` · `triggers` · `regulates` · `feeds_back_to`.
Correlational/temporal: `correlates_with` · `precedes` · `follows`.
Comparative: `competes_with` · `cooperates_with` · `complements` · `alternative_to` ·
`analogous_to` · `transfers_to` · `scales_to` · `emerges_from`.
Epistemic/lifecycle: `contradicts` · `detects` · `fails_under` · `repairs` · `tests` ·
`falsifies` · `refines` · `supersedes`.
Plus **custom relationship types** (registered, typed, documented).

### 23.3 Edge record

```json
{
  "edge_id": "edge_01J9...",
  "from": "concept:quantum_tunneling",
  "type": "requires",
  "to": "concept:wave_function",
  "confidence": 0.86,
  "epistemic_status": "inference",           // observation|inference|hypothesis|...
  "evidence": ["claim_...", "doc_..."],
  "provenance_event_id": "prov_...",
  "valid_from": "2026-09-13T00:00:00Z",
  "valid_to": null,                           // temporal validity (§27)
  "version": 1
}
```

- Every edge carries **confidence**, **epistemic status**, **evidence**, and
  **provenance** — the graph never asserts unsourced relationships.
- Edges are **temporally versioned** (`valid_from`/`valid_to`) so the graph's history is
  queryable (§27).

### 23.4 Storage & scale

- Start: adjacency tables in PostgreSQL (nodes, edges) — simplest, transactional.
- Scale: migrate hot graph to a dedicated graph engine (see
  [`docs/26-technology-comparison.md`](26-technology-comparison.md)); keep the relational
  copy as the durable system of record so the graph store is a rebuildable index.
- Guardrails against graph explosion & traversal DoS: bounded traversal depth, per-query
  edge budgets (§30, §63, §66).

---

## 24. Provenance graph

**Purpose.** Give every derived object a complete, queryable lineage. Provenance is a
first-class graph, separate from the knowledge graph.

### 24.1 Lineage chain

```
knowledge_object ─▶ claim ─▶ extracted_segment ─▶ document ─▶ source ─▶
   source_version ─▶ acquisition_event ─▶ processing_pipeline_version
```

### 24.2 Provenance event

Every transformation emits a provenance event:

```json
{
  "provenance_event_id": "prov_01J9...",
  "produced": { "type": "claim", "id": "claim_..." },
  "derived_from": [{ "type": "segment", "id": "seg_..." }],
  "actor": "extractor.claim@2.3.1",          // who/what created it
  "at": "2026-09-13T12:01:00Z",              // when
  "using_parser": "parser.pdf@2.1.0",        // which parser
  "using_transformation": "claim_extraction_ruleset@2.3",
  "pipeline_version": "kb@5.0.0",            // which version
  "confidence": 0.82,                         // with what confidence
  "inputs_hash": "sha256:...",               // deterministic input fingerprint
  "epistemic_status": "inference"
}
```

### 24.3 Guarantees

- **Completeness:** no derived object exists without a provenance event linking it to
  inputs and a pipeline version (enforced at write time; violations are audit failures).
- **Determinism:** `inputs_hash` + `pipeline_version` reproduce the output — enabling
  verification and idempotent reprocessing.
- **Answerable questions:** where did this come from? using what parser/version? with what
  confidence? what else derived from the same inputs? (all direct graph queries.)

### 24.4 Recovery role

Provenance is what makes the whole knowledge/graph/index layer **rebuildable** from the
raw lake: replay provenance events (or re-run pipeline versions) to reconstruct derived
data deterministically ([`docs/23-disaster-recovery.md`](23-disaster-recovery.md)).

---

## 25. Claim system

**Purpose.** Represent claims **independently from documents**, so the same claim can be
supported/contradicted by many sources and tracked over time.

### 25.1 Claim record

```json
{
  "claim_id": "claim_01J9...",
  "subject": "entity:electron",
  "predicate": "has_property",
  "object": "quantized_charge",
  "conditions": { "context": "standard_model", "scope": "physics" },
  "source": "src_...",
  "source_version": "srcv_...",
  "timestamp": "2026-09-13T12:01:00Z",
  "evidence_type": "observed|claimed|derived|measured|cited",
  "extraction_method": "ruleset@2.3",
  "confidence": 0.9,
  "status": "supported|contradicted|qualified|superseded|unresolved|unknown",
  "contradictions": ["claim_..."],
  "supporting_claims": ["claim_..."],
  "conflicting_claims": ["claim_..."],
  "epistemic_status": "observation|inference|hypothesis|estimate|fact|assumption|unknown",
  "provenance_event_id": "prov_..."
}
```

### 25.2 Extraction (deterministic)

- Claims are extracted by **rule-based** subject–predicate–object patterns over the
  normalized structure (with typed predicates from a controlled vocabulary), plus dataset-
  and code-derived facts (e.g., "package X depends on Y").
- Every claim links to the exact `extracted_segment` it came from (provenance).
- Confidence reflects extraction certainty, **not** truth. Truth adjudication is not done;
  support/contradiction and evidence quality are (§26, §29).

### 25.3 Independence from copies

Because claims carry `source`/`source_version` and the dedup engine marks lineage,
**N copies of a claim from one lineage count as one independent claim** (§13 L4, §27
source independence, §42). Support is weighted by *independent* sources.

### 25.4 Status lifecycle

```
unknown ─▶ unresolved ─▶ {supported | contradicted | qualified} ─▶ superseded
```

Transitions are driven by the contradiction engine (§26) and temporal versioning (§27),
and are themselves recorded as provenance events.

### 25.5 Failure modes & observability

- Over-extraction (spurious claims) → confidence thresholds + review sampling (§44).
- Predicate ambiguity → controlled predicate vocabulary; unmapped predicates → `unknown`.
- Metrics: `claims_created_total`, `claims_contradicted_total`,
  `claims_superseded_total`, `claim_confidence` histogram.
