# 54. Top 50+ Foreseeable Problems & Solutions

Each entry: **Problem · Cause · Impact · Detection · Prevention · Mitigation · Recovery.**
This is the design attacking itself (per §68). Compact format for density.

---

### Scale & throughput

**1. Crawl throughput hits per-host politeness ceiling**
Cause: politeness caps per host · Impact: slow coverage growth · Detect: `crawl_rate` vs
target · Prevent: scale *breadth* (more hosts), not depth · Mitigate: prioritize
high-value/volatile sources · Recover: rebalance scheduler shards.

**2. Source volume grows 100×**
Cause: successful discovery · Impact: registry/scheduler overload · Detect: registry write
rate, scheduler lag · Prevent: partition registry by domain hash; distributed scheduler ·
Mitigate: registration budgets, priority admission · Recover: add shards; backfill.

**3. Document volume grows 1000×**
Cause: rich sources/archives · Impact: processing + storage + index blowup · Detect:
`processing_rate`, `storage_growth` · Prevent: dedup L1–L4 + compression + tiering ·
Mitigate: autoscale parser pools; backpressure · Recover: rebuild lean derived stores.

**4. Queue backlog explosion**
Cause: consumer slower than producer · Impact: growing latency, memory pressure · Detect:
`queue_depth`, `oldest_message_age` · Prevent: backpressure + autoscaling · Mitigate:
shed low-priority work; add consumers · Recover: drain with temporary extra capacity.

**5. Graph becomes enormous / traversals slow**
Cause: edge growth super-linear · Impact: slow queries, DoS risk · Detect: `graph_size`,
traversal latency · Prevent: traversal budgets, partitioning, dedicated graph engine ·
Mitigate: cap depth/edges; precompute neighborhoods · Recover: shard/rebuild graph index.

**6. Ontology/taxonomy explosion**
Cause: unchecked subdomain discovery · Impact: unusable taxonomy · Detect:
`taxonomy_growth_rate`, pending candidates · Prevent: governance gates + growth cap (§22) ·
Mitigate: freeze auto-accept; operator review · Recover: roll back taxonomy version; re-cluster.

---

### Storage & bandwidth

**7. Storage cost balloons**
Cause: raw retention + copies · Impact: cost · Detect: `storage_bytes{tier}` trend ·
Prevent: dedup + compression + cold-tiering · Mitigate: aggressive lifecycle to cold ·
Recover: re-tier; prune per retention (never silent).

**8. Bandwidth waste re-downloading unchanged content**
Cause: no change detection · Impact: cost + load on sources · Detect: `crawl_304_ratio`
low · Prevent: ETag/If-Modified-Since/HEAD/hash (§52) · Mitigate: raise crawl interval ·
Recover: enable conditional requests per source.

**9. Cold-restore latency surprises users**
Cause: archived data accessed · Impact: slow reads · Detect: `cold_restore_latency` ·
Prevent: keep hot set well-sized; predictive warm-up · Mitigate: "restoring" UI state ·
Recover: promote/cache restored object.

**10. Object-store prefix hot-spotting**
Cause: sequential keys · Impact: throttling · Detect: store 503s · Prevent: hash fan-out
paths · Mitigate: spread writes · Recover: repartition prefixes.

---

### Internet & sources

**11. Internet changes in unanticipated ways (new formats/protocols)**
Cause: web evolves · Impact: parse gaps · Detect: rising `unknown` format rate · Prevent:
Format Registry + connector framework (extensible) · Mitigate: fallback path stores raw +
flags · Recover: add descriptor/connector; reprocess.

**12. Source blocks the crawler**
Cause: rate/UA/policy · Impact: coverage loss · Detect: 403/429 spikes, circuit trips ·
Prevent: politeness, honest UA, respect limits · Mitigate: back off; canary probes ·
Recover: honor block; mark source; do NOT evade.

