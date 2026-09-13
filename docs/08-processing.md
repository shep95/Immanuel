# 16. Document · 17. Code · 18. Dataset · 19. Media Processing

Four specialized processors turn normalized objects into structured, connectable data.
None treats its input as an undifferentiated blob.

---

## 16. Document structure engine

**Purpose.** Decompose documents into a structural tree and preserve relationships.

### 16.1 Structure model

```
document
 └─ sections
     └─ subsections
         └─ paragraphs
             └─ sentences
 ├─ tables (rows, cells, headers)
 ├─ figures (captions, refs)
 ├─ equations
 ├─ references / citations
 ├─ footnotes
 ├─ code blocks
 └─ metadata
```

Each node has: `node_id`, `parent_id`, `order`, `type`, `text_ref`/`payload`,
`char_span`, and back-links to the source object (provenance). Structural relationships
(e.g., "sentence S cites reference R", "figure F is referenced by paragraph P") are
preserved as edges into the knowledge graph.

### 16.2 Segmentation

- Deterministic sentence/paragraph segmentation (rule + dictionary based; language-aware).
- Tables extracted with header detection and per-column type inference (see §18).
- Citations/references parsed into structured records (authors, title, identifiers) and
  linked to sources when resolvable (`verified` metadata).

### 16.3 Failure modes

- Poorly-structured PDFs → best-effort tree + `low_structure_confidence` flag; text still
  captured.
- OCR is **not** implied for scanned docs in the core; flagged as `requires_ocr`
  (optional future component). No AI dependency in the core path.

---

## 17. Code analysis engine

**Purpose.** Treat source code as structured artifacts, not text.

### 17.1 Entities extracted

repository · project · directory · file · module · package · class · function · method ·
variable · constant · interface · api · dependency · import · export · configuration ·
build system · test · documentation.

### 17.2 Graphs constructed (deterministic, static analysis)

- **Dependency graph** (package/module deps from manifests + imports).
- **Call graph** (static, per language; best-effort for dynamic languages, confidence-tagged).
- **Module graph** (file/module import structure).
- **Data flow** and **control flow** (per-function, where the language permits static
  derivation).
- **Temporal flow / state transitions** (from VCS history + explicit state machines where
  declared).
- **Invariants** and **failure relationships** (from assertions, tests, error handling).

### 17.3 Method

- Language-aware parsing to a concrete/abstract syntax tree (per-language grammar; e.g.,
  tree-sitter-style parsers). Deterministic, no execution.
- **Acquired code is never executed.** Analysis is purely static. Parsing runs in the same
  sandbox class as other untrusted input.
- Dynamic/reflective constructs → edges tagged `low_confidence` or `unresolved`, never
  guessed as fact.

### 17.4 Outputs

Code entities + relationships flow into the knowledge graph (`is_a`, `part_of`,
`requires`, `imports`, `calls`, `tests`, `fails_under`, `repairs`, …) with provenance to
the exact file/commit. Enables code search (§28) and cross-domain pattern transfer (§43).

### 17.5 Failure modes

- Unparseable/partial files → partial tree + anomaly; never abort the repo.
- Huge monorepos → per-file work units; graph assembled incrementally/idempotently.

---

## 18. Dataset engine

**Purpose.** Understand structured/tabular data while **preserving uncertainty** in
inferred schemas.

### 18.1 Detection

tables · columns · rows · keys · foreign keys · relationships · schemas · types · units ·
null patterns · duplicate records · missing values · outliers · versioning · lineage.

### 18.2 Supported formats

csv · tsv · json · xml · parquet · database exports · structured API responses · other
machine-readable datasets (via the format registry).

### 18.3 Schema inference (uncertainty-preserving)

- Per column: infer type by deterministic voting over cell parses (int/float/date/bool/
  string/enum), record **type confidence** and the distribution of parse outcomes.
- Detect candidate keys (uniqueness), candidate foreign keys (value-set containment across
  tables), null/missing patterns, and outliers (statistical, e.g., IQR/z-score — not ML).
- Inferred schema is **proposed**, not asserted: stored with confidence and the evidence
  (sample counts). Conflicts (e.g., a column that is 98% int, 2% string) are surfaced, not
  silently coerced.

### 18.4 Dataset record

```json
{
  "dataset_id": "ds_01J9...",
  "object_id": "obj_...",
  "format": "csv",
  "row_count": 120345,
  "columns": [
    { "name": "id", "inferred_type": "int", "type_confidence": 1.0, "candidate_key": true, "null_ratio": 0.0 },
    { "name": "value", "inferred_type": "float", "type_confidence": 0.98, "outlier_ratio": 0.01 }
  ],
  "candidate_foreign_keys": [{ "column": "user_id", "references": "ds_users.id", "confidence": 0.87 }],
  "epistemic_status": "derived",
  "schema_version": "inferred@1"
}
```

### 18.5 Failure modes

- Malformed rows → quarantined rows + `parse_error_ratio`; the dataset is still ingested.
- Ambiguous delimiters/encodings → dialect sniff with confidence; low confidence flagged.

---

## 19. Media processing

**Purpose.** Extract available **non-sensitive** technical/structural information; preserve
the original media object separately from derived representations.

### 19.1 Images

dimensions · format · metadata · EXIF (where legitimately available **and** non-sensitive) ·
embedded text (if present as text, not OCR in core) · visual structure (deterministic
descriptors) · similarity fingerprints (perceptual hashes: aHash/dHash/pHash for
near-duplicate detection).

### 19.2 Audio

duration · codec · sample rate · channels · metadata (ID3/Vorbis/etc.) · transcript
(**only where permitted**, optional component) · speech segments (VAD-based, deterministic)
· sound structure (silence/segment boundaries).

### 19.3 Video

duration · codec · frames · scenes (deterministic shot-boundary detection) · subtitles
(embedded tracks) · audio track (as above) · metadata · timestamps.

### 19.4 Invariants

- Original media stays in the raw lake, untouched; derived descriptors are separate objects
  with provenance.
- **Sensitive metadata (e.g., GPS in EXIF) is governed by privacy policy** — minimized or
  dropped by default; never surfaced without explicit configuration and access control.
- **No AI required:** transcription/vision models are explicitly *optional future
  components*; the core extracts only deterministic technical/structural data.

### 19.5 Failure modes & observability

- Unsupported codecs → technical metadata only + `codec_unsupported` flag.
- Corrupt media → header-only extraction + anomaly.
- Metrics: `media_processed_total{kind}`, `perceptual_hash_dupes_total`,
  `media_parse_failures_total`.
