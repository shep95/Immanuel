# Immanuel

**Universal Data Acquisition & Knowledge Infrastructure**

Immanuel is a deterministic, non-AI system that continuously **discovers, acquires,
processes, normalizes, compresses, deduplicates, organizes, indexes, versions,
connects, and exposes** the maximum *lawful and technically accessible* amount of
public internet information — websites, public APIs, public datasets, repositories,
documents, archives, source code, structured data, media metadata, and feeds.

> Immanuel is **not** an AI model. Its core — acquisition, parsing, organization,
> compression, indexing, provenance, scheduling, deduplication, versioning, storage,
> distribution, and retrieval — is built on deterministic algorithms, parsers,
> databases, data structures, statistical methods, graph algorithms, compression
> systems, crawlers, queues, schedulers, rules, and schemas. AI/ML is identified only
> as an **optional future component**, never a hidden dependency of the core.
>
> It runs **24/7** as an ecosystem of independent, horizontally-scalable services.

## Engineering target

> Maximize lawful and technically accessible information coverage while preserving
> source authorization, rate limits, provenance, integrity, privacy, and source
> restrictions.

Immanuel **does not** bypass authentication, access controls, paywalls, encryption,
`robots` restrictions, private systems, or any other access boundary. See
[`docs/39-access-policy.md`](docs/39-access-policy.md).

---

# 🚀 Running Immanuel (the working bot + algorithm)

This repo contains **both** the full engineering spec (`docs/`) **and** a working
implementation (the `immanuel/` Python package): a 24/7 crawler ("the algorithm"), a
5-category classifier, a Discord control bot, and an HTTP API with per-user API keys.
It's designed to be hosted on **Railway** as a single service.

## What it does

- **The algorithm** crawls public web sources 24/7 (politely, respecting `robots.txt`),
  extracts content from **any media type** (HTML, feeds, JSON, text, images/audio/video
  metadata), deduplicates it, and stores it with provenance.
- **Auto source discovery (zero-config):** with `AUTO_DISCOVER=on` (default) it starts from
  a built-in set of link-rich public hubs and live feeds and **finds its own domains** — you
  don't have to add anything. `/addsource` and `SEED_URLS` just add extras. Optionally
  `ENABLE_CT_DISCOVERY=true` turns on a **Certificate-Transparency domain firehose** that
  streams newly-seen domains from across the web, in batches.
- **Crawler-agent swarm with 3-hop fan-out (default):** in `swarm` mode Immanuel spawns a
  **brand-new, non-AI crawler-agent for every page/link it discovers** — each agent fetches
  its page, then its discovered links spawn more agents. Fan-out is bounded by a **hop
  depth** (`MAX_HOPS`, default 3): a domain is hop 0, its links hop 1, and so on — so it
  batches the domains it finds and hops across the domains connected to those pages, up to 3
  levels. Also bounded by `MAX_AGENTS`, a bounded frontier, and per-domain politeness so it
  goes fast without exhausting the machine or hammering any host. (`CRAWLER_MODE=cycle`
  switches to a fixed worker pool if you prefer steadier behavior.)
- **Timestamps + versioning:** every capture is timestamped. When a page changes between
  crawls, Immanuel records a **new version** and shows **what was added/removed and when**
  (see `/recent_updates`, the `immanuel-updates` channel, and `GET /v1/versions`).
- **Non-index / non-SEO + subdomains:** it doesn't rely on search engines or sitemaps —
  it follows links directly and (with `ENABLE_SUBDOMAIN_PROBE=true`) probes common
  subdomains (`blog.`, `api.`, `docs.`, …) and paths to reach hosts/pages that aren't
  linked or indexed anywhere.
- **Timeline collection:** with `ENABLE_WAYBACK=true`, each seed is expanded with
  historical captures from the Internet Archive (from when a site was founded up to
  today); forward-in-time ("future days") coverage happens as the crawler keeps running.
- **Hosts data on your Discord server:** new items are posted into per-category channels
  and page updates into `#immanuel-updates`, all under a **📚 Immanuel Data** category the
  bot creates — which is why it needs channel/category permissions.
