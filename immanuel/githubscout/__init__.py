"""GitHub tool scout — the deterministic (non-AI) organ that continuously scans
public GitHub repositories and keeps the ones that are real *software* or
*algorithms* for osint / cyber-security / hacking / surveillance / red-team.

- ``classify`` decides the category + why-it's-useful, purely by keyword/topic
  signals and the repo's own metadata (no model, fully reproducible).
- ``scout`` is the 24/7 runner that searches GitHub, classifies, stores new
  finds, and emits them to the private owner-only Discord channel.
"""
from .classify import CATEGORY_SIGNALS, RepoClassification, classify_repo, is_software
from .scout import GitHubScout

__all__ = [
    "CATEGORY_SIGNALS",
    "RepoClassification",
    "classify_repo",
    "is_software",
    "GitHubScout",
]
