"""Deterministic text diffing for page-version tracking.

When a page changes between captures, we compute exactly what was added and
removed so Immanuel can show "the timestamp of the new data and what updated".
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass

MAX_SNIPPET = 4000  # cap stored added/removed text


@dataclass
class Diff:
    summary: str
    added_text: str
    removed_text: str
    added_lines: int
    removed_lines: int
    changed_chars: int

    @property
    def changed(self) -> bool:
        return self.added_lines > 0 or self.removed_lines > 0


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def compute_diff(old_text: str, new_text: str) -> Diff:
    """Return the added/removed content between two texts."""
    old = _lines(old_text)
    new = _lines(new_text)
    sm = difflib.SequenceMatcher(a=old, b=new, autojunk=False)

    added, removed = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("insert", "replace"):
            added.extend(new[j1:j2])
        if tag in ("delete", "replace"):
            removed.extend(old[i1:i2])

    added_text = "\n".join(added)[:MAX_SNIPPET]
    removed_text = "\n".join(removed)[:MAX_SNIPPET]
    changed_chars = len(added_text) + len(removed_text)

    parts = []
    if added:
        parts.append(f"+{len(added)} lines")
    if removed:
        parts.append(f"-{len(removed)} lines")
    summary = ", ".join(parts) if parts else "no textual change"

    return Diff(
        summary=summary,
        added_text=added_text,
        removed_text=removed_text,
        added_lines=len(added),
        removed_lines=len(removed),
        changed_chars=changed_chars,
    )