- **The classifier** files every item into one of five buckets:
  **public-facts · public-rumors · private-facts · private-rumors · conspiracies**.
  > ⚠️ The "private" labels describe the *subject matter of publicly-posted content*.
  > Immanuel never accesses private systems or bypasses access controls — see
  > [`docs/39-access-policy.md`](docs/39-access-policy.md).
- **The Discord bot** is your control panel: start/pause/stop, see updates, download all
  data, manage channels, generate API keys, and it **logs every member join/leave** to an
  admin channel.
- **The API** lets you (or your users' LLMs/platforms) query the knowledge base with an
  API key generated from Discord.

### Deep acquisition (scrape, don't just link)

With `DEEP_EXTRACT=true` (default) every page is **fully scraped**, not merely linked:

- **Text + full metadata + code** — all `<meta>` tags, OpenGraph/Twitter cards, JSON-LD,
  `lang`, and code assets (script/stylesheet/inline JSON-LD) are captured per item.
- **Exposed API keys / secrets** (`SCAN_SECRETS=true`) — a deterministic (regex + entropy)
  scanner flags secrets left in public page source. Findings are **masked** (raw value is
  never stored — only a sha256 fingerprint + preview) and routed to a **private admin-only**
  `#asherin-api-keys` channel (`/setup_secrets_channel`). Read them via `GET /v1/secrets`
  with an **admin** key (`/adminkey`).
- **Media download & import** (`DOWNLOAD_MEDIA=true`) — images/audio/video are downloaded to
  a content-addressed store, deduped by hash, with open image metadata (dimensions + EXIF/GPS
  when `Pillow` is installed).
- **YouTube → transcripts + thumbnails** (`ENABLE_YOUTUBE=true`) — YouTube links are converted
  to **transcripts** (needs the optional `youtube-transcript-api`) and their **thumbnails** are
  imported.
- **Intel data-report** (`BUILD_INTEL_REPORT=true`) — per page, Immanuel compiles a report of
  the open metadata, the link/media graph, and any secrets found — the raw material for a
  domain-wide **10-way hop** (`MAX_HOPS`) across every connected page and data source.
- **Organize by company / topic** (`ORGANIZE_BY=company|topic|epistemic`) — each data topic
  (or company) gets its **own channel/category**, created on demand up to `MAX_DYNAMIC_CHANNELS`.
- **Global, every-country coverage** — the bootstrap seed set spans multilingual Wikipedias,
  regional news, and international government/open-data portals so it isn't US/big-corp only.
- **Incremental / no re-collect** — a persistent HTTP ledger stores each page's ETag /
  Last-Modified. If the algorithm is turned off and back on, conditional GETs mean a page is
  **only re-collected when it actually changed** (HTTP 304 = skip).

### asherin.eng — the search engine

`/setup_asherin_eng` creates `#asherin-eng`; `/search <query>` (with optional `category` /
`company` / `topic` filters) queries everything collected — a real working-workflow search
engine over your own corpus. Same data is available at `GET /v1/search`.

### Pattern Forge — the second, non-AI algorithm (24/7)

A separate **deterministic** engine runs alongside the crawler. It does **not** pile up facts;
it learns **patterns**: `experience → outcome → cause → abstract mechanism → formalize →
test → scope → store → retrieve → adapt`. Each pattern is a Universal Pattern Object
(identity, domain, trigger, mechanism, invariants, evidence, confidence, failure modes,
tests, scope, lifecycle…) and moves through a lifecycle
(`candidate → testing → validated → active → deprecated → retired`) so untested strategies
stay hypotheses. See `/patterns`, `GET /v1/patterns`, and **`/skills-download`** to export
all learned pattern skills as a `.txt` file. The framework "brains" this implements live in
[`docs/patternforge/`](docs/patternforge/).

### GitHub tool scout — the third, non-AI algorithm (24/7)

A deterministic scout (`ENABLE_GITHUB_SCOUT=true`) continuously scans **public GitHub**
for real **software / algorithms** in five families — **osint · cyber-security · hacking ·
surveillance · red-team**. It searches the public GitHub API, classifies each repo purely by
keyword/topic signals + the repo's own metadata (no AI), keeps only actual tools (not
docs/awesome-lists), and walks pages across passes so it reaches deep/forgotten repos over
time. Each new find is dropped into a **private channel only the server owner and the bot can
see** (`#asherin-github-tools`, created by `/setup_github_channel`) with:

