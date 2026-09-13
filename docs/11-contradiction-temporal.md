# 26. Contradiction Engine · 27. Temporal Knowledge & Source Independence

## 26. Contradiction engine

**Purpose.** Actively detect conflicting claims and represent conflicts explicitly.
**Never simply select the first result.**

### 26.1 Detection

- Index claims by normalized `(subject, predicate)`; candidate conflicts are claims that
  share subject+predicate but differ in `object` (or in a measured value beyond tolerance).
- For candidate conflicts, run **discriminating analysis** across dimensions:
  definition · time · context · measurement · units · conditions · scope · population ·
  source lineage · source independence · methodology.

### 26.2 Resolution outcomes (explicit, never hidden)

```
resolved_contradiction   — one claim is demonstrably wrong given shared assumptions
contextual_difference    — both hold under different, stated contexts
superseded_claim         — a newer version replaces an older one (temporal)
measurement_difference   — different instruments/precision/tolerances
definition_difference    — terms defined differently across sources
unresolved_contradiction — genuine conflict, left open and surfaced
unknown                  — insufficient evidence to classify
```

The chosen outcome, the dimensions examined, and the evidence are stored as a
**Contradiction** record and linked to the involved claims (via `contradicts` edges).

### 26.3 Contradiction record

```json
{
  "contradiction_id": "contra_01J9...",
  "claims": ["claim_a", "claim_b"],
  "subject": "entity:material_x",
  "predicate": "melting_point",
  "dimensions_examined": ["units", "measurement", "conditions"],
  "outcome": "measurement_difference",
  "explanation": "claim_a in °C, claim_b in K; consistent after unit normalization",
  "independent_sources": { "claim_a": 3, "claim_b": 1 },
  "status": "resolved|unresolved|contextual|superseded|unknown",
  "provenance_event_id": "prov_..."
}
```

### 26.4 Interaction with ranking

The contradiction engine never picks a "winner" as truth. Search/ranking (§29) surfaces
*both* sides with their evidence quality, independent-source counts, recency, and
contradiction status — separating **relevance**, **evidence quality**, **source quality**,
**recency**, and **confidence**.

### 26.5 Failure modes & observability

- Missed conflicts (indexing gaps) → periodic full re-scan of high-value subjects.
- False conflicts (normalization gaps, e.g., units) → normalization improvements; each
  false positive is a self-audit signal (§44).
- Metrics: `contradictions_detected_total{outcome}`, `unresolved_contradictions`,
  `contradiction_scan_latency_ms`.

---

## 27. Temporal knowledge & source independence

### 27.1 Temporal versioning

Everything important supports versioning. Tracked lifecycle timestamps:

```
created · published · modified · retrieved · superseded · deleted · restored
```

- **Documents** are versioned (§67-style): a change creates a new version; differences are
  computed and stored; which **claims changed** is tracked.
- **Claims, edges, ontology nodes, patterns** carry `valid_from`/`valid_to` so the state of
  knowledge at any time is reconstructable.

### 27.2 Temporal queries

The system answers:

- *What was known at time `t`?* — filter objects to `valid_from ≤ t < valid_to`.
- *What changed between version A and B?* — diff claims/edges/structure.
- *Which claims disappeared?* — claims whose `valid_to` fell in `[A,B]`.
- *Which sources changed?* — source versions created in `[A,B]`.
- *Which relationships were added?* — edges with `valid_from` in `[A,B]`.

### 27.3 Document versioning model

```
document
 ├─ version 1 (object_id: obj_a, valid 2025-01..2025-06)
 ├─ version 2 (object_id: obj_b, valid 2025-06..2026-03)  diff(v1→v2) stored
 └─ version 3 (object_id: obj_c, valid 2026-03..present)  diff(v2→v3) stored
```

Versions are never overwritten; each maps to an immutable raw object. Deletion is a
**tombstone** (retention/privacy driven), not a hard erase of lineage, except where
privacy/legal deletion requires content removal — then the content is purged but the
provenance stub and audit record remain ([`docs/19-security-privacy-policy.md`](19-security-privacy-policy.md)).

### 27.4 Source independence (anti-flooding invariant)

**Do not equate number of copies with number of independent sources.**

```
source A ─(copies)→ source B ─(copies)→ source C ─(copies)→ source D
   ⇒ recognized as ONE information lineage ⇒ independent_source_count = 1
```

- Built on dedup L4 (§13): near-duplicate clustering + publication-lineage analysis
  (timestamps, citation/link graph, shared-origin signals).
- **Every evidence-weighting computation uses `independent_source_count`,** never raw copy
  count. This is enforced in claim support (§25), contradiction weighting (§26), ranking
  (§29), and data-poisoning resistance (§42).

### 27.5 Failure modes & observability

- Lineage misattribution (wrong "origin") → confidence-tagged; corrected on re-analysis;
  raw copies always retained.
- Metrics: `lineage_clusters_total`, `avg_copies_per_independent_source`,
  `temporal_versions_total`, `temporal_query_latency_ms`.
