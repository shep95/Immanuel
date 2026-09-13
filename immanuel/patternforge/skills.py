"""Export learned patterns as a downloadable skill file.

Renders the Pattern Forge library into a single human-readable ``.txt`` skill
document (validated/active patterns first), the artifact behind
``/skills-download`` and the ``/v1/patterns/export`` API.
"""
from __future__ import annotations

import datetime as dt
import os

_ORDER = {"active": 0, "validated": 1, "testing": 2, "candidate": 3,
          "deprecated": 4, "retired": 5, "unknown": 6}


def _render_pattern(p: dict) -> str:
    d = p.get("data", {})
    lines = [
        f"SKILL: {p['name']}",
        f"  id:         {p['pattern_id']}",
        f"  family:     {p.get('family')}",
        f"  domain:     {d.get('domain')}",
        f"  scope:      {d.get('scope')}",
        f"  status:     {p.get('status')}  (confidence {p.get('confidence'):.2f}, "
        f"evidence {p.get('evidence_count')})",
        f"  trigger:    {d.get('trigger')}",
        f"  mechanism:  {d.get('mechanism')}",
        f"  function:   {d.get('function')}",
        f"  invariant:  {d.get('invariant')}",
    ]
    if d.get("evidence"):
        lines.append("  evidence:   " + "; ".join(str(x) for x in d["evidence"][:8]))
    if d.get("tests"):
        lines.append("  tests:      " + "; ".join(d["tests"]))
    if d.get("falsifiers"):
        lines.append("  falsifiers: " + "; ".join(d["falsifiers"]))
    if d.get("success_conditions"):
        lines.append("  success:    " + "; ".join(d["success_conditions"]))
    if d.get("failure_modes"):
        lines.append("  failure:    " + "; ".join(d["failure_modes"]))
    return "\n".join(lines)


def render_skills(db, *, only_validated: bool = False) -> str:
    """Return the full skills document as text."""
    patterns = db.list_patterns()
    if only_validated:
        patterns = [p for p in patterns if p.get("status") in ("validated", "active")]
    patterns.sort(key=lambda p: (_ORDER.get(p.get("status"), 9),
                                 -float(p.get("confidence") or 0)))
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    counts: dict[str, int] = {}
    for p in patterns:
        counts[p["status"]] = counts.get(p["status"], 0) + 1

    header = [
        "asherin.eng — Pattern Forge skill export",
        "=" * 60,
        f"generated: {now}",
        f"patterns:  {len(patterns)}  (" +
        ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) + ")",
        "",
        "these are deterministic patterns learned by the non-AI Pattern Forge",
        "from the collected corpus. each records the mechanism behind a class of",
        "situations (not a single fact), with evidence, confidence, scope, and a",
        "falsifier. a novel/untested pattern stays a hypothesis until it earns",
        "promotion (candidate -> testing -> validated -> active).",
        "=" * 60,
        "",
    ]
    body = ("\n\n" + ("-" * 60) + "\n\n").join(_render_pattern(p) for p in patterns)
    return "\n".join(header) + body + "\n"


def export_skills_file(db, out_dir: str, *, only_validated: bool = False) -> str:
    """Write the skills document to ``out_dir`` and return the file path."""
    os.makedirs(out_dir, exist_ok=True)
    text = render_skills(db, only_validated=only_validated)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(out_dir, f"asherin_skills_{stamp}.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path