**13. Source disappears / permanent 4xx**
Cause: content removed · Impact: stale data · Detect: sustained 404/410 · Prevent: n/a ·
Mitigate: mark `expired`; keep last raw version (temporal) · Recover: rediscover if it returns.

**14. Source impersonation / spoofed identity**
Cause: hostile actor · Impact: poisoned provenance · Detect: identity/lineage mismatch
(§40) · Prevent: source-identity signals, TLS validation · Mitigate: reduce trust weight;
alert · Recover: quarantine affected claims; re-verify.

---

### Data quality & poisoning

**15. Data poisoning: false claim on 10,000 sites**
Cause: coordinated flooding · Impact: fake "consensus" · Detect: lineage clustering, burst
detection · Prevent: independence counting (§27/§42) · Mitigate: weight by independent
sources; flag burst · Recover: re-cluster lineage; correct evidence weights.

**16. Duplicate floods inflate storage/evidence**
Cause: mirrors/syndication · Impact: cost + skew · Detect: `independent_vs_copy_ratio` ·
Prevent: dedup L1–L4 · Mitigate: registration budgets · Recover: merge duplicate groups.

**17. Near-duplicate false merge**
Cause: aggressive thresholds · Impact: lost distinctions · Detect: audit sampling ·
Prevent: conservative thresholds; keep all raw · Mitigate: reversible derived merge ·
Recover: re-split; recompute.

**18. Misclassification (wrong domain)**
Cause: weak signals · Impact: bad organization/search · Detect: `classification_error_rate`
· Prevent: multi-signal deterministic scoring; multi-domain allowed · Mitigate:
`unclassified` bucket · Recover: reweight + targeted reclassification.

**19. Metadata corruption / tampering**
Cause: hostile input / bug · Impact: broken lineage/trust · Detect: metadata integrity hash
mismatch (§40) · Prevent: hashing + signing · Mitigate: anomaly flag; distrust field ·
Recover: re-derive observed/derived fields from raw.

**20. Schema-inference errors on datasets**
Cause: dirty data · Impact: wrong types/keys · Detect: type-confidence low, parse-error
ratio · Prevent: uncertainty-preserving inference · Mitigate: flag; keep raw · Recover:
re-infer on improved rules.

---

### Parsing & processing

**21. Parser crash on malformed input**
Cause: hostile/broken file · Impact: worker loss · Detect: `parser_errors_total`, sandbox
kills · Prevent: sandbox isolation + limits · Mitigate: quarantine object; continue ·
Recover: fix parser; reprocess quarantined.

**22. Archive bomb / decompression attack**
Cause: malicious archive · Impact: resource exhaustion · Detect: ratio/byte/count/time caps
tripped · Prevent: strict caps + sandbox (§10) · Mitigate: abort + quarantine archive ·
Recover: none needed (contained); investigate source.

**23. Path traversal / symlink escape in archive**
Cause: crafted entry · Impact: FS write outside root · Detect: path validation rejects ·
Prevent: normalized-path checks, no symlink follow · Mitigate: reject entry/archive ·
Recover: contained.

**24. Non-deterministic normalization**
Cause: locale/lib nondeterminism · Impact: idempotency breaks, index churn · Detect:
determinism golden tests fail · Prevent: pin libs/locale; version normalization · Mitigate:
quarantine outputs · Recover: fix + reprocess version.

**25. OCR/transcription needed but absent (core is non-AI)**
Cause: scanned/media content · Impact: unindexed content · Detect: `requires_ocr` flag rate
· Prevent: n/a (by design) · Mitigate: store raw + flag · Recover: optional AI layer later.

---

### Search & API

**26. Search index corruption/loss**
Cause: cluster failure · Impact: degraded search · Detect: index health, checksum ·
Prevent: replicas; SoR is authoritative · Mitigate: serve from SoR for critical lookups ·
Recover: rebuild from SoR (§28).

