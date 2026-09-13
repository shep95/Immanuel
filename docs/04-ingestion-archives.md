# 9. Universal File Ingestion · 10. Archive Processing

## 9. Universal file ingestion

**Purpose.** Recognize and process as many legitimate digital formats as practical, via a
data-driven **Format Registry** so new formats are added without rewriting the ingestion
architecture.

### 9.1 Format detection (deterministic)

Detection is layered and does **not** trust the declared media type alone:

1. **Magic bytes / signatures** (e.g., `%PDF-`, `PK\x03\x04`, `\x1f\x8b`, `ID3`, PNG/JPEG
   signatures). Highest precedence.
2. **Structural probes** (well-formed XML? valid JSON? UTF-8 BOM? CSV dialect sniff?).
3. **Declared media type** (`Content-Type`) and **filename extension** as *hints only*.
4. **Registry resolution** → a `FormatDescriptor` (parser, limits, category).

Conflicts (declared type ≠ detected type) are recorded as a **metadata anomaly**
([`docs/07-metadata.md`](07-metadata.md)) and the detected type wins.

### 9.2 Format categories & minimum coverage

- **Web/markup:** html, css, javascript, json, xml, yaml, csv, tsv, txt, markdown.
- **Documents:** pdf, doc, docx, odt, rtf, xls, xlsx, ods, ppt, pptx, epub, latex.
- **Archives:** zip, 7z, tar, gz, bz2, xz, rar, tgz, tbz (see §10).
- **Code:** python, javascript, typescript, c, cpp, csharp, java, go, rust, ruby, php,
  swift, kotlin, dart, r, julia, matlab, sql, shell, powershell, lua, perl, assembly,
  webassembly; plus configuration files, dependency manifests, schema files, API
  definitions.
- **Media:** png, jpeg/jpg, webp, gif, svg, tiff, bmp, heic; mp3, wav, flac, aac, ogg,
  m4a, opus; mp4, mkv, mov, avi, webm, mpeg.

> This list is **not** assumed complete — the registry is the extension point.

### 9.3 Format Registry [PROPOSED]

```json
{
  "format_id": "pdf",
  "category": "document",
  "detectors": [{ "type": "magic", "signature": "25504446" }],
  "media_types": ["application/pdf"],
  "extensions": [".pdf"],
  "parser": "parser.pdf@2.1.0",
  "limits": { "max_bytes": 536870912, "max_pages": 20000, "max_time_s": 120, "max_mem_mb": 1024 },
  "sandbox_profile": "document-strict",
  "enabled": true,
  "epistemic_default": "observation"
}
```

- Registry is stored in the config DB and hot-reloadable.
- A **fallback descriptor** handles `unknown` formats: store raw, extract only
  size/hash/detected-type, mark for operator review — never silently drop.

### 9.4 Ingestion flow

```
IngestionObject ─▶ detect format ─▶ resolve FormatDescriptor ─▶ select parser + limits ─▶
   ├─ archive?  ─▶ archive processor (recursive; §10)
   ├─ known?    ─▶ parser (sandboxed) ─▶ extraction ─▶ normalization
   └─ unknown?  ─▶ fallback: raw + minimal metadata + review flag
```

### 9.5 Failure modes

- Unknown/ambiguous format → fallback path, never a crash.
- Parser mismatch → detected type wins; anomaly logged.
- Corrupt/malformed file → parser runs in sandbox, failure captured as a
  `parser.failed` outcome with the object quarantined for review, pipeline continues.

---

## 10. Archive processing

**Purpose.** Safely inspect archives recursively, e.g.
`archive.zip → project.tar.gz → dataset.zip → documents.pdf`, while resisting
decompression attacks.

### 10.1 Threat-driven design

All untrusted archive processing occurs inside an **isolated processing environment**
(sandbox: no network, read-only FS except a capped scratch dir, dropped capabilities,
seccomp profile, cgroup limits). Protections against:

- **Archive/zip bombs** (nested + flat) — enforce ratio and absolute-byte caps.
- **Path traversal** (`../`, absolute paths, symlink escape) — reject entries whose
  normalized path escapes the extraction root; never follow symlinks out of root.
- **Recursive archive explosions** — depth cap.
- **Excessive extraction / file counts** — byte and count caps.
- **Malformed archives** — parser isolation; failure is contained.
- **Decompression abuse / resource exhaustion** — time, memory, CPU caps.

### 10.2 Hard limits (configurable) [PROPOSED]

| Limit | Default | Enforcement |
|-------|---------|-------------|
| Max recursion depth | 8 | counter per lineage chain |
| Max total extracted bytes | 5 GiB per top-level archive | running sum; abort on breach |
| Max compression ratio | 200:1 (per entry & aggregate) | ratio guard streaming |
| Max file count | 100,000 | counter; abort on breach |
| Max processing time | 300 s | wall-clock kill |
| Max memory | 1 GiB | cgroup `memory.max` |
| Max CPU | 1 core-equivalent | cgroup `cpu.max` |

Breaching any limit → abort the whole archive, quarantine it, emit `parser.failed`
with reason, and continue. Partial extraction results are discarded (idempotency).

### 10.3 Recursive inspection

```
archive (depth d) ─▶ for each entry:
   validate path (no traversal) ─▶ enforce per-entry ratio/size ─▶ update running totals ─▶
   detect format(entry) ─▶
      ├─ archive AND d < MAX_DEPTH ─▶ recurse (depth d+1)  [each nested item keeps lineage]
      └─ file ─▶ emit child IngestionObject (raw_ref, parent_ingestion_id, path-in-archive)
```

Every extracted file becomes a **first-class object** with provenance pointing to its
containing archive and its path within it — lineage is preserved through nesting.

### 10.4 State, observability, recovery

- **State:** extraction is stateless per archive; scratch space is ephemeral.
- **Observability:** `archive_depth`, `archive_extracted_bytes`, `archive_file_count`,
  `archive_bombs_detected_total`, `archive_time_ms`.
- **Recovery:** archives live immutably in the raw lake; re-extraction is deterministic
  and idempotent (child object IDs derive from parent hash + in-archive path + child hash).

### 10.5 Security note

Archive processing is one of the highest-risk ingress surfaces. It runs in the **strictest
sandbox profile**, on **dedicated worker nodes** separate from knowledge/search services,
with no credentials beyond raw-lake write for the specific object lineage.
