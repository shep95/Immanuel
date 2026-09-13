# Schemas — Database (71) · API (72) · Event (73) · Observability (74)

Conceptual schemas. Types are illustrative (PostgreSQL-flavored). IDs are ULIDs unless
noted. Timestamps are `timestamptz` (UTC). Every record that can be derived carries
`provenance_event_id`; every important record is versioned.

---

## 71. Database schemas

### source
```
source_id           text PK
source_type         text        -- website|api|graphql|rss|atom|sitemap|git|dataset|…
canonical_location  text        UNIQUE(domain, canonical_location)
domain              text        INDEX
protocol            text
discovery_method    text
discovery_timestamp timestamptz
first_seen          timestamptz
last_seen           timestamptz
last_modified       timestamptz
etag                text
content_hash        text        -- last observed representation
crawl_policy        jsonb
authorization_state text        INDEX  -- allowed|restricted|requires_authorization|…
rate_limit          jsonb
crawl_frequency     text
priority            real        INDEX
availability        real
failure_count       int
next_crawl_at       timestamptz INDEX
provenance          jsonb
status              text        INDEX  -- discovered|authorized|active|paused|blocked|retired
```

### acquisition
```
acquisition_id  text PK
source_id       text FK→source        INDEX
job_id          text FK→job
started_at      timestamptz
finished_at     timestamptz
transport_meta  jsonb                  -- status, etag, last_modified
outcome         text                   -- ok|unchanged|failed|blocked
object_id       text FK→raw_object NULL
provenance_event_id text FK→provenance_event
```

### job
```
job_id         text PK
stage          text     INDEX          -- discovery|acquisition|parsing|…
source_id      text FK→source NULL
state          text     INDEX          -- queued|assigned|fetching|…|completed|failed|…
priority       int
attempts       int
max_attempts   int
idempotency_key text    UNIQUE
payload        jsonb
enqueued_at    timestamptz
updated_at     timestamptz
```

### raw_object
```
object_id        text PK
content_hash     text UNIQUE           -- == storage address
source_id        text FK→source        INDEX
acquisition_id   text FK→acquisition
ingestion_id     text
timestamp        timestamptz           INDEX
format           text                  INDEX
declared_media_type text
size_bytes       bigint
storage_location text
storage_tier     text     INDEX        -- hot|warm|cold
integrity_status text     INDEX        -- verified|unverified|failed
compression      jsonb                 -- {codec, stored_bytes}
parent_object_id text FK→raw_object NULL -- archive children
in_archive_path  text NULL
provenance_event_id text FK→provenance_event
```

### document / document_version
```
document          (document_id PK, canonical_key text INDEX, current_version_id text)
document_version  (version_id PK, document_id FK INDEX, object_id FK→raw_object,
                   version_no int, valid_from timestamptz, valid_to timestamptz NULL,
                   structure_ref text, normalized_text_ref text, language jsonb,
                   normalization_version text, diff_from_prev jsonb NULL,
                   epistemic_status text, provenance_event_id text)
```

### metadata
```
metadata_id  text PK
object_id    text FK→raw_object INDEX
document_id  text FK→document NULL
fields       jsonb          -- [{key,value,epistemic,confidence,source_field,verification}]
integrity    jsonb          -- {hash, signed, signer}
anomalies    text[]         INDEX (GIN)
provenance_event_id text
```

### entity
```
entity_id    text PK
type         text INDEX     -- person|organization|location|concept|…
canonical_name text INDEX
aliases      text[]
domains      text[]         -- multi-domain
attributes   jsonb
valid_from   timestamptz
valid_to     timestamptz NULL
version      int
provenance_event_id text
```

### claim
```
claim_id     text PK
subject      text INDEX
predicate    text INDEX     -- controlled vocabulary
object       text
conditions   jsonb
source_id    text FK→source
source_version text
timestamp    timestamptz
evidence_type text
extraction_method text
confidence   real
status       text INDEX     -- supported|contradicted|qualified|superseded|unresolved|unknown
epistemic_status text
segment_ref  text           -- extracted_segment provenance
valid_from   timestamptz
valid_to     timestamptz NULL
version      int
provenance_event_id text
  INDEX (subject, predicate)  -- contradiction candidate lookup
```