**27. Indexing lag under write burst**
Cause: producer > index workers · Impact: stale results · Detect: `index_lag_seconds` ·
Prevent: backpressure; autoscale index workers · Mitigate: prioritize hot content ·
Recover: catch up; verify.

**28. API abuse / expensive queries**
Cause: pathological/hostile queries · Impact: infra exhaustion · Detect:
`query_budget_breaches_total` · Prevent: complexity budgets, rate limits (§62/§63) ·
Mitigate: reject `QUERY_TOO_COMPLEX`; circuit-break · Recover: tune budgets.

**29. Deep graph traversal DoS via API**
Cause: unbounded traversal · Impact: overload · Detect: traversal edge counts · Prevent:
depth/edge budgets · Mitigate: truncate + `truncated:true` · Recover: n/a.

**30. Search traffic 100×**
Cause: popularity · Impact: latency · Detect: `search_qps`, p95 · Prevent: caching +
read replicas + CDN · Mitigate: scale search nodes · Recover: add capacity.

---

### Distribution (Discord) & frontend

**31. Discord unavailable**
Cause: platform outage · Impact: no notifications/commands · Detect: delivery failures ·
Prevent: durable queue + degraded mode · Mitigate: queue digests; core unaffected ·
Recover: regenerate missed digests from event log.

**32. Discord rate limits / message flood**
Cause: too many events · Impact: throttling · Detect: `discord_rate_limited_total` ·
Prevent: aggregation windows (§33) · Mitigate: coalesce further · Recover: catch up.

**33. Frontend coupling to internals**
Cause: leaky API · Impact: brittle UI · Detect: contract-test breaks · Prevent: stable
API/BFF contract · Mitigate: version endpoints · Recover: shim old contract.

---

### Messaging, queues, workers

**34. Queue loses messages**
Cause: broker misconfig/failure · Impact: dropped work · Detect: reconciliation
(expected vs processed), offsets · Prevent: durable, replicated broker; outbox pattern ·
Mitigate: replay from event log/offsets · Recover: reprocess (idempotent).

**35. Worker crashes mid-processing**
Cause: bug/OOM · Impact: partial work · Detect: visibility-timeout redeliveries · Prevent:
idempotency + transactions/outbox · Mitigate: auto-reschedule · Recover: safe reprocess.

**36. Poison message loops**
Cause: unprocessable payload · Impact: retry storms · Detect: attempts→max, DLQ growth ·
Prevent: attempt caps + DLQ · Mitigate: route to DLQ; alert · Recover: fix + replay DLQ.

**37. Idempotency key collision / bug**
Cause: bad key derivation · Impact: duplicate/missing knowledge · Detect: dup-rate audit ·
Prevent: content-hash-based keys + tests · Mitigate: dedupe on write · Recover: reconcile
from provenance.

---

### Databases & infrastructure

**38. Primary database fails**
Cause: hardware/soft failure · Impact: write outage · Detect: health checks · Prevent:
replicas + PITR · Mitigate: promote replica · Recover: restore + resync (§46).

**39. Region becomes unavailable**
Cause: cloud region outage · Impact: partial/total outage · Detect: multi-region health ·
Prevent: multi-region raw lake + cells (§36) · Mitigate: fail over region/cell · Recover:
re-warm hot data; verify provenance.

**40. Hardware failure (node/disk)**
Cause: physical · Impact: capacity loss · Detect: node metrics · Prevent: redundancy,
replication · Mitigate: reschedule pods · Recover: replace; rebalance.

**41. Network partition between services**
Cause: infra · Impact: split-brain risk · Detect: connectivity probes · Prevent:
leader election, quorum · Mitigate: fence minority; queue buffers · Recover: heal + reconcile.

**42. Dependency (library/service) failure or vuln**
Cause: upstream · Impact: outage/security · Detect: dep scanning, health · Prevent: pin +
scan + isolate · Mitigate: fallback/disable feature · Recover: patch + redeploy.

