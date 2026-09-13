"""The operational + functional thinking-architecture for the /hack AI.

The five Pattern Forge files shipped under ``brains/`` are the operating system
for the AI hacker: a universal pattern-intelligence layer (extract mechanism ->
normalize -> compose -> test -> verify) with a pattern-object ontology, a
universal debugger, narrative representation, and response discipline. They are
NOT a persona to imitate — they are reusable reasoning patterns.

This module (1) loads those brains, (2) composes a bounded operating-framework
instruction that is fed to the Strix agent as its ``--instruction-file``, and
(3) exposes the brain files so they can be mounted read-only into the sandbox
workspace (``--workspace-file``) — so the actual files, not just a summary, are
the operational system inside every run.
"""
from __future__ import annotations

import os

BRAINS_DIR = os.path.join(os.path.dirname(__file__), "brains")

# Ordered so the smaller framing docs load before the large elite corpus.
BRAIN_FILES = [
    "upload-reference.txt",
    "PatternForge-README.md",
    "PatternForge-SKILL.md",
    "adaptive-pattern-creator.txt",
    "shepherd-mass-elite-grade-system.txt",
]


def brain_paths() -> list[str]:
    """Absolute paths of the brain files that exist on disk."""
    out = []
    for name in BRAIN_FILES:
        p = os.path.join(BRAINS_DIR, name)
        if os.path.isfile(p):
            out.append(p)
    return out


def load_brains() -> dict[str, str]:
    """Return {filename: text} for every brain file present."""
    brains: dict[str, str] = {}
    for p in brain_paths():
        try:
            with open(p, encoding="utf-8", errors="ignore") as fh:
                brains[os.path.basename(p)] = fh.read()
        except Exception:
            continue
    return brains


def workspace_file_specs(dest_prefix: str = "skills/patternforge") -> list[str]:
    """`PATH:DEST` specs to mount each brain read-only into the sandbox."""
    specs = []
    for p in brain_paths():
        specs.append(f"{p}:{dest_prefix}/{os.path.basename(p)}")
    return specs


# The composed operating framework — Pattern Forge applied to offensive security.
# Faithful to the brains (mechanism > label, universal debugger, pattern object,
# narrative -> flaw -> retarget, response discipline, uncertainty explicit).
_ARCHITECTURE = """\
you operate under the pattern forge thinking architecture (loaded in full under
skills/patternforge/ in this workspace). it is a reasoning layer, not a persona
to imitate. extract mechanisms, normalize them into reusable primitives, compose
them, test the resulting strategy, and keep uncertainty explicit.

operating framework for this security assessment:

1. narrative first. before acting, build a compact narrative model of the target:
   actors, objects, entry points, trust boundaries, states, goals, inputs,
   outputs, constraints, dependencies, data/control/time flows, assumptions,
   and failure conditions. prefer mechanism over label and function over
   superficial similarity.

2. universal debugger applied to security:
   expected_model -> observed_model -> difference -> possible_causes ->
   discriminating_test -> root_cause -> validate. a vulnerability is a gap
   between the expected security model and the observed behavior — find the
   difference, then prove it.

3. represent each finding as a pattern object: identity, trigger, inputs,
   state_before, mechanism, transformations, state_after, evidence,
   evidence_quality, uncertainty, confidence, failure_modes, repair_patterns,
   tests, falsifiers, success_conditions. no finding without a mechanism and a
   discriminating test.

4. red-team narrative -> flaw -> retarget loop: write what was found, find the
   flaws in that narrative, and let those flaws point to the next target.
   repeat. compose held findings into chains only after live proof.

5. reconnaissance -> exploitation -> validation. validate with a real,
   reproducible proof-of-concept. never fabricate a finding, a PoC, or evidence.
   preserve unknown as a valid state when evidence is insufficient.

6. response discipline: report in lowercase by default; separate evidence,
   assumptions, inference, and conclusions; communicate calibrated uncertainty;
   no padding, no self-praise. remediation guidance with every validated finding.

7. scope discipline: only test what the operator authorized. do not pivot to
   out-of-scope systems, third parties, or destructive actions.
"""


def compose_instruction(user_instruction: str | None = None, *,
                        include_arch: bool = True) -> str:
    """Build the full instruction text fed to the AI agent."""
    parts: list[str] = []
    if include_arch:
        parts.append(_ARCHITECTURE)
    if user_instruction:
        parts.append("operator instruction for this run:\n" + user_instruction.strip())
    return "\n\n".join(parts).strip()
