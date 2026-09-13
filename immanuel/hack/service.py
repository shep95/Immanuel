"""HackService: pick an engine, run it, persist the run, render a report.

Used by the Discord `/hack` command and the API. Keeps all the decision logic
(engine selection, persistence, report rendering) out of the bot so it can be
unit-tested without Discord, Docker, or an LLM key.
"""
from __future__ import annotations

import json
import os
import time

from .recon import recon
from .strix_runner import run_strix, strix_availability


class HackService:
    def __init__(self, db, config):
        self.db = db
        self.config = config

    # ------------------------------------------------------------- helpers
    def availability(self) -> dict:
        strix = strix_availability(self.config)
        return {
            "enabled": getattr(self.config, "enable_hack", True),
            "configured_engine": getattr(self.config, "hack_engine", "auto"),
            "strix": strix,
            "recon": {"ready": True},  # deterministic engine is always available
        }

    def _choose_engine(self, requested: str | None) -> str:
        engine = (requested or getattr(self.config, "hack_engine", "auto") or "auto").lower()
        if engine == "strix":
            return "strix"
        if engine == "recon":
            return "recon"
        # auto
        return "strix" if strix_availability(self.config)["ready"] else "recon"

    # --------------------------------------------------------------- run
    async def run(self, target: str, instruction: str | None = None, *,
                  engine: str | None = None, requested_by: str | None = None,
                  on_line=None) -> dict:
        """Run a hack against ``target``; persist + return the result dict."""
        chosen = self._choose_engine(engine)
        run_id = self.db.add_hack_run(target, chosen, instruction, requested_by)

        try:
            if chosen == "strix":
                result = await run_strix(self.config, target, instruction,
                                         on_line=on_line)
                # explicit strix request but not runnable -> honest fallback to recon
                if result.get("status") == "unavailable" and \
                        (engine or getattr(self.config, "hack_engine", "auto")) == "auto":
                    result = await recon(self.config, target, on_line=on_line)
            else:
                result = await recon(self.config, target, on_line=on_line)
        except Exception as exc:  # never let a run crash the bot/API
            result = {"engine": chosen, "status": "failed", "findings": [],
                      "summary": f"{type(exc).__name__}: {exc}"}

        findings = result.get("findings") or []
        report_path = self._write_report(run_id, target, result)
        self.db.finish_hack_run(
            run_id, status=result.get("status", "completed"),
            summary=result.get("summary", ""), findings=findings,
            engine=result.get("engine", chosen), report_path=report_path)

        result["run_id"] = run_id
        result["report_path"] = report_path
        return result

    # ------------------------------------------------------------ report
    def _write_report(self, run_id: int, target: str, result: dict) -> str | None:
        path_dir = os.path.abspath(getattr(self.config, "hack_runs_path", "./data/hack"))
        try:
            os.makedirs(path_dir, exist_ok=True)
            path = os.path.join(path_dir, f"hack_{run_id}.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.render_report_text(run_id, target, result))
            return path
        except Exception:
            return None

    @staticmethod
    def render_report_text(run_id: int, target: str, result: dict) -> str:
        lines = [
            "ASHERIN / HACK REPORT",
            f"run: #{run_id}",
            f"target: {target}",
            f"engine: {result.get('engine', '?')}",
            f"status: {result.get('status', '?')}",
            f"summary: {result.get('summary', '')}",
            "",
        ]
        tech = result.get("tech") or {}
        if tech:
            lines.append("tech fingerprint:")
            for k, v in tech.items():
                lines.append(f"  - {k}: {v}")
            lines.append("")
        findings = result.get("findings") or []
        lines.append(f"findings ({len(findings)}):")
        if not findings:
            lines.append("  - none")
        for i, f in enumerate(findings, 1):
            sev = str(f.get("severity", "info")).upper()
            lines.append(f"  {i}. [{sev}] {f.get('title', '')}")
            detail = f.get("detail") or ""
            if detail:
                lines.append(f"       {detail[:300]}")
            if f.get("masked"):
                lines.append(f"       secret(masked): {f['masked']}")
            if f.get("page"):
                lines.append(f"       page: {f['page']}")
        if result.get("log_tail"):
            lines += ["", "strix log tail:", result["log_tail"]]
        lines.append("")
        lines.append("report written by asherin ai — observational; no exploitation.")
        return "\n".join(lines)