- **link to GitHub**
- **software name**
- **software description**
- **how it's useful** (why it matched + language/stars)

Keyless by default; a `GITHUB_TOKEN` (if present in the environment) is used only to raise
the rate limit. Browse finds via `/github_tools [category]` or `GET /v1/github/tools`. The
raw code is never downloaded — only public repo metadata.

## Discord commands

| Command | Who | What it does |
|---------|-----|--------------|
| `/start` | admin | Start / resume the 24/7 collection engine |
| `/pause` | admin | Pause collection (keeps state) |
| `/stop` | admin | Stop collection |
| `/updates` | anyone | Live stats: engine state, totals, per-category counts |
| `/download` | admin | Export **all** collected data as a JSON file (or a sample + API link if too big) |
| `/apikey [name]` | anyone | Generate a personal API key (shown once) to connect a platform/LLM |
| `/addsource <url>` | admin | Add a public URL for the crawler to collect |
| `/sources` | anyone | List recent sources |
| `/categories` | anyone | Show the 5 categories and current counts |
| `/recent_updates` | anyone | Show recent page updates (what changed + timestamps) |
| `/setup_data_channels` | admin | Create the 📚 Immanuel Data category + channels that host the data |
| `/setup_admin_channel [channel]` | admin | Create/designate the admin log channel for join/leave logs |
| `/create_channel <name> [category]` | admin | Create a new text channel |
| `/rename_channel <channel> <new_name>` | admin | Rename a channel |
| `/set_channel_perms <channel> <role> <can_view>` | admin | Allow/deny a role from viewing a channel |
| `/search <query> [category] [company] [topic]` | anyone | **asherin.eng** — query everything collected, like a working search engine |
| `/setup_asherin_eng` | admin | Create the `#asherin-eng` search channel |
| `/patterns` | anyone | Show the Pattern Forge library (learned patterns + lifecycle) |
| `/skills-download [only_validated]` | anyone | Download all learned pattern skills as a `.txt` file |
| `/intel` | anyone | Show the most recent intel data-reports |
| `/setup_secrets_channel` | admin | Create the **private** `#asherin-api-keys` channel for exposed-secret alerts |
| `/adminkey` | admin | Generate an **admin** API key (unlocks the exposed-secrets endpoint) |
| `/setup_github_channel` | admin | Create the **private owner-only** `#asherin-github-tools` channel |
| `/github_tools [category]` | anyone | Show recently discovered useful GitHub tools |

"admin" = a Discord user with the **Administrator** permission, or a user ID listed in
`MASTER_ADMIN_IDS`.

## HTTP API (for LLM / platform integration)

Authenticate with the key from `/apikey` (header `X-API-Key:` or `Authorization: Bearer`):

```bash
# search
curl -H "X-API-Key: imk_xxx" "https://<your-app>.up.railway.app/v1/search?q=climate&category=public_fact"
# full export
curl -H "X-API-Key: imk_xxx" "https://<your-app>.up.railway.app/v1/export"
# interactive docs
open https://<your-app>.up.railway.app/docs
```

Endpoints: `GET /health` (public) · `GET /v1/status` · `GET /v1/categories` ·
`GET /v1/search` (now also filters `&company=` and `&topic=`) · `GET /v1/items/{id}` ·
`GET /v1/versions?url=…` (page history + timestamps) · `GET /v1/updates` (recent
changes) · `GET /v1/export`.

Deep-acquisition + Pattern Forge endpoints: `GET /v1/companies` · `GET /v1/topics` ·
`GET /v1/intel` (recent reports) · `GET /v1/intel/report?url=…` · `GET /v1/patterns`
(learned patterns) · `GET /v1/patterns/export` (skills as text) ·
`GET /v1/secrets` (**admin key required** — masked exposed-secret findings) ·
`GET /v1/github/tools?category=…` (discovered osint/cyber/hacking/surveillance/red-team tools).

## How many crawler-agents do I need?