### relationship (graph edge)
```
edge_id      text PK
from_node    text INDEX
type         text INDEX     -- is_a|part_of|requires|causes|contradicts|…
to_node      text INDEX
confidence   real
epistemic_status text
evidence     text[]
valid_from   timestamptz
valid_to     timestamptz NULL
version      int
provenance_event_id text
  INDEX (from_node, type), (to_node, type)
```

### domain / subdomain (ontology)
```
onto_node (node_id PK, level text, labels text[], aliases text[],
           status text INDEX -- active|candidate|deprecated,
           version int, provenance_event_id text)
onto_edge (edge_id PK, child_id FK, parent_id FK, kind text -- 'hierarchy',
           UNIQUE(child_id,parent_id))   -- DAG-lite; cycles forbidden
```

### dataset / repository / code_file
```
dataset     (dataset_id PK, object_id FK, format text, row_count bigint,
             columns jsonb, candidate_foreign_keys jsonb, schema_version text,
             epistemic_status text)
repository  (repo_id PK, source_id FK, vcs text, default_branch text,
             commit text, file_count int)
code_file   (code_file_id PK, repo_id FK INDEX, path text, language text,
             ast_ref text, imports text[], exports text[], commit text)
```

### knowledge_object
```
knowledge_object_id text PK
kind         text INDEX     -- concept|process|theory|method|…
labels       text[]
domains      text[]
claim_refs   text[]
edge_refs    text[]
epistemic_status text INDEX
version      int
provenance_event_id text
```

### pattern / pattern_version
```
pattern         (pattern_id PK, domain text INDEX, approval_state text INDEX,
                 current_version int)
pattern_version (pv_id PK, pattern_id FK INDEX, version int, context text,
                 mechanism text, function text, constraints text[], evidence text[],
                 confidence real, tests text[], falsifiers text[], failure_modes text[],
                 repair_patterns text[], compatible_patterns text[],
                 conflicting_patterns text[], transfer_constraints text[],
                 usage_history jsonb, failure_history jsonb, provenance_event_id text)
```

### provenance_event
```
provenance_event_id text PK
produced_type  text
produced_id    text INDEX
derived_from   jsonb          -- [{type,id}]
actor          text           -- service@version
at             timestamptz INDEX
using_parser   text
using_transformation text
pipeline_version text INDEX
confidence     real
inputs_hash    text INDEX      -- deterministic input fingerprint (idempotency)
epistemic_status text
```

### audit_event
```
audit_event_id text PK
actor          text INDEX      -- operator|service
action         text INDEX
target         text
before         jsonb
after          jsonb
at             timestamptz INDEX
signature      text            -- tamper-evident
```

### contradiction
```
contradiction_id text PK
claims           text[] INDEX
subject          text INDEX
predicate        text
dimensions_examined text[]
outcome          text INDEX     -- resolved|contextual|superseded|measurement|definition|unresolved|unknown
explanation      text
independent_sources jsonb
status           text
provenance_event_id text
```

### search_document (derived index doc — rebuildable)
```
search_id     text PK          -- mirrors source object id
type          text             -- document|claim|entity|code|dataset|pattern
text          text             -- indexed content
facets        jsonb            -- domain, source, date, format, language, confidence, evidence_quality
scores        jsonb            -- precomputed: recency, independence, provenance_quality
updated_at    timestamptz
```

**Conventions:** PKs are stable ULIDs; FKs enforced in SoR; `valid_from/valid_to` give
temporal validity; `version` monotonic; `content_hash`/`inputs_hash` drive idempotency;
GIN indexes for array/jsonb search; hot tables (`job`, `claim`, `relationship`) partitioned
by time/domain at scale.

---

## 72. API schemas (examples)

### Search — request/response
```
GET /v1/search?q=quantum+tunneling&domain=physics&from=2024-01-01&page_size=20&cursor=…

200 {
  "query": "quantum tunneling",
  "facets": { "domain": {"physics":120,"math":45}, "format": {"pdf":80,"html":85} },
  "results": [
    { "id":"doc_…", "type":"document", "title":"…",
      "scores": {"relevance":0.88,"evidence_quality":0.61,"source_quality":0.72,
                 "recency":0.95,"confidence":0.70,"independent_sources":4},
      "rank_score":0.83, "provenance_ref":"/v1/provenance/obj_…" }
  ],
  "next_cursor": "…", "api_version":"v1", "request_id":"req_…"
}
```

### Document retrieval
```
GET /v1/documents/{id}?version=latest
200 { "document_id":"doc_…","version_no":3,"language":{"code":"en","confidence":0.98},
      "structure":{…},"versions":[{"version_no":1,…},…],"provenance_ref":"…" }
```

