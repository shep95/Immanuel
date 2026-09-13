# 44. Observability · 45. Administration

## 44. Observability

**Purpose.** Make every plane measurable: metrics, logs, traces, audit events, health
checks, alerts.

### 44.1 Signals

- **Metrics** (time series) — counters/gauges/histograms per service (§74 schema).
- **Logs** — structured, correlated by `trace_id`/`request_id`; privacy-scrubbed.
- **Traces** — distributed tracing across planes (fetch → parse → index → serve).
- **Audit events** — append-only, tamper-evident, for privileged/admin actions.
- **Health checks** — liveness/readiness per service; dependency checks.
- **Alerts** — threshold + anomaly based; severity-tiered; routed to Discord/on-call.

### 44.2 Key measures (by concern)

| Concern | Metrics |
|---------|---------|
| Crawl | `crawl_rate`, `source_availability`, `fetch_latency_ms`, `crawl_304_ratio` |
| Processing | `processing_rate`, `parser_errors_total`, `parse_latency_ms` |
| Queues | `queue_depth`, `oldest_message_age`, `dlq_depth`, `retry_rate` |
| Storage | `storage_bytes{tier}`, `storage_growth_bytes_per_day`, `compression_ratio`, `dedup_savings_bytes` |
| Dedup | `dedup_exact_ratio`, `near_dup_pairs_total`, `independent_vs_copy_ratio` |
| Knowledge | `entities_created`, `claims_created`, `relationships_created`, `graph_size`, `knowledge_growth` |
| Search | `search_latency_ms{p50,p95,p99}`, `search_qps`, `cache_hit_ratio`, `index_lag_seconds` |
| API | `api_latency_ms`, `api_error_rate`, `rate_limited_total`, `query_budget_breaches_total` |
| Discord | `discord_publish_latency_ms`, `discord_queue_depth`, `discord_rate_limited_total` |
| Quality | `contradictions_detected_total`, `classification_error_rate`, `provenance_integrity_failures` |
| Security | `security_events_total{severity}`, `metadata_integrity_failures_total` |

### 44.3 Failure modes

- Metric/log pipeline overload → sampling + aggregation; metrics kept even if logs drop.
- Alert fatigue → severity tiers + digest aggregation (§33).
- Blind spots → coverage audit of instrumentation itself (§41 "audit the auditor").

---

## 45. Administration (control center)

**Purpose.** An internal admin console (separate admin boundary, MFA) for operating the
system.

### 45.1 Dashboard shows

total sources · active sources · failed sources · documents · entities · claims ·
relationships · patterns · storage · compression savings · deduplication savings ·
queue depth · worker count · crawler health · parser health · search health · API health ·
Discord health · security events · contradictions.

### 45.2 Admin capabilities

- **Source management** — register/pause/retire sources; adjust crawl policy & rate limits.
- **Policy management** — edit/version the access-policy engine (§39); requires audit + review.
- **Taxonomy governance** — approve/reject/merge/split candidate subdomains (§22).
- **Pattern governance** — approve/quarantine/reject patterns (§42).
- **Reprocessing** — trigger targeted reprocessing on a pipeline-version bump (idempotent).
- **Queue/DLQ operations** — inspect, replay, drain DLQs.
- **Config** — hot-reloadable, versioned, audited.
- **Incident tools** — surface findings from self-audit/root-cause (§41).

### 45.3 Admin security

- Separate authn + MFA; admin API only (not internet-exposed) (§30).
- Every admin action is audit-logged (who/what/when/before→after).
- Dangerous actions (policy change, mass reprocessing, deletion) require confirmation and,
  optionally, dual-control approval.

### 45.4 Failure modes & recovery

- Bad config/policy change → versioned; **rollback** to prior version; audit trail shows
  the change. (See §84 "administrator configuration mistake".)
- Admin console down → core keeps running; ops fall back to the admin API/CLI.
