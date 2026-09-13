# 37. Security · 38. Privacy · 39. Access Policy · 40. Metadata Security · 41. Input Security · 42. Data-Poisoning Resistance

## 37. Security architecture

Security is present **throughout** the architecture, modeled explicitly.

### 37.1 Security model

| Element | Immanuel instance |
|---------|-------------------|
| Assets | raw lake, knowledge stores, provenance, secrets, config, pattern library. |
| Actors | operators, API consumers, frontend, Discord users, internal services, internet sources (untrusted). |
| Identities | per-service identities (mTLS/SPIFFE-style), per-operator (MFA), per-API-key. |
| Permissions | least-privilege scopes per identity per resource/action. |
| Trust boundaries | internet→quarantine, quarantine→processing, public API→internal, admin boundary. |
| Resources/actions | read/write per store; fetch; reprocess; config change; policy change. |
| Data flows | mapped per plane (see §80 diagram). |
| Controls | below. |
| Audit events | every privileged action logged immutably. |

### 37.2 Controls

authentication · authorization (deny-by-default) · least privilege · isolation
(sandboxes for untrusted processing) · network segmentation between planes · secrets
management (vault; short-lived creds; no secrets in code/env dumps) · encryption
(in transit TLS, at rest per store) · integrity verification (content + metadata hashes) ·
audit logging (append-only, tamper-evident) · privacy controls (§38) · data minimization ·
retention · recovery.

### 37.3 Protecting the system from hostile input

The single most important security posture: **all acquired data is untrusted.** Parsing/
extraction of untrusted bytes runs in **isolated, resource-capped sandboxes** on dedicated
nodes with no credentials beyond their narrow task. Details in §41.

---

## 38. Privacy

Privacy controls throughout:

- **Data minimization** — do not collect private information merely because it's
  technically obtainable. Only public, lawful data; sensitive fields minimized/dropped.
- **Retention rules** — per source class & data category; expiry drives deletion (§59).
- **Access controls** — sensitive metadata (e.g., GPS EXIF) is access-controlled or removed
  by default.
- **Sensitive-metadata protection** — flagged, minimized, never surfaced by default.
- **Audit logs** — access to any sensitive data is logged.
- **Deletion workflows** — honor source restrictions and takedown/deletion requests:
  content is purged, a tombstone + audit record remains, and derived indexes/graph are
  updated (deletion propagates through provenance).
- **Privacy-aware indexing** — sensitive fields are excluded from public indexes; query
  logs are privacy-scrubbed.

## 39. Access / legal policy layer

An **explicit policy engine** evaluates every source/acquisition **before** fetching.

### 39.1 Inputs evaluated

`robots` restrictions · terms where applicable · authentication requirements · rate limits
· copyright-related handling · source restrictions · jurisdictional requirements ·
retention requirements.

### 39.2 Access state (represented explicitly)

```
allowed · restricted · requires_authorization · temporarily_unavailable · disallowed · unknown
```

### 39.3 Rules (invariant)

- **Never bypass restrictions.** `disallowed` / `requires_authorization` sources are not
  fetched. No defeating of authentication, paywalls, encryption, or access controls.
- The policy engine is consulted at discovery (register vs skip), at scheduling (due vs
  block), and at fetch (final gate). Decisions are logged with the rule that fired.
- Policy is **config-driven and versioned**; legal review supplies jurisdictional inputs
  (the engine enforces, it does not decide law).
- `unknown` defaults to the **most conservative** action (do not fetch body content) until
  resolved.

### 39.4 Policy record

```json
{
  "source_id": "src_...",
  "decision": "allowed|restricted|requires_authorization|temporarily_unavailable|disallowed|unknown",
  "rules_applied": ["robots:allow /data/", "rate_limit:20rpm", "jurisdiction:EU:retention_30d"],
  "evaluated_at": "2026-09-13T12:00:00Z",
  "policy_version": "policy@4.1.0"
}
```

---

## 40. Metadata security

Metadata is **tamper-aware** (see [`docs/07-metadata.md`](07-metadata.md)). Protected:
timestamps · source identity · classification · provenance · versions · authorization
state · audit records. Detected: metadata tampering · timestamp inconsistencies · identity
mismatches · broken lineage · spoofed metadata · unauthorized modification. Integrity is
enforced by hashing + signing; violations raise `security.event` and reduce trust weight.

---

## 41. Input security

**Assume internet data is hostile or malformed.** Protections:

| Threat | Control |
|--------|---------|
| Malformed documents | parsers isolated; failures contained, not fatal |
| Malicious archives | strict sandbox + limits (§10) |
| Resource exhaustion | CPU/mem/time/byte caps (cgroups, wall-clock kills) |
| Path traversal | normalized-path checks, no symlink escape |
| Parser crashes | sandbox isolation; one object quarantined, pipeline continues |
| Oversized files | streaming size caps; fail fast |
| Decompression attacks | ratio + absolute caps (§10) |
| Malformed encoding | safe transcoding; low-confidence flag |
| Unexpected schemas | uncertainty-preserving inference; anomaly flags |
| Poisoned metadata | tamper detection (§40); not used for security decisions |
| Duplicate floods | dedup L1–L4 + registration budgets |
| Source impersonation | source-identity verification signals; lineage analysis |

**All untrusted processing is isolated** on dedicated, credential-minimal nodes with no
network egress.

---

## 42. Data-poisoning resistance

**One false claim on 10,000 websites is NOT 10,000 confirmations.**

- Evidence weight uses **`independent_source_count`** (dedup L4 + lineage, §13/§27), never
  raw copy count.
- Tracked signals: lineage · source independence · publication relationships · timestamps
  (who first) · content similarity · shared origins.
- Ranking (§29) and claim support (§25) are copy-flood-resistant by construction.
- Sudden coordinated floods (same content, many new sources, tight time window) raise a
  `security.event` / contradiction/anomaly for review, and expansion budgets throttle the
  source burst (§6).
- **[EXPERIMENTAL]** Additional anomaly heuristics (burst detection, hosting-cluster
  signals) can augment this; they are additive, not core dependencies.
