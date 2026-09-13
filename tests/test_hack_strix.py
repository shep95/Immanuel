import json

import pytest

from immanuel.config import Config
from immanuel.hack import strix_runner as sr


def _cfg(**kw):
    base = dict(strix_bin="strix", strix_scan_mode="standard",
                strix_max_budget_usd=2.0, strix_max_turns=0)
    base.update(kw)
    return Config(**base)


def test_build_command_minimal():
    cmd = sr.build_command(_cfg(), "https://ex.com")
    assert cmd[0] == "strix"
    assert "--target" in cmd and "https://ex.com" in cmd
    assert "-n" in cmd                       # non-interactive
    assert cmd[cmd.index("-m") + 1] == "standard"
    assert cmd[cmd.index("--max-budget") + 1] == "2.0"
    assert "--max-turns" not in cmd          # 0 => omitted


def test_build_command_with_instruction_and_turns():
    cmd = sr.build_command(_cfg(strix_max_turns=50), "ex.com",
                           instruction="focus on auth")
    assert cmd[cmd.index("--instruction") + 1] == "focus on auth"
    assert cmd[cmd.index("--max-turns") + 1] == "50"


def test_availability_reports_missing(monkeypatch):
    monkeypatch.setattr(sr.shutil, "which", lambda _: None)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("STRIX_LLM", raising=False)
    a = sr.strix_availability(_cfg())
    assert a["ready"] is False
    assert not a["strix"] and not a["docker"] and not a["llm"]
    assert len(a["reasons"]) == 3


def test_availability_ready(monkeypatch):
    monkeypatch.setattr(sr.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    a = sr.strix_availability(_cfg(strix_llm="openrouter/z-ai/glm-5.3"))
    assert a["strix"] and a["docker"] and a["llm"] and a["ready"]


def test_parse_run_dir(tmp_path):
    run = tmp_path / "strix_runs" / "brave-otter"
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"status": "finished"}))
    (run / "vuln.json").write_text(json.dumps({
        "vulnerabilities": [
            {"title": "SQL Injection", "severity": "high",
             "description": "param id is injectable"},
            {"title": "Reflected XSS", "severity": "medium"},
        ]}))
    findings, summary = sr.parse_run_dir(run)
    titles = {f["title"] for f in findings}
    assert "SQL Injection" in titles and "Reflected XSS" in titles
    assert any(f["severity"] == "high" for f in findings)
    assert "2 finding" in summary and "finished" in summary


@pytest.mark.asyncio
async def test_run_strix_unavailable(monkeypatch):
    monkeypatch.setattr(sr.shutil, "which", lambda _: None)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    out = await sr.run_strix(_cfg(), "https://ex.com")
    assert out["status"] == "unavailable"
    assert out["findings"] == []
    assert out["reasons"]
