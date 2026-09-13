# 20. Universal Ontology · 21. Domain Classification · 22. Dynamic Taxonomy

## 20. Universal knowledge ontology

**Purpose.** Represent human knowledge across all domains in an **extensible** hierarchy,
organized as a **tree** (for hierarchy) that co-exists with a **graph** (for cross-domain
relationships, §23).

### 20.1 Hierarchy levels

```
domain → subdomain → microdomain → concept → subconcept → entity →
property · process · mechanism · event · theory · method · artifact · system ·
dataset · document · claim · source
```

The ontology is **not** limited to science/technology/history/business — those are just
examples. It is a scalable, extensible schema (§22 governs growth).

### 20.2 Ontology node

```json
{
  "node_id": "onto_physics.quantum.tunneling",
  "level": "concept",
  "labels": ["quantum tunneling"],
  "parents": ["onto_physics.quantum"],          // tree edges (may be >1: DAG-lite)
  "definition_refs": ["claim_...", "doc_..."],
  "aliases": ["tunnelling"],
  "cross_domain_edges": ["onto_math...", "onto_cs..."],  // pointers into the graph
  "status": "active|candidate|deprecated",
  "version": 3,
  "provenance_event_id": "prov_..."
}
```

- The tree is a **DAG-lite**: a node may have multiple parents (a concept can legitimately
  belong to more than one branch), but cycles are forbidden in the *hierarchy* edges.
- Cross-domain relationships live in the graph, not the tree, keeping the hierarchy clean.

### 20.3 Pattern Forge domain integration (organizational reference)

The Pattern Forge domain set is used as an **organizational reference** for top-level
domains, e.g.: logic · reasoning · knowledge · information · mathematics · measurement ·
science · control · networks · complexity · design · interface · workflow · planning ·
creativity · morphology · biomimetics · evolution · ecology · physics · geometry ·
context · code · algorithms · data · technology · security · operations · manufacturing ·
economics · organization · institutions · law · value · human factors · education.

**These are not rigid silos.** Cross-domain membership and relationships are first-class.
Example (tree for hierarchy, graph for cross-links):

```
quantum computing
 ├─(tree) physics.quantum
 └─(graph) ─analogous_to→ information theory
           ─requires→ mathematics.linear_algebra
           ─enables→ cryptography.post_quantum
           ─part_of→ computer_science.computation
```

---

## 21. Domain classification

**Purpose.** Assign objects to domains **deterministically / rule-based** (no ML required),
producing **ranked candidates** and allowing multi-domain membership.

### 21.1 Signals

terminology (domain lexicons/TF-IDF against domain corpora) · metadata · document
structure · citations (cited venues/domains) · source category · link neighborhood ·
known entities present · schema · code syntax/language · mathematical structures ·
relationships · existing ontology placement of neighbors.

### 21.2 Method (deterministic scoring)

Each signal contributes a weighted vote; scores are combined and normalized:

```
score(domain) = Σ_i  w_i · signal_i(object, domain)
candidates = top-k domains by score, each with a normalized confidence
```

Example output:

```json
{
  "object_id": "doc_...",
  "domain_candidates": [
    { "domain": "physics", "confidence": 0.91 },
    { "domain": "mathematics", "confidence": 0.84 },
    { "domain": "computer_science", "confidence": 0.79 }
  ],
  "method": "rule_weighted_vote@2.0",
  "multi_domain": true
}
```

- **Multi-domain membership is allowed** — objects are not forced into one branch.
- Weights are configurable and versioned; classification is reproducible per version.
- **[EXPERIMENTAL]** An optional ML classifier could later augment (not replace) the
  deterministic scorer; it would contribute an additional weighted signal only.

### 21.3 Failure modes

- Ambiguous/low-confidence → object placed under a `general/unclassified` bucket with its
  candidates retained; never force-fit.
- Misclassification → detected by self-audit (§44: classification errors) and correctable
  by reweighting + targeted reclassification (idempotent).

---

## 22. Dynamic subdomain discovery (taxonomy governance)

**Purpose.** Let the taxonomy grow by discovering candidate new subdomains **without
uncontrolled explosion.**

### 22.1 Discovery process

```
existing knowledge ─▶ clustering (deterministic, e.g., graph community detection / MinHash
   clustering on terminology & entities) ─▶ recurring terminology ─▶ recurring entities ─▶
   recurring relationships ─▶ structural similarity ─▶ candidate cluster ─▶
   candidate subdomain ─▶ validation ─▶ ontology proposal ─▶ approval or auto-accept (policy)
```

### 22.2 Governance rules (anti-explosion) [PROPOSED]

A candidate subdomain must pass thresholds before proposal:

| Gate | Example threshold |
|------|-------------------|
| Minimum member size | ≥ N documents/entities (e.g., 200) |
| Cohesion | intra-cluster similarity ≥ τ_cohesion |
| Separation | distinct enough from existing subdomains (≥ τ_sep) |
| Stability | cluster persists across ≥ K re-clustering runs |
| Independence | members not all from one lineage (§13 L4) |

- Below thresholds → stays a **candidate** (quarantined), not part of the active taxonomy.
- Auto-accept only when *all* gates clear **and** policy allows; otherwise operator
  approval via the admin console (§45).
- **Merge/split governance:** near-duplicate subdomains are merged; over-broad ones are
  split — both are versioned, reversible operations.

### 22.3 Failure modes & observability

- **Taxonomy explosion** (main risk) → gated proposals + global growth-rate cap + operator
  review queue. Alert if candidate-generation rate exceeds a budget.
- Metrics: `taxonomy_nodes_total`, `taxonomy_candidates_pending`,
  `taxonomy_accepted_total`, `taxonomy_merges_total`, `taxonomy_growth_rate`.
- **Recovery:** taxonomy is versioned; a bad acceptance is rolled back to a prior version;
  affected classifications are recomputed.
