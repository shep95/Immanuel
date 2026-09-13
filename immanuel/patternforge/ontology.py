"""Universal Pattern Object + lifecycle (the Pattern Forge ontology).

Mirrors the uploaded Pattern Forge schema: a pattern records the *mechanism*
responsible for a class of situations, not a single fact. Every pattern carries
evidence, confidence, scope, tests/falsifiers, and a lifecycle state so an
untested discovery stays a hypothesis until it earns promotion.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

# Pattern scope — how widely a pattern is allowed to apply (narrow -> broad).
SCOPES = (
    "ephemeral", "task", "conversation", "project", "user", "domain", "system",
)

# Lifecycle — a novel/untested pattern must not become system behavior directly.
STATUSES = (
    "unknown", "candidate", "testing", "validated", "active", "deprecated", "retired",
)

# Epistemic firewall labels (kept distinct, never silently converted).
EPISTEMIC = (
    "observation", "interpretation", "hypothesis", "inference",
    "estimate", "fact", "assumption", "unknown",
)


def stable_id(family: str, key: str) -> str:
    """Deterministic id so re-running the forge updates, not duplicates."""
    h = hashlib.sha1(f"{family}::{key}".encode("utf-8", "ignore")).hexdigest()[:16]
    return f"pf_{family}_{h}"


@dataclass
class PatternObject:
    pattern_id: str
    name: str
    family: str                      # miner family (e.g. topic_category)
    domain: str = "knowledge"        # ontology domain this pattern lives in
    scope: str = "domain"
    trigger: str = ""                # when this pattern applies
    mechanism: str = ""              # HOW the structure is produced
    function: str = ""               # WHAT it does / lets you predict
    invariant: str = ""              # what stays true across instances
    evidence: list = field(default_factory=list)  # supporting observations
    evidence_count: int = 0
    confidence: float = 0.0
    epistemic_status: str = "hypothesis"
    tests: list = field(default_factory=list)         # how to confirm
    falsifiers: list = field(default_factory=list)    # what would break it
    success_conditions: list = field(default_factory=list)
    failure_modes: list = field(default_factory=list)
    transfer_constraints: list = field(default_factory=list)
    status: str = "candidate"
    created_at: float = field(default_factory=time.time)

    # ------------------------------------------------------------------ helpers
    def lifecycle(self, prior_status: str | None, *, min_evidence: int,
                  min_confidence: float) -> str:
        """Determine the lifecycle state from evidence + confidence + history."""
        if self.evidence_count < min_evidence:
            return "candidate"
        if self.confidence < min_confidence:
            return "testing"
        # meets the bar -> validated; promote to active if it already held before
        if prior_status in ("validated", "active"):
            return "active"
        return "validated"

    def to_data(self) -> dict:
        """Full universal pattern object for storage / skill export."""
        return {
            "identity": self.pattern_id,
            "name": self.name,
            "family": self.family,
            "domain": self.domain,
            "scope": self.scope,
            "trigger": self.trigger,
            "mechanism": self.mechanism,
            "function": self.function,
            "invariant": self.invariant,
            "epistemic_status": self.epistemic_status,
            "evidence": self.evidence[:20],
            "evidence_count": self.evidence_count,
            "confidence": round(self.confidence, 3),
            "tests": self.tests,
            "falsifiers": self.falsifiers,
            "success_conditions": self.success_conditions,
            "failure_modes": self.failure_modes,
            "transfer_constraints": self.transfer_constraints,
            "status": self.status,
        }

    def to_row(self) -> dict:
        """Compact row for the ``patterns`` table."""
        return {
            "pattern_id": self.pattern_id,
            "name": self.name,
            "domain": self.domain,
            "family": self.family,
            "scope": self.scope,
            "mechanism": self.mechanism,
            "status": self.status,
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "data": self.to_data(),
        }
