# 32. Discord Integration · 33. Message Design · 34. Command Interface

**Principle.** Discord is a **distribution / notification / human-interface / operations**
layer. It is **NOT** the primary database. Internal events drive Discord; Discord never
owns knowledge state.

---

## 32. Discord gateway

**Purpose.** Translate internal events into aggregated Discord notifications and translate
Discord commands into API calls.

### 32.1 Event → notification

```
internal event (event bus)  e.g. knowledge.created
   └─▶ Discord Gateway (subscribes to a curated set of events)
          └─▶ aggregation window (batch + summarize; §33)
                 └─▶ channel router (map event class → channel)
                        └─▶ Discord API (rate-limit aware)
```

### 32.2 Example server architecture

Categories (channel groups): **knowledge · sources · domains · patterns · system ·
operations · alerts**.

Example channels:

```
#physics  #mathematics  #computer-science      (per-domain knowledge digests)
#new-sources  #new-datasets  #new-repositories (source events)
#processing-status  #crawler-status            (operations)
#errors  #contradictions  #security-alerts     (alerts)
#system-health                                 (system)
```

Channel routing is **config-driven** (event class + domain → channel), so new channels/
domains don't require code changes.

### 32.3 Gateway properties

- **Rate-limit aware:** respects Discord's rate limits with a token bucket + queue; never
  floods.
- **Backpressure:** if Discord is slow/down, notifications queue durably and are
  delivered later (or dropped past a TTL with a summary), **without** affecting the core
  pipeline.
- **Stateless-ish:** the gateway keeps only delivery state (what's been sent), which is
  reconstructable; knowledge is never stored only in Discord.

---

## 33. Discord message design

**Do not send every raw document as a separate message.** Aggregate events over a window.

### 33.1 Aggregation example

Instead of 1,000 messages:

```
📚 Physics ingest — last 15 min
• 1,000 sources processed
• 245 new knowledge objects
• 81 new entities
• 17 new relationships
• 4 candidate patterns (pending review)
[ Open in Immanuel ▸ ]   [ View sources ▸ ]   [ Review patterns ▸ ]
```

Buttons/links deep-link to the frontend rather than dumping content into Discord.

### 33.2 Message templates (config-driven)

```json
{
  "template_id": "domain_digest",
  "trigger_events": ["knowledge.created", "entity.created", "relationship.created", "pattern.created"],
  "window": "PT15M",
  "group_by": "domain",
  "fields": [
    { "label": "sources processed", "metric": "sources_processed" },
    { "label": "new knowledge objects", "metric": "knowledge_created" },
    { "label": "new entities", "metric": "entities_created" },
    { "label": "new relationships", "metric": "relationships_created" },
    { "label": "candidate patterns", "metric": "patterns_candidate" }
  ],
  "links": [{ "label": "Open in Immanuel", "url_template": "https://frontend/domain/{domain}" }]
}
```

Other templates: `crawler_status`, `error_digest`, `contradiction_alert`,
`security_alert`, `system_health`. Alerts (errors/security/contradictions) may bypass the
aggregation window for **severity ≥ threshold**.

---

## 34. Discord command interface

**Purpose.** Let operators/users query Immanuel from Discord; commands map to API calls.

### 34.1 Commands & flows

| Command | Behavior | API flow |
|---------|----------|----------|
| `/search <q>` | Search summary + link | `GET /v1/search?q=` → top results embed |
| `/source <id\|domain>` | Source status/health | `GET /v1/sources/{id}` |
| `/document <id>` | Document summary + link | `GET /v1/documents/{id}` |
| `/entity <name>` | Entity page summary | `GET /v1/entities?name=` |
| `/domain <name>` | Domain overview | `GET /v1/domains/{name}` |
| `/graph <node>` | Bounded neighborhood image/summary | `GET /v1/graph/traverse?node=&depth=1` |
| `/pattern <id>` | Pattern + provenance | `GET /v1/patterns/{id}` |
| `/status` | System status snapshot | `GET /v1/system/status` |
| `/crawler` | Crawler health/queue depth | admin API (restricted) |
| `/contradictions [subject]` | Open contradictions | `GET /v1/claims/contradictions` |
| `/health` | Health checks summary | admin API (restricted) |

### 34.2 Command security

- Commands are authorized by Discord role → mapped to API scopes; operator-only commands
  (`/crawler`, `/health`) require an operator role and hit the **admin** API.
- All command invocations are audit-logged.
- Command inputs are validated and complexity-bounded exactly like API inputs (§62/§63).

### 34.3 Failure modes, observability, recovery

- **Discord down:** notifications queue; commands fail gracefully; **core unaffected**.
- **Rate limits:** gateway backs off; digests coalesce further.
- **Observability:** `discord_publish_latency_ms`, `discord_rate_limited_total`,
  `discord_queue_depth`, `discord_delivery_failures_total`.
- **Recovery:** delivery state is reconstructable from the event log; missed digests can be
  regenerated for a window; no knowledge is lost because Discord is not a store.
