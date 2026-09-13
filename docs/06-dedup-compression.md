# 13. Deduplication Engine · 14. Compression Engine

## 13. Deduplication engine

**Purpose.** Avoid storing/treating the same information many times, and — critically —
avoid mistaking *copies* for *independent evidence*. Four levels, each with a distinct
mechanism and purpose.

### 13.1 Level 1 — Exact byte deduplication

- Mechanism: cryptographic content hash (`sha256`) of the raw bytes.
- Store keyed by hash; a re-acquisition of identical bytes is an **idempotent no-op** that
  adds a new *observation* (source + acquisition event) to the existing object.
- Purpose: storage savings + integrity + idempotency.

### 13.2 Level 2 — Normalized content deduplication

- Mechanism: hash of the **normalized** representation (after encoding/whitespace/structure
  canonicalization).
- Catches "same document, trivially different bytes" (different encodings, CRLF vs LF,
  reflowed whitespace, boilerplate wrapping).
- Produces a `normalized_content_hash`; equal hashes join a **duplicate group**.

### 13.3 Level 3 — Near-duplicate detection

- Mechanisms (deterministic, statistical — no ML): **shingling** (k-shingles of tokens),
  **MinHash** signatures, **SimHash** fingerprints, **LSH** banding for candidate
  generation, then **edit distance** / **structural similarity** for verification.
- Pipeline:
  ```
  normalized text ─▶ k-shingles ─▶ MinHash signature ─▶ LSH bucket ─▶
     candidate pairs ─▶ verify (Jaccard estimate + optional edit distance) ─▶
     similarity score ─▶ if ≥ threshold: link into duplicate_group (near-dup)
  ```
- Document fingerprints stored for fast re-comparison; thresholds are configurable per
  source class.

### 13.4 Level 4 — Source lineage deduplication

- **The anti-flooding level.** Detect when many sources carry the *same underlying
  content* (syndication, mirrors, scrapes-of-scrapes).
- Mechanism: cluster near-duplicates (L3) across sources, then analyze **publication
  lineage** — timestamps (who published first), link/citation graph, shared origin
  signals, hosting/ownership signals where public.
- Output: a **content lineage** where copies are marked as derivative, and only
  *independent* origins count as independent evidence.
- Feeds directly into data-poisoning resistance
  ([`docs/19-security-privacy-policy.md`](19-security-privacy-policy.md) / §42) and search
  ranking's "source independence" signal.

### 13.5 Core dedup objects

```json
{
  "canonical_content_object": "ccobj_01J9...",   // the representative
  "duplicate_group": "dg_01J9...",
  "members": [
    { "object_id": "obj_a", "level": "exact" },
    { "object_id": "obj_b", "level": "normalized" },
    { "object_id": "obj_c", "level": "near", "similarity": 0.94 }
  ],
  "source_references": ["src_a", "src_b", "src_c"],
  "lineage": { "origin": "src_a", "derivatives": ["src_b", "src_c"], "confidence": 0.8 },
  "independent_source_count": 1
}
```

Note the distinction: `source_references` may be large while `independent_source_count`
is small. **Downstream systems must use `independent_source_count`, never raw copy count,
as evidence weight.**

### 13.6 Failure modes & tradeoffs

- False merge (two distinct docs judged duplicate) → conservative thresholds; keep both
  raw objects always; merge only the *derived* layer, reversibly.
- False split (one doc judged distinct) → periodic re-clustering catches it.
- **Tradeoff:** aggressiveness vs precision — deduping too hard loses nuance; too little
  inflates evidence. Thresholds are per-source-class and audited (§44).
- Scale: LSH keeps near-dup candidate generation sub-quadratic; sharded by band.

### 13.7 Observability

`dedup_exact_ratio`, `dedup_normalized_ratio`, `near_dup_pairs_total`,
`lineage_clusters_total`, `independent_vs_copy_ratio`.

---

## 14. Compression engine

**Purpose.** Reduce storage cost **losslessly**, and report real savings.
**Semantic summarization is never treated as compression.**

### 14.1 Techniques (kept separate)

| Technique | Applies to | Notes |
|-----------|-----------|-------|
| Lossless storage compression | raw & normalized blobs | zstd/xz; tunable level per tier |
| Structural compression | structure trees, tables | encode structure compactly |
| Deduplication | across objects | see §13; the single biggest saver |
| Columnar compression | datasets/tables | Parquet-style column encoding |
| Delta encoding | document versions, volatile text | store diffs vs prior version |
| Dictionary encoding | repetitive categorical data | shared dictionaries per corpus slice |

### 14.2 Reporting

The system reports, per object / group / corpus:

```json
{
  "original_size": 10485760,
  "compressed_size": 2097152,
  "compression_ratio": 5.0,
  "deduplication_savings": 734003200,
  "total_storage_savings": 736100352
}
```

Compression and deduplication savings are reported **separately** so neither hides the
other.

### 14.3 Invariants

- Every compression path is **reversible**; the exact original bytes are recoverable
  (verified by re-hashing after decompression during periodic scrubs).
- Choice of codec/level is per storage tier: hot favors speed, cold favors ratio.
- Delta chains are bounded (periodic full snapshots) so restore cost stays bounded.

### 14.4 Failure modes & recovery

- Corrupt compressed blob → detected by hash mismatch → restore from replica/backup.
- Broken delta chain → rebuild from nearest full snapshot + raw lake.
- **Never** delete originals as a compression "optimization"; cold-tiering ≠ deletion.
