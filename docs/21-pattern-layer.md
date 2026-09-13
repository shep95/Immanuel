# 42. Pattern Layer · 43. Cross-Domain Pattern Transfer

**Position.** The pattern layer sits **above** the data infrastructure as a **separate,
governed layer**. It observes the knowledge base and proposes patterns — but **never
blindly learns**, and a novel untested pattern **remains a hypothesis**.

> This layer is deterministic/statistical in its governance. Any ML used for *proposing*
> candidate patterns is optional and downstream of the same test/quarantine gates — it can
> never inject an unvetted pattern into established knowledge.

## 42. Pattern layer

### 42.1 Capabilities & lifecycle

```
discover → create → evaluate → retain/quarantine/reject → retrieve → compose → adapt → evolve
```

### 42.2 Governed evaluation pipeline (never blind)

```
observation → candidate pattern → classification → test → comparison →
   contradiction check → confidence estimation → scope determination →
   retain (approved) | quarantine (needs more evidence) | reject (failed)
```

- **Candidate patterns start as hypotheses** (epistemic status `hypothesis`) and are
  quarantined until they pass tests. They cannot be used as established knowledge while
  quarantined.
- **Tests** are explicit (falsifiers + failure modes recorded); a pattern that fails its
  discriminating test is rejected or refined, not silently kept.
- **Contradiction check** runs candidates against existing patterns/claims (§26).
- **Confidence** and **scope** are estimated and stored; a pattern only applies within its
  determined scope/constraints.

### 42.3 Pattern provenance (required fields — §47 of the prompt)

```json
{
  "pattern_id": "pat_01J9...",
  "domain": "control",
  "context": "feedback-regulated systems",
  "mechanism": "negative feedback dampens deviation",
  "function": "stabilization",
  "constraints": ["measurable output", "actuator with sufficient authority"],
  "evidence": ["claim_...", "dataset_...", "doc_..."],
  "confidence": 0.74,
  "source": ["src_...", "src_..."],
  "provenance": { "creation_event": "prov_...", "derived_from": ["obs_..."] },
  "tests": ["test_stability_margin"],
  "falsifiers": ["oscillation under bounded gain"],
  "failure_modes": ["actuator saturation", "delay-induced instability"],
  "repair_patterns": ["add anti-windup", "phase-lead compensation"],
  "compatible_patterns": ["pat_observer"],
  "conflicting_patterns": ["pat_open_loop_only"],
  "transfer_constraints": ["requires invariant: measurable error signal"],
  "version": 2,
  "approval_state": "approved|quarantined|rejected|candidate",
  "usage_history": [{ "at": "...", "context": "...", "outcome": "..." }],
  "failure_history": [{ "at": "...", "mode": "...", "resolution": "..." }]
}
```

The system can answer, for any pattern: **where it originated · why it was retained · what
evidence supported it · what tests were performed · what failed · what modified it · which
version is active · when it should be reconsidered** — all from the record above + its
provenance events.

### 42.4 Governance against pattern-library poisoning

- New patterns require passing tests + independent evidence (via §27 independence) before
  `approved`.
- A pattern that "appears successful temporarily" is caught by ongoing `usage_history` /
  `failure_history` tracking and re-evaluation triggers (reconsider-when conditions).
- The pattern library is a **system of record**, versioned and audited (§35, §44); a
  poisoned/incorrect pattern is rolled back and its downstream uses flagged.
- **[EXPERIMENTAL]** All auto-acceptance thresholds are conservative and operator-tunable.

### 42.5 Storage, observability, recovery

- Store: pattern records in PostgreSQL, artifacts in object store (§35).
- Metrics: `patterns_candidate`, `patterns_approved_total`, `patterns_rejected_total`,
  `pattern_reeval_triggered_total`, `pattern_failure_rate`.
- Recovery: versioned + rebuildable from provenance and the evidence it references.

---

## 43. Cross-domain pattern transfer

**Purpose.** Transfer a pattern from one domain to another **only when structurally
justified**, never by surface resemblance.

### 43.1 Transfer method

```
source pattern → function → mechanism → invariant → abstract pattern →
   target function → target constraints → candidate implementation → TEST
```

- Extract the **invariant** that makes the pattern work, abstract it, then check the target
  domain actually satisfies that invariant and the target constraints.
- **An apparent analogy must be tested structurally.** Two systems "looking similar" is not
  sufficient; the transfer produces a **candidate** (hypothesis) that must pass tests in
  the target domain before approval.

### 43.2 Guardrails

- `transfer_constraints` on the pattern gate eligibility.
- Failed structural tests → transfer rejected; the attempt (and why it failed) is recorded
  for future reference (turning failed transfers into knowledge).
- Successful transfers create a new, versioned pattern in the target domain with a
  `transfers_to`/`analogous_to` edge (§23) back to the source — provenance preserved.

### 43.3 Example

```
biology: "immune memory" (mechanism: retain signatures of past threats for fast response)
   invariant: cheap recall of prior adversarial encounters improves future response
   → security domain candidate: "attack-signature cache with decay"
   → target constraints: bounded memory, low false-positive tolerance
   → TEST against known attack replay set → pass ⇒ approve as a security pattern
   (fail ⇒ reject; record why)
```