---

### Security & privacy

**43. Compromised parser leads to code execution**
Cause: parser vuln + untrusted input · Impact: breach · Detect: sandbox anomaly, EDR ·
Prevent: strict sandbox, no egress, minimal creds, dedicated nodes (§41) · Mitigate:
isolate/kill node · Recover: rotate creds; rebuild node; patch parser.

**44. Secret leakage**
Cause: misconfig/log exposure · Impact: breach · Detect: secret scanning, audit · Prevent:
vault, short-lived creds, no secrets in logs · Mitigate: revoke/rotate · Recover: rotate all
affected; audit access.

**45. Authorization bypass on API**
Cause: authz bug · Impact: data exposure · Detect: authz tests, anomaly · Prevent:
deny-by-default, per-endpoint scopes · Mitigate: disable endpoint · Recover: patch + audit.

**46. Privacy violation (sensitive data indexed/exposed)**
Cause: over-collection/leak · Impact: harm + legal · Detect: privacy audits · Prevent: data
minimization, privacy-aware indexing, sensitive-field dropping (§38/§60) · Mitigate: purge
+ reindex · Recover: deletion workflow end-to-end; audit.

**47. Ignoring access restrictions (policy failure)**
Cause: policy bug/misconfig · Impact: legal/ethical breach · Detect: policy-decision audit ·
Prevent: policy engine as hard gate + `unknown`→conservative (§39) · Mitigate: block source ·
Recover: purge improperly acquired data; fix policy.

---

### Patterns & knowledge

**48. Pattern is wrong but appears temporarily successful**
Cause: overfit/coincidence · Impact: bad guidance · Detect: `usage/failure_history`,
re-eval triggers · Prevent: tests + falsifiers + scope + quarantine (§42) · Mitigate:
demote to hypothesis · Recover: reject/refine; flag downstream uses.

**49. Pattern library poisoned**
Cause: bad candidates accepted · Impact: systemic errors · Detect: pattern failure rate,
audit · Prevent: independence + tests before approval; conservative auto-accept · Mitigate:
freeze approvals · Recover: roll back pattern versions; re-evaluate.

**50. Unresolved contradictions accumulate**
Cause: genuine conflicts / detection gaps · Impact: user confusion · Detect:
`unresolved_contradictions` trend · Prevent: strong contradiction analysis (§26) ·
Mitigate: surface both sides honestly · Recover: re-scan; improve normalization (units etc.).

---

### Human & operational

**51. Administrator configuration mistake**
Cause: human error · Impact: outage/data issues · Detect: config audit, canary · Prevent:
versioned config, validation, dual-control for dangerous changes (§45) · Mitigate: rollback ·
Recover: restore prior version; post-incident review.

**52. Alert fatigue → missed real incident**
Cause: noisy alerts · Impact: slow response · Detect: alert volume/ack rate · Prevent:
severity tiers + aggregation · Mitigate: tune thresholds · Recover: incident review.

**53. Reprocessing storm after pipeline-version bump**
Cause: mass reprocess trigger · Impact: load spike · Detect: queue depth · Prevent:
throttled, targeted reprocessing · Mitigate: rate-limit reprocess jobs · Recover: pace out.

**54. Coverage blind spots (silent under-crawling of a domain)**
Cause: prioritization skew · Impact: gaps · Detect: coverage metrics per domain · Prevent:
coverage-gap prioritization (§6) · Mitigate: boost under-covered domains · Recover: backfill.

---

Each mitigation maps to a concrete mechanism elsewhere in the spec; none relies on AI. The
recurring themes — **immutable raw + provenance ⇒ rebuildability**, **independence over
copy-count ⇒ poison resistance**, **sandbox + limits ⇒ hostile-input safety**, **budgets ⇒
DoS resistance**, **versioning + rollback ⇒ human-error recovery** — are the load-bearing
defenses.
