# 11. Raw Data Lake · 12. Normalization Engine

## 11. Raw data lake

**Purpose.** Preserve acquired content as closely as practical, immutably, with integrity
guarantees. The raw lake is the **system of record** from which everything else can be
rebuilt.

### 11.1 Principles

- **Immutable.** Objects are write-once; never overwritten or edited.
- **Content-addressed.** Stored under a path derived from `sha256` (self-verifying).
- **Versioned by nature.** A new source representation → a new object; nothing is lost.
- **Cheap to store, cheap to verify.** Integrity via stored hash + periodic scrubbing.

### 11.2 Raw object record

```json
{
  "object_id": "obj_01J9...",
  "content_hash": "sha256:abcd...",         // == storage address
  "source_id": "src_01J9...",
  "acquisition_id": "acq_01J9...",
  "ingestion_id": "ing_01J9...",
  "timestamp": "2026-09-13T12:00:05Z",
  "format": "pdf",                            // detected
  "declared_media_type": "application/pdf",
  "size_bytes": 1048576,
  "storage_location": "s3://immanuel-raw/sha256/ab/cd/abcd...",
  "storage_tier": "hot|warm|cold",
  "integrity_status": "verified|unverified|failed",
  "compression": { "codec": "zstd", "stored_bytes": 486000 },
  "parent_object_id": null,                   // set for files extracted from archives
  "in_archive_path": null,                    // e.g. "project/data.csv"
  "provenance_event_id": "prov_01J9..."
}
```

**Keys/indexes:** PK `object_id`; unique on `content_hash` (dedup L1 is a no-op insert);
indexes on `source_id`, `timestamp`, `storage_tier`, `integrity_status`.

### 11.3 Storage layout & tiering

- Path: `sha256/<aa>/<bb>/<full-hash>` (2-level fan-out to avoid hot prefixes).
- Compression at rest with a fast lossless codec (zstd) — this is *storage* compression,
  never semantic reduction (see [`docs/06-dedup-compression.md`](06-dedup-compression.md)).
- Lifecycle: hot → warm → cold by access recency and age
  ([`docs/17-storage.md`](17-storage.md)).

### 11.4 Integrity

- On write: compute and store `sha256`; verify the round-trip read.
- Background **scrubber** periodically re-reads a sample and re-hashes; `integrity_status`
  flips to `failed` on mismatch → repair from replica/backup → alert.
- Object store versioning + Object Lock (WORM) for immutability enforcement [PROPOSED].

### 11.5 Failure modes & recovery

- Duplicate write (same hash) → idempotent no-op; add a new *observation* linking the
  existing object to the new acquisition event.
- Store outage → writes buffered in the acquisition queue (backpressure), not dropped.
- Corruption → detected by scrubber, repaired from replication/backups
  ([`docs/23-disaster-recovery.md`](23-disaster-recovery.md)).

---

## 12. Normalization engine

**Purpose.** Convert heterogeneous source material into standardized structures for
downstream processing **without destroying source-specific information**. Both the
**original** and the **normalized** representations are preserved.

### 12.1 Normalization dimensions

| Dimension | What it does |
|-----------|--------------|
| Encoding | Detect charset; transcode to UTF-8; preserve original encoding tag. |
| Character | Unicode NFC normalization; control-char handling; homoglyph flagging (not rewriting). |
| Date/time | Parse to RFC3339/UTC; keep original string + parsed value + timezone confidence. |
| Units | Recognize + annotate units (SI canonical) without discarding original units. |
| Schema | Map source schemas to internal canonical schemas via declarative mappings. |
| Metadata | Canonicalize key names/types (see metadata engine). |
| Language | Deterministic language identification (n-gram/dictionary based); store confidence. |
| Document structure | Build a normalized structure tree (sections→…→sentences). |
| Table | Detect + normalize tabular structures (headers, types, null patterns). |
| Code structure | Language-aware structural parse (see code engine). |
| Link | Canonicalize/resolve links relative to base; classify (internal/external/anchor). |
| Identifier | Recognize + canonicalize identifiers (DOI, ISBN, ORCID, package coords, commit SHAs). |

### 12.2 Dual representation (invariant)

```
RawObject ──parse──▶ OriginalRepresentation (faithful, structure-preserving)
                              │
                              └─normalize─▶ NormalizedRepresentation (canonical)
```

Both are stored and linked; normalization is **additive**, never destructive. If a
normalization step is lossy by nature (e.g., collapsing whitespace), the original is
retained and the transformation is recorded in provenance.

### 12.3 NormalizedDocument (shape)

```json
{
  "document_id": "doc_01J9...",
  "object_id": "obj_01J9...",              // raw source
  "format": "pdf",
  "language": { "code": "en", "confidence": 0.98, "method": "trigram" },
  "encoding_original": "windows-1252",
  "structure_ref": "docstruct_01J9...",     // pointer to structure tree
  "normalized_text_ref": "s3://…/norm/…",   // canonical text stream
  "tables": ["tbl_...", "tbl_..."],
  "links": ["lnk_...", "..."],
  "identifiers": [{ "type": "doi", "value": "10.1000/xyz" }],
  "normalization_version": "norm@3.2.0",
  "epistemic_status": "observation",
  "provenance_event_id": "prov_..."
}
```

### 12.4 Determinism

Normalization is deterministic per `normalization_version`. Re-running the same version on
the same raw object yields byte-identical normalized output — required for idempotency and
for cache/index rebuilds.

### 12.5 Failure modes, observability, recovery

- **Failure:** undetectable encoding → best-effort + low-confidence flag; malformed
  structure → partial tree + anomaly. Never a hard crash on well-formed-but-weird input.
- **Observability:** `normalization_latency_ms`, `normalization_failures_total`,
  `language_id_confidence` histogram, `encoding_detected` breakdown.
- **Recovery:** normalized artifacts are fully re-derivable from the raw lake; a
  normalization bug fix bumps `normalization_version` and triggers targeted reprocessing.
