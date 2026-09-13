# 47. Testing Strategy · 48. Benchmarking

## 47. Testing strategy

Testing spans correctness, safety, and adversarial resilience. **Adversarial and
pathological inputs are first-class.**

### 47.1 Test types

| Type | Focus |
|------|-------|
| Unit | Pure functions: canonicalization, hashing, schema inference, scoring. |
| Integration | Stage-to-stage flows (fetch→parse→normalize→index). |
| Contract | Event & API schemas between services (schema-version compatibility). |
| Parser | Per-format parsers against a golden corpus + malformed variants. |
| Fuzz | Feed random/mutated bytes to parsers/archive handler; expect no crash/escape. |
| Load | Sustained throughput at target rates per stage. |
| Stress | Beyond capacity; verify graceful degradation + backpressure. |
| Failure injection | Kill workers/brokers/stores mid-flight; verify idempotency & recovery. |
| Recovery | Restore-from-backup, index/graph rebuild, region failover drills. |
| Security | SSRF, path traversal, zip bombs, injection, authz bypass attempts. |
| Data integrity | Hash round-trips, provenance-chain completeness, no-silent-loss. |
| Deduplication | L1–L4 correctness; false-merge/false-split rates on labeled sets. |
| Compression | Lossless round-trip; reported-savings accuracy. |
| Search relevance | Fixed query set with judged results; track relevance metrics. |
| Graph integrity | No dangling edges; temporal validity consistency; traversal budgets. |
| API | Endpoint contracts, error envelopes, rate-limit/complexity enforcement. |
| Discord integration | Aggregation correctness, rate-limit handling, degraded-mode. |

### 47.2 Adversarial / pathological suite (must-have)

- Zip/xz bombs (nested + flat), path-traversal archives, symlink-escape archives.
- Malformed PDFs/HTML/XML/JSON; huge single-line files; deeply nested JSON/XML.
- Encoding attacks (mixed/invalid encodings, homoglyphs, BOM tricks).
- Copy-flood scenario: same claim from N synthetic sources → assert
  `independent_source_count` stays ~1 and ranking is unaffected.
- Poisoned metadata (spoofed timestamps/authors) → assert tamper detection fires.
- SSRF payloads (link-local/metadata IPs) → assert fetch is refused.
- Query bombs (deep graph traversal, wildcard explosions) → assert `QUERY_TOO_COMPLEX`.

### 47.3 Determinism tests

For every deterministic stage: same input + same pipeline version ⇒ byte-identical output
(golden tests). This underpins idempotency and rebuildability.

### 47.4 CI posture [PROPOSED]

- Unit + contract + parser + fuzz (short) on every change.
- Integration + security + determinism nightly.
- Load/stress/recovery on a schedule + before releases.
- A **SessionStart-style** setup ensures tests/linters run in any environment.

---

## 48. Benchmarking

Benchmark datasets + metrics to track performance and catch regressions.

| Benchmark | Metric | Dataset |
|-----------|--------|---------|
| Crawl throughput | pages/sec at fixed politeness | synthetic source farm + recorded fixtures |
| Parse throughput | docs/sec per format | mixed-format corpus |
| Deduplication accuracy | precision/recall of near-dup + lineage | labeled duplicate/lineage set |
| Compression ratio | ratio + throughput | representative corpus slices |
| Storage efficiency | bytes stored / bytes ingested (after dedup+compress) | full-pipeline sample |
| Search latency | p50/p95/p99 at target QPS | fixed query set + corpus |
| Graph traversal latency | ms per bounded traversal | graph of known size |
| API latency | p50/p95/p99 per endpoint | replayed traffic |
| Discord publishing latency | event→delivered ms | event burst fixtures |
| Failure recovery | RTO measured | DR drills |
| Source update detection | detection lag; 304-hit ratio | volatile source fixtures |

- Benchmarks run against **pinned datasets** so results are comparable over time.
- Regressions beyond a threshold fail the release gate.
- Results feed the cost model (§49) and scalability planning (§36).