Agents/workers are **async I/O tasks**, so one Railway container runs many cheaply.
Throughput is bounded by **per-domain politeness** (`CRAWL_DELAY_SECONDS`), not by CPU —
so the way to go faster is more *distinct domains*, not more agents hitting one host.
(One agent per page still means same-domain agents queue politely behind the per-host
delay; different domains run fully in parallel.)

Rough sizing (with `CRAWL_DELAY_SECONDS=2`, i.e. ≤0.5 req/s per host):

| Goal | `MAX_AGENTS` (swarm) / `NUM_CRAWLERS` (cycle) | Notes |
|------|-----------------------------------------------|-------|
| Light / a few dozen sites | 50 / 8 | comfortable on 1 small container |
| Busy / hundreds of domains | 200 / 16 | good balance |
| Heavy / thousands of domains | 500 / 32 | 1 larger container, or scale out |
| Very large | above × N containers | run multiple Railway replicas sharing the DB (Postgres — a roadmap item); one politeness budget per host |

Formula: sustainable pages/sec ≈ `min(concurrent_agents, distinct_domains) / CRAWL_DELAY_SECONDS`.
With 200 agents across ≥200 domains at 2s delay ≈ **100 pages/sec ≈ 8.6M pages/day**.
The swarm auto-scales agents up to `MAX_AGENTS` as it discovers pages; you don't tune
per-cycle batch sizes in swarm mode.

## Can it crawl "every domain in the world"?

Honestly: **not from one container.** The public web is hundreds of millions of live
domains and tens of billions of pages — that's Common-Crawl / search-engine territory
(large clusters, petabytes of storage, months of crawling). Immanuel gives you the right
**mechanism** for it — auto domain discovery (built-in firehose + optional CT-log stream),
one crawler-agent per page, and bounded N-hop fan-out — but a single Railway box + SQLite
will realistically track **thousands to low-millions of pages**, not the entire internet.

To actually push toward web-scale you need the distributed setup from the design spec:
- **Postgres** instead of SQLite (so many replicas share one dataset + one politeness
  budget per host) — this is the current top roadmap item.
- **Multiple Railway replicas / workers** all pulling from the shared frontier.
- Object storage for raw content and a real search index.

Turn `ENABLE_CT_DISCOVERY=on` and it *will* discover domains far faster than it can crawl
them (they queue as sources) — so treat `MAX_HOPS`, `MAX_AGENTS`, and your infra as the
real throttle. Want me to wire the Postgres + multi-replica backend? Say the word.

## Setup — Step by step

### 1. Create the Discord bot
1. Go to <https://discord.com/developers/applications> → **New Application** → name it *Immanuel*.
2. **Bot** tab → **Add Bot** → **Reset Token** → copy the token (this is `DISCORD_TOKEN`).
3. Under **Privileged Gateway Intents**, enable **SERVER MEMBERS INTENT** (needed for
   join/leave logging).
4. **OAuth2 → URL Generator**: scopes `bot` + `applications.commands`; bot permissions:
   **Manage Channels**, **Manage Roles**, **Send Messages**, **Read Message History**,
   **Attach Files**, **View Channels**. Open the generated URL and invite the bot to your server.
5. (Recommended) Copy your **server (guild) ID** (enable Developer Mode → right-click the
   server → Copy ID) → this is `DISCORD_GUILD_ID` (makes slash commands appear instantly).

