# 46. Disaster Recovery · 59. Data Lifecycle · 60. Privacy Controls

## 46. Disaster recovery

**Purpose.** Survive component, store, and region failures with bounded data loss and
recovery time, exploiting the raw-lake-as-backbone design.

### 46.1 Mechanisms

- **Backups** — PITR (point-in-time recovery) for relational stores; snapshots for config
  and pattern library.
- **Replication** — object storage multi-AZ (and multi-region for cold archives);
  relational primary + replicas; broker replication factor ≥ 3.
- **Snapshots** — periodic consistent snapshots of systems of record.
- **Restore procedures** — documented, tested runbooks per store.
- **Derived-store reconstruction** — search indexes and graph store rebuilt from systems of
  record + provenance (they are indexes, not records).
- **Queue recovery** — durable brokers; DLQ replay; consumers resume from offsets.
- **Discord recovery** — delivery state reconstructable; missed digests regenerated.
- **Configuration recovery** — versioned config restored from snapshot.

### 46.2 Recovery targets [PROPOSED]

| Data | RPO | RTO | Recovery method |
|------|-----|-----|-----------------|
| Raw lake | ~0 (replicated, immutable) | minutes (failover) | multi-AZ object storage |
| Relational SoR (jobs/claims/provenance/audit) | ≤ 5 min (PITR/WAL) | < 1 hr | restore + replica promote |
| Search indexes | n/a (derived) | hours (rebuild) | reindex from SoR |
| Graph store | n/a (derived) | hours (rebuild) | rebuild from relational adjacency/provenance |
| Event log | replication factor ≥ 3 | minutes | broker failover |
| Config / pattern library | ≤ 1 hr (snapshot) | < 1 hr | restore snapshot |

### 46.3 Failure scenarios & recovery sequence

- **Single service loss** → orchestrator reschedules; queues buffer; no data loss.
- **Store instance loss** → promote replica (relational) / failover (object store); resume.
- **Index/graph corruption** → serve from SoR for critical reads; rebuild derived store in
  background; swap in when caught up.
- **Region loss (stage 3–4)** → fail over to another region/cell; cold archives are
  multi-region; hot data re-warmed from replicas.

Recovery sequence (region failover): stabilize brokers → promote relational replicas →
point services at healthy region → resume queues from offsets → rebuild lagging derived
stores → verify provenance integrity → resume acquisition.

### 46.4 Verification

- DR runbooks are **tested** (game days); recovery/restore tests in the test strategy
  (§47). Provenance-integrity audit (§41) is run post-recovery to confirm no lineage gaps.

---

## 59. Data lifecycle

The complete lifecycle of a data object:

```
discovered → authorized → acquired → quarantined → validated → parsed → normalized →
   deduplicated → compressed → structured → classified → indexed → connected → exposed →
   updated → superseded → archived
```

- Each transition is an explicit, logged, provenance-emitting step.
- **Retention & deletion:** each object/category has a retention policy (source class +
  jurisdiction + privacy). On expiry (or takedown), content is deleted (tombstone + audit),
  and deletion **propagates** to derived indexes/graph via provenance links.
- **Supersession** is versioning, not deletion: superseded versions stay (temporal, §27)
  unless retention/privacy requires removal.

## 60. Privacy controls (summary; full detail in §38)

data minimization · retention rules · access controls · sensitive-metadata protection ·
audit logs · deletion workflows · source restrictions · privacy-aware indexing.

Invariant: **do not collect private information merely because it is technically
obtainable.** Deletion is honored end-to-end (raw → derived → index → graph), leaving only
a tombstone + audit record for integrity.
