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
