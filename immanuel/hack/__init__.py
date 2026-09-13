"""/hack: an autonomous AI-pentest command for Immanuel.

Two engines behind one command:
- ``strix`` — drives the open-source Strix AI-pentesting agents (real exploit
  validation with working PoCs). Needs Docker + an LLM key at runtime.
- ``recon`` — Immanuel's own deterministic, non-AI reconnaissance (security
  headers, tech fingerprint, exposed-secret scan, surface map). Always works,
  no Docker / no LLM key / fully offline-testable.

``HackService`` picks the engine ("auto" = strix when ready, else recon),
persists the run, and renders a downloadable report.
"""
from __future__ import annotations

from .recon import recon
from .service import HackService
from .strix_runner import build_command, run_strix, strix_availability

__all__ = ["HackService", "recon", "strix_availability", "build_command", "run_strix"]
