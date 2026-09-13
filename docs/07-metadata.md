# 15. Metadata Engine

**Purpose.** Extract, classify, integrity-protect, and manage metadata from every source
and object. Metadata is itself a first-class, tamper-aware data category — never trusted
blindly.

## 15.1 Metadata categories extracted

Source metadata · file metadata · document metadata · timestamps · authors (where
legitimately available) · publication metadata · repository metadata · schema metadata ·
technical metadata · media metadata · version metadata · provenance metadata ·
authorization metadata · processing metadata.

## 15.2 Epistemic classification of metadata (invariant)

Every metadata field carries an epistemic tag; the system never conflates them:

| Tag | Meaning | Example |
|-----|---------|---------|
| observed | Directly measured by Immanuel | byte size, fetch timestamp, HTTP status |
| claimed | Asserted by the source, unverified | document "author", "published" date in HTML meta |
| verified | Cross-checked against independent evidence | DOI resolves to matching title/author |
| derived | Computed by Immanuel from other data | detected language, inferred schema type |
| unknown | Not available | missing author, absent timestamp |

A `claimed` author never silently becomes a `verified` author.

## 15.3 Metadata record (shape)

```json
{
  "metadata_id": "meta_01J9...",
  "object_id": "obj_01J9...",
  "document_id": "doc_01J9...",
  "fields": [
    { "key": "author", "value": "A. Researcher", "epistemic": "claimed", "source_field": "meta[name=author]" },
    { "key": "published_at", "value": "2025-03-01", "epistemic": "claimed" },
    { "key": "fetched_at", "value": "2026-09-13T12:00:05Z", "epistemic": "observed" },
    { "key": "language", "value": "en", "epistemic": "derived", "confidence": 0.98 },
    { "key": "doi", "value": "10.1000/xyz", "epistemic": "verified", "verification": "resolver_match" }
  ],
  "integrity": { "hash": "sha256:...", "signed": true, "signer": "metadata-svc@1.0" },
  "anomalies": ["declared_type_mismatch"],
  "provenance_event_id": "prov_..."
}
```

## 15.4 Metadata integrity & tamper awareness

Metadata records are **integrity-protected** (hash + optional signature by the producing
service). The engine actively detects:

- **Tampering** — metadata hash mismatch vs recomputed value.
- **Inconsistency** — internal contradictions (e.g., `modified` < `created`).
- **Timestamp conflicts** — source-claimed dates conflicting with observed fetch/HTTP dates
  or with version history.
- **Identity mismatch** — author/owner claims conflicting across versions/mirrors.
- **Version mismatch** — declared version inconsistent with content hash lineage.
- **Provenance failure** — a derived object whose lineage chain is broken/missing.
- **Authorization mismatch** — content whose declared license/authorization disagrees with
  the source's registered authorization state.

Detected issues become **anomalies** attached to the record and surfaced to self-audit
(§44) and, if severe, to security alerts (§39/§40).

## 15.5 Media & technical metadata (non-sensitive)

Only **non-sensitive** technical/structural metadata is extracted (see media processing,
[`docs/08-processing.md`](08-processing.md)). Sensitive EXIF (e.g., GPS) is treated per
privacy policy ([`docs/19-security-privacy-policy.md`](19-security-privacy-policy.md)):
minimized, access-controlled, or dropped, per configuration — never surfaced by default.

## 15.6 Failure modes, observability, recovery

- **Failure modes:** absent metadata (→ `unknown`, never fabricated); conflicting metadata
  (→ anomaly, both values retained); poisoned metadata (→ anomaly + reduced trust weight).
- **Observability:** `metadata_anomalies_total{type}`, `verified_fields_ratio`,
  `metadata_integrity_failures_total`.
- **Recovery:** metadata is re-derivable from raw objects for `observed`/`derived` fields;
  `claimed` fields are preserved verbatim from the source in the raw lake.

## 15.7 Security considerations

- Metadata is untrusted external input (for `claimed` fields) → validated, size-capped,
  never used to make security or access decisions without corroboration.
- Integrity signing keys are managed by the secrets subsystem
  ([`docs/19-security-privacy-policy.md`](19-security-privacy-policy.md)).
