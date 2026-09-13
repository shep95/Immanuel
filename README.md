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
- **Timeline collection:** with `ENABLE_WAYBACK=true`, each seed is expanded with
  historical captures from the Internet Archive (from when a site was founded up to
  today); forward-in-time ("future days") coverage happens as the crawler keeps running.
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
| `/setup_admin_channel [channel]` | admin | Create/designate the admin log channel for join/leave logs |
| `/create_channel <name> [category]` | admin | Create a new text channel |
| `/rename_channel <channel> <new_name>` | admin | Rename a channel |
| `/set_channel_perms <channel> <role> <can_view>` | admin | Allow/deny a role from viewing a channel |

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
`GET /v1/search` · `GET /v1/items/{id}` · `GET /v1/export`.

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
/addsource https://example.com/news     → give it something to crawl
/start                        → the algorithm begins collecting 24/7
/updates                      → watch totals climb, per category
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
├── README.md              # this file — overview + spec index
├── docs/                  # the full engineering specification
└── LICENSE
```

## License

See [`LICENSE`](LICENSE).