### Source retrieval
```
GET /v1/sources/{id}
200 { "source_id":"src_…","source_type":"rss","domain":"example.org",
      "authorization_state":"allowed","availability":0.998,"status":"active" }
```

### Entity / Domain / Claim
```
GET /v1/entities/{id}         -> entity + mentions + relationships (bounded)
GET /v1/domains/{name}        -> ontology node + children + concepts
GET /v1/claims/{id}           -> claim + status + supporting/conflicting + evidence
GET /v1/claims/{id}/contradictions -> contradiction records (both sides)
```

### Graph traversal (bounded)
```
GET /v1/graph/traverse?node=concept:quantum_tunneling&depth=2&max_edges=200&types=requires,enables
200 { "root":"concept:…","nodes":[…],"edges":[…],"truncated":false }
409 QUERY_TOO_COMPLEX if budget exceeded
```

### Pattern / Version history / Provenance
```
GET /v1/patterns/{id}                 -> pattern + active version + provenance
GET /v1/versions?subject=…&from=&to=  -> temporal history + diffs
GET /v1/provenance/{object_id}        -> full lineage chain
```

### System health
```
GET /v1/system/status
200 { "coverage":{…},"queues":{…},"search":{"p95_ms":180},"crawler":{"active":true} }
```

### Error response (all endpoints)
```
4xx/5xx { "error": { "code":"…","message":"…","details":{…},
                     "request_id":"req_…","api_version":"v1" } }
```

---

## 73. Event schemas (examples)

All events use the common envelope (see [`docs/16-events-queues.md`](16-events-queues.md)).
Payloads:

```
source.discovered      { source_id, source_type, canonical_location, discovery_method, authorization_state }
source.updated         { source_id, changed_fields[], content_hash }
acquisition.started    { job_id, source_id, connector_type }
acquisition.completed  { job_id, source_id, object_id, outcome }  -- outcome: ok|unchanged
acquisition.failed     { job_id, source_id, error_class, retryable:bool }
document.parsed        { document_id, object_id, format }
document.normalized    { document_id, object_id, normalization_version, language }
document.deduplicated  { object_id, duplicate_group, level, similarity? }
entity.created         { entity_id, type, canonical_name, domains[] }
claim.created          { claim_id, subject, predicate, object, confidence, status }
relationship.created   { edge_id, from, type, to, confidence }
contradiction.detected { contradiction_id, claims[], subject, outcome }
index.updated          { search_id, type, op }             -- op: upsert|delete
pattern.created        { pattern_id, domain, approval_state }
pattern.updated        { pattern_id, version, approval_state }
discord.notification   { template_id, channel, window, metrics{…}, links[] }
system.failure         { component, severity, failure_category, message }
security.event         { kind, severity, source_ref, detail }
```

---

## 74. Observability schemas

Per-metric definition shape:

```
{ name, type, meaning, collection_frequency, alert_threshold, dashboard_location }
```

Examples:

| name | type | meaning | freq | alert threshold | dashboard |
|------|------|---------|------|-----------------|-----------|
| `crawl_rate` | gauge | fetches/sec | 15s | < 50% of baseline | Crawler |
| `source_availability` | gauge | rolling availability | 1m | < 0.95 | Crawler |
| `parser_errors_total` | counter | parse failures | 15s | rate > X/min | Processing |
| `queue_depth{stage}` | gauge | messages waiting | 15s | > cap | Queues |
| `dlq_depth{stage}` | gauge | dead-letter size | 1m | > 0 sustained | Queues |
| `index_lag_seconds` | gauge | index behind SoR | 15s | > 60s | Search |
| `search_latency_ms{q}` | histogram | query latency | 15s | p95 > 300ms | Search |
| `storage_bytes{tier}` | gauge | bytes per tier | 5m | growth anomaly | Storage |
| `dedup_savings_bytes` | gauge | bytes saved by dedup | 5m | — | Storage |
| `provenance_integrity_failures` | counter | broken lineage found | 1m | > 0 | Quality |
| `security_events_total{severity}` | counter | security events | 15s | any `high` | Security |
| `unresolved_contradictions` | gauge | open contradictions | 5m | trend up | Quality |

Every service exposes RED (Rate, Errors, Duration) + its domain metrics; all wired to
alerts (severity-tiered) and dashboards (§45/§58).