### 2. Deploy on Railway
1. Push this repo to GitHub (already at <https://github.com/shep95/Immanuel>).
2. On <https://railway.app> → **New Project → Deploy from GitHub repo** → pick `shep95/Immanuel`.
   Railway auto-detects the `Dockerfile`.
3. **Variables** (Settings → Variables) — set at minimum:
   - `DISCORD_TOKEN` = your bot token
   - `DISCORD_GUILD_ID` = your server ID (optional but recommended)
   - `MASTER_ADMIN_IDS` = your Discord user ID (optional; otherwise Administrators only)
   - `PUBLIC_BASE_URL` = your Railway public URL (e.g. `https://immanuel-production.up.railway.app`)
   - Optional crawler/timeline tuning — see [`.env.example`](.env.example)
     (`SEED_URLS`, `ENABLE_WAYBACK`, `AUTOSTART_CRAWLER`, etc.)
4. **Add a Volume** (Settings → Volumes) mounted at `/app/data` so the SQLite DB persists
   across deploys. (The Dockerfile already points `DATABASE_PATH=/app/data/immanuel.db`.)
5. Railway sets `PORT` automatically; the app binds the API to it (also the healthcheck at
   `/health`). Deploy — the bot logs in and the API comes up in one process.

### 3. First run in Discord
```
/setup_admin_channel          → creates #immanuel-admin-log (join/leave logs land here)
/setup_data_channels          → creates 📚 Immanuel Data + per-category channels (data hosted here)
/addsource https://example.com/news     → give it something to crawl
/start                        → the algorithm begins collecting 24/7 (multiple workers)
/updates                      → watch totals climb, per category, versions & updates
/recent_updates               → see which pages changed, what changed, and when
/apikey myapp                 → get an API key to plug into your app/LLM
/download                     → pull everything collected as a file
```

## Run locally (optional)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # fill in DISCORD_TOKEN (or leave blank for API-only)
python -m immanuel.main         # API on :8000 (+ bot if token set)
```

Run the tests / end-to-end smoke check:

```bash
pip install -r requirements-dev.txt
python -m pytest -q              # 36 unit tests
python scripts/smoke.py          # crawl→classify→store→API, no token needed
```

---

## Design philosophy

- Source first · Provenance first · Data preservation
- Deterministic processing where practical
- Modular architecture · Horizontal scalability · Fault isolation · Idempotent processing
- Version everything important
- **Separate** raw from derived · evidence from inference · relevance from truth · source count from independent evidence
- Tree **plus** graph organization
- Security, privacy, observability, and recoverability throughout

## The epistemic separation (core invariant)

Immanuel never silently converts one category of data into another. The pipeline keeps
these strictly distinct at all times:

```
raw data → normalized data → derived data → metadata → claims →
knowledge objects → relationships → patterns → inferences → hypotheses → unknowns
```

with each object tagged by epistemic status:

```
observation · interpretation · hypothesis · inference · estimate · fact · assumption · unknown
```

A novel or untested derived pattern **remains a hypothesis** — it does not
automatically become established knowledge.

## The pipeline

```
source discovery → source registration → authorization evaluation → crawl scheduling →
acquisition → quarantine → format detection → parsing → extraction → normalization →
deduplication → compression → metadata extraction → segmentation → entity extraction →
claim extraction → relationship extraction → domain classification → subdomain classification →
knowledge organization → graph construction → provenance construction → contradiction detection →
temporal versioning → quality analysis → indexing → search → api exposure →
discord distribution → frontend consumption → monitoring → feedback → repair → continuous improvement
```

Lineage is preserved end-to-end: **every derived object is traceable back to its
originating source and acquisition event.**

## Specification index

The specification follows the required 55-section structure. It is split across the
documents below (section numbers in brackets map to the required output structure).

| Doc | Covers (required sections) |
|-----|----------------------------|
| [`docs/00-executive-architecture.md`](docs/00-executive-architecture.md) | 1 Executive architecture · 5 Complete architecture (overview) |
| [`docs/01-objectives-boundaries.md`](docs/01-objectives-boundaries.md) | 2 Objectives · 3 Non-objectives · 4 System boundaries |
| [`docs/02-source-discovery.md`](docs/02-source-discovery.md) | 6 Source discovery |
| [`docs/03-acquisition-connectors.md`](docs/03-acquisition-connectors.md) | 7 Acquisition · 8 Connectors |
| [`docs/04-ingestion-archives.md`](docs/04-ingestion-archives.md) | 9 File ingestion · 10 Archive processing |
| [`docs/05-raw-normalization.md`](docs/05-raw-normalization.md) | 11 Raw storage · 12 Normalization |
| [`docs/06-dedup-compression.md`](docs/06-dedup-compression.md) | 13 Deduplication · 14 Compression |
| [`docs/07-metadata.md`](docs/07-metadata.md) | 15 Metadata |
| [`docs/08-processing.md`](docs/08-processing.md) | 16 Document · 17 Code · 18 Dataset · 19 Media processing |
| [`docs/09-ontology-classification.md`](docs/09-ontology-classification.md) | 20 Ontology · 21 Domain classification · 22 Dynamic taxonomy |
| [`docs/10-knowledge-graph-provenance.md`](docs/10-knowledge-graph-provenance.md) | 23 Knowledge graph · 24 Provenance · 25 Claim system |
| [`docs/11-contradiction-temporal.md`](docs/11-contradiction-temporal.md) | 26 Contradiction engine · 27 Temporal system |
| [`docs/12-search-ranking.md`](docs/12-search-ranking.md) | 28 Search engine · 29 Ranking |
| [`docs/13-api.md`](docs/13-api.md) | 30 API |
| [`docs/14-frontend.md`](docs/14-frontend.md) | 31 Frontend |
| [`docs/15-discord.md`](docs/15-discord.md) | 32 Discord |
| [`docs/16-events-queues.md`](docs/16-events-queues.md) | 33 Event architecture · 34 Queues |
| [`docs/17-storage.md`](docs/17-storage.md) | 35 Storage |
| [`docs/18-scalability.md`](docs/18-scalability.md) | 36 Scalability |
| [`docs/19-security-privacy-policy.md`](docs/19-security-privacy-policy.md) | 37 Security · 38 Privacy · 39 Access policy |
| [`docs/20-failure-audit.md`](docs/20-failure-audit.md) | 40 Failure engine · 41 Self audit |
| [`docs/21-pattern-layer.md`](docs/21-pattern-layer.md) | 42 Pattern layer · 43 Cross-domain transfer |
| [`docs/22-observability-admin.md`](docs/22-observability-admin.md) | 44 Observability · 45 Administration |
| [`docs/23-disaster-recovery.md`](docs/23-disaster-recovery.md) | 46 Disaster recovery |
| [`docs/24-testing-benchmarking.md`](docs/24-testing-benchmarking.md) | 47 Testing · 48 Benchmarking |
| [`docs/25-cost-model.md`](docs/25-cost-model.md) | 49 Cost model |
| [`docs/26-technology-comparison.md`](docs/26-technology-comparison.md) | 50 Technology comparison |
| [`docs/27-mvp-roadmap.md`](docs/27-mvp-roadmap.md) | 51 MVP · 52 Development roadmap · 53 Future evolution |
| [`docs/28-schemas.md`](docs/28-schemas.md) | Database, API, event & observability schemas |
| [`docs/30-foreseeable-problems.md`](docs/30-foreseeable-problems.md) | 54 Top 50 foreseeable problems & solutions |
| [`docs/31-final-architecture.md`](docs/31-final-architecture.md) | 55 Final architecture diagram · Architectural audit |

## Status legend

Throughout the spec, claims about the design are tagged:

- **[KNOWN]** — established, well-understood engineering.
- **[ASSUMED]** — depends on an assumption stated inline.
- **[PROPOSED]** — a design decision open to revision.
- **[EXPERIMENTAL]** — unproven; requires validation before relied upon.
- **[UNKNOWN]** — an explicit open question.

No untested design is claimed as guaranteed to work.

## Repository layout

```
immanuel/
├── immanuel/
│   ├── crawler/           # fetcher, extract (deep), secrets scanner, pipeline, swarm
│   ├── media/             # media downloader + YouTube transcript/thumbnail import
│   ├── patternforge/      # non-AI Pattern Forge: ontology, forge (miners), skills, runner
│   ├── githubscout/       # non-AI GitHub tool scout: classify (families) + scout (24/7)
│   ├── discordbot/        # bot commands + publisher (dynamic channels, secrets channel)
│   ├── api/               # FastAPI app (search, intel, patterns, companies, secrets)
│   ├── intel.py           # intel data-report builder
│   ├── organize.py        # deterministic company/topic classifier
│   ├── engine.py · db.py · config.py · main.py
├── docs/
│   ├── patternforge/      # the Pattern Forge "brains" (framework this implements)
│   └── …                  # the full engineering specification
├── requirements.txt · requirements-optional.txt   # optional = Pillow, youtube-transcript-api
├── README.md              # this file — overview + spec index
└── LICENSE
```

## License

See [`LICENSE`](LICENSE).
