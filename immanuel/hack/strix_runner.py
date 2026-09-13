"""Drive the open-source Strix AI-pentesting CLI (strix-agent) as a subprocess.

Strix runs autonomous AI hacker agents inside a Docker sandbox and validates
findings with real PoCs. It needs, at runtime:
  - the `strix` CLI on PATH  (pip install strix-agent)
  - Docker running
  - an LLM key:  STRIX_LLM + LLM_API_KEY

We never import strix in-process (heavy, Docker-bound). We shell out to the CLI
in non-interactive mode, stream its output, then read the run directory it wrote
under `<hack_runs_path>/strix_runs/<run-name>/`. When the environment can't run
Strix, this reports `unavailable` cleanly and the caller falls back to recon.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path


def strix_availability(config) -> dict:
    """What's present for a real Strix run, and what's missing."""
    strix_bin = getattr(config, "strix_bin", "strix") or "strix"
    has_strix = shutil.which(strix_bin) is not None
    has_docker = shutil.which("docker") is not None
    llm_model = (getattr(config, "strix_llm", "") or os.getenv("STRIX_LLM", "")).strip()
    llm_key = (os.getenv("LLM_API_KEY", "") or os.getenv("STRIX_LLM_API_KEY", "")).strip()
    has_llm = bool(llm_model and llm_key)

    reasons: list[str] = []
    if not has_strix:
        reasons.append(f"strix CLI not found (pip install strix-agent) [{strix_bin}]")
    if not has_docker:
        reasons.append("docker not found on PATH (Strix runs agents in a sandbox)")
    if not has_llm:
        reasons.append("set STRIX_LLM + LLM_API_KEY (any supported provider)")
    return {
        "strix": has_strix, "docker": has_docker, "llm": has_llm,
        "ready": has_strix and has_docker and has_llm, "reasons": reasons,
    }


def build_command(config, target: str, instruction: str | None = None) -> list[str]:
    """Assemble the non-interactive `strix` invocation."""
    cmd = [getattr(config, "strix_bin", "strix") or "strix",
           "--target", target,
           "-n",                                   # non-interactive, exit on done
           "-m", getattr(config, "strix_scan_mode", "standard") or "standard"]
    budget = getattr(config, "strix_max_budget_usd", 0) or 0
    if budget and budget > 0:
        cmd += ["--max-budget", str(budget)]
    turns = getattr(config, "strix_max_turns", 0) or 0
    if turns and turns > 0:
        cmd += ["--max-turns", str(turns)]
    if instruction:
        cmd += ["--instruction", instruction]
    return cmd


def _strix_env(config) -> dict:
    env = dict(os.environ)
    model = (getattr(config, "strix_llm", "") or "").strip()
    if model and not env.get("STRIX_LLM"):
        env["STRIX_LLM"] = model
    return env


def _run_dirs(runs_base: Path) -> list[Path]:
    if not runs_base.is_dir():
        return []
    return [c for c in runs_base.iterdir()
            if c.is_dir() and (c / "run.json").is_file()]


def parse_run_dir(run_dir: Path | str | None) -> tuple[list[dict], str]:
    """Best-effort, schema-tolerant extraction of findings from a Strix run dir.

    Reads run.json for status, then harvests any JSON objects carrying a
    title/severity (Strix vulnerability records) plus markdown reports under a
    vulnerabilities/reports folder. Robust to Strix schema drift.
    """
    if not run_dir:
        return [], ""
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        return [], ""

    findings: list[dict] = []
    seen: set[str] = set()

    def _consume(obj: object) -> None:
        if isinstance(obj, dict):
            title = obj.get("title") or obj.get("name") or obj.get("vulnerability")
            sev = (obj.get("severity") or obj.get("risk") or obj.get("cvss_severity")
                   or "info")
            if title:
                key = f"{title}|{sev}"
                if key not in seen:
                    seen.add(key)
                    findings.append({
                        "severity": str(sev).lower(),
                        "kind": "strix-finding",
                        "title": str(title)[:200],
                        "detail": str(obj.get("description")
                                      or obj.get("summary") or "")[:600],
                    })
            for v in obj.values():
                _consume(v)
        elif isinstance(obj, list):
            for v in obj:
                _consume(v)

    for path in run_dir.rglob("*.json"):
        try:
            _consume(json.loads(path.read_text(encoding="utf-8", errors="ignore")))
        except Exception:
            continue

    status = ""
    run_json = run_dir / "run.json"
    if run_json.is_file():
        try:
            rec = json.loads(run_json.read_text(encoding="utf-8", errors="ignore"))
            status = str(rec.get("status") or "")
        except Exception:
            pass

    summary = (f"strix run {run_dir.name}: {len(findings)} finding(s)"
               + (f" · status={status}" if status else ""))
    return findings, summary


async def run_strix(config, target: str, instruction: str | None = None, *,
                    on_line=None, timeout: float | None = None) -> dict:
    """Run Strix non-interactively; return an engine-result dict."""
    avail = strix_availability(config)
    if not avail["ready"]:
        return {"engine": "strix", "status": "unavailable",
                "findings": [], "reasons": avail["reasons"],
                "summary": "strix not runnable: " + "; ".join(avail["reasons"])}

    workdir = Path(os.path.abspath(getattr(config, "hack_runs_path", "./data/hack")))
    workdir.mkdir(parents=True, exist_ok=True)
    runs_base = workdir / "strix_runs"
    before = {p.name for p in _run_dirs(runs_base)}

    cmd = build_command(config, target, instruction)
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(workdir), env=_strix_env(config),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    except FileNotFoundError:
        return {"engine": "strix", "status": "unavailable", "findings": [],
                "reasons": ["strix CLI vanished at exec time"],
                "summary": "strix CLI not executable"}

    lines: list[str] = []

    async def _reader() -> None:
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode("utf-8", "ignore").rstrip()
            lines.append(line)
            if on_line:
                try:
                    await on_line(line)
                except Exception:
                    pass

    timed_out = False
    try:
        await asyncio.wait_for(
            asyncio.gather(_reader(), proc.wait()),
            timeout=timeout or getattr(config, "hack_timeout_seconds", 1800))
    except asyncio.TimeoutError:
        timed_out = True
        try:
            proc.kill()
        except Exception:
            pass

    rc = proc.returncode
    after = _run_dirs(runs_base)
    new = [p for p in after if p.name not in before] or after
    run_dir = max(new, key=lambda p: (p / "run.json").stat().st_mtime) if new else None
    findings, summary = parse_run_dir(run_dir)

    if timed_out:
        status = "timeout"
    elif rc == 0:
        status = "completed"
    else:
        status = "failed"
    return {
        "engine": "strix",
        "status": status,
        "returncode": rc,
        "run_dir": str(run_dir) if run_dir else None,
        "findings": findings,
        "summary": summary or f"strix exited with code {rc}",
        "log_tail": "\n".join(lines[-40:]),
    }
