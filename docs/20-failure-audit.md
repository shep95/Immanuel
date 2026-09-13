# 40. Failure Engine · 41. Self-Audit · 45. Root-Cause Engine · 49. Contradiction/Tradeoff Engine · 50. Quality Engine

> (These map to the required output sections: 40 Failure engine, 41 Self audit; and to the
> detailed-prompt sections 43 Failure engine, 44 Self audit, 45 Root-cause, 49 Tradeoffs,
> 50 Quality. Grouped here as the reliability/quality core.)

## Failure engine (universal failure model)

**Purpose.** A shared taxonomy and method for reasoning about *any* failure — software,
data, workflow, crawler, classification, search, storage, API, Discord.

### Failure categories

intent · requirement · logic · causal · state · flow · data · information · assumption ·
temporal · resource · performance · privacy · security · human-factor · interaction ·
evidence · uncertainty · metadata · integration · infrastructure · operational.

### Per-component failure record (every major component has one)

```json
{
  "component": "normalization-svc",
  "expected_behavior": "UTF-8 canonical output, deterministic per version",
  "observed_behavior": "non-deterministic whitespace on RTL text",
  "difference": "ordering of combining marks varies",
  "possible_causes": ["locale-dependent sort", "unstable normalization step"],
  "discriminating_test": "run same input under two locales; compare bytes",
  "root_cause": "locale-dependent collation in step 4",
  "repair": "pin ICU normalization; add golden test",
  "verification": "byte-identical output across locales; regression test green"
}
```

## Self-audit

The system **continuously audits itself**. Audited dimensions:

coverage · accuracy · duplicate rate · parser failure · source failure · latency ·
storage growth · index health · queue health · data quality · metadata quality ·
provenance integrity · security events · contradictions · classification errors ·
taxonomy problems.

- Each dimension has metrics (§44/§74) + thresholds + alerts + a dashboard tile (§45/§58).
- Self-audit runs as scheduled jobs + streaming checks; anomalies open **findings** that
  route to the root-cause engine and, if severe, to alerts/Discord.
- **Provenance-integrity audit** is special: it verifies every derived object has an
  intact lineage chain; any break is a high-severity finding.

## Root-cause engine

**When something fails, do not immediately patch the symptom.** Apply:

```
expected model ─▶ observed model ─▶ difference ─▶ possible causes ─▶
   discriminating test ─▶ root cause ─▶ model repair ─▶ implementation repair ─▶ verification
```

Applies uniformly to: software · data · workflow · crawler · classification · search ·
storage · API · Discord failures. Every root-cause investigation is recorded (linked to the
failure record + the fix + the verifying test), building an operational knowledge base.

## Contradiction & tradeoff engine (design-level tensions)

Immanuel explicitly tracks architectural tradeoffs rather than pretending one side is
always right:

speed vs accuracy · efficiency vs redundancy · simplicity vs flexibility · centralization
vs decentralization · privacy vs observability · exploration vs exploitation · stability
vs adaptability · optimization vs robustness · specialization vs generalization ·
short-term vs long-term · local vs global optimum.

For each, the spec states **the conditions under which the balance shifts** (e.g.,
"favor redundancy over efficiency for systems-of-record; favor efficiency for rebuildable
derived stores"). These conditions are documented per-subsystem and revisited in audits.

## Quality engine

Scores system **outputs** along many dimensions, kept **separate** (never one blended
"goodness"):

correctness · evidence · calibration · utility · efficiency · robustness ·
generalizability · transferability · simplicity · explainability · novelty ·
reversibility · failure tolerance · security · privacy · provenance quality.

And — as an invariant echoed from ranking (§29) — the quality engine keeps **relevance
score · confidence · evidence quality · source quality** distinct. Quality scores feed
self-audit and pattern evaluation (§42/§46) but never silently promote a hypothesis to a
fact.

### Failure modes of the reliability core itself

- Audit blind spots → periodic "audit the auditor" reviews; coverage metrics on the audits.
- Alert fatigue → severity tiers + aggregation (Discord digests, §33).
- Metric gaming → separated scores + provenance make single-number gaming ineffective.
