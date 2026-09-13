"""24/7 Pattern Forge loop — runs alongside the crawler.

Every ``pattern_forge_interval_seconds`` it runs one deterministic pass over the
whole collected corpus, updating the pattern library. It stays cheap (aggregate
queries only) and never blocks the crawler.
"""
from __future__ import annotations

import asyncio
import time

from . import forge


class PatternForge:
    def __init__(self, db, config, shutdown: "asyncio.Event | None" = None):
        self.db = db
        self.config = config
        self._shutdown = shutdown or asyncio.Event()
        self.passes = 0
        self.last_summary: dict | None = None
        self.last_run_at: float | None = None

    def snapshot(self) -> dict:
        return {
            "enabled": self.config.enable_pattern_forge,
            "passes": self.passes,
            "last_run_at": self.last_run_at,
            "patterns_total": self.db.count_patterns(),
            "validated": self.db.count_patterns("validated"),
            "active": self.db.count_patterns("active"),
            "last_summary": self.last_summary,
        }

    def run_once(self) -> dict:
        summary = forge.run_pass(
            self.db,
            min_evidence=self.config.pattern_min_evidence,
            min_confidence=self.config.pattern_min_confidence,
        )
        self.passes += 1
        self.last_run_at = time.time()
        self.last_summary = summary
        self.db.set_state("pattern_forge_last", str(int(self.last_run_at)))
        return summary

    async def run_forever(self) -> None:
        if not self.config.enable_pattern_forge:
            return
        interval = max(15.0, self.config.pattern_forge_interval_seconds)
        # small initial delay so the crawler has something to learn from
        try:
            await asyncio.wait_for(self._shutdown.wait(), timeout=min(interval, 30.0))
        except asyncio.TimeoutError:
            pass
        while not self._shutdown.is_set():
            try:
                await asyncio.to_thread(self.run_once)
            except Exception as e:  # never let the forge kill the process
                self.db.set_state("pattern_forge_error", f"{type(e).__name__}: {e}")
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    def request_shutdown(self) -> None:
        self._shutdown.set()
