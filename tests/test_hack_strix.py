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


class _FakeStdout:
    def __init__(self, lines):
        self._lines = [l.encode() for l in lines]

    def __aiter__(self):
        async def _gen():
            for l in self._lines:
                yield l
        return _gen()


class _FakeProc:
    def __init__(self, cwd):
        self.stdout = _FakeStdout(["strix booting", "scan complete"])
        self.returncode = 0
        self._cwd = cwd

    async def wait(self):
        from pathlib import Path
        run = Path(self._cwd) / "strix_runs" / "run-xyz"
        run.mkdir(parents=True, exist_ok=True)
        (run / "run.json").write_text('{"status": "finished"}')
        (run / "v.json").write_text(
            '{"vulnerabilities": [{"title": "IDOR", "severity": "high"}]}')
        return 0

    def kill(self):
        pass


@pytest.mark.asyncio
async def test_run_strix_injects_byo_key_and_mounts_brains(tmp_path, monkeypatch):
    # strix + docker "present"
    monkeypatch.setattr(sr.shutil, "which", lambda name: f"/usr/bin/{name}")
    captured = {}

    async def _fake_exec(*cmd, cwd=None, env=None, stdout=None, stderr=None):
        captured["cmd"] = list(cmd)
        captured["env"] = env
        return _FakeProc(cwd)

    monkeypatch.setattr(sr.asyncio, "create_subprocess_exec", _fake_exec)

    out = await sr.run_strix(
        _cfg(hack_runs_path=str(tmp_path)), "https://ex.com",
        instruction="focus on auth", api_key="sk-user-123", model="prov/model-x")

    assert out["status"] == "completed"
    assert out["framework"] == "pattern-forge"
    assert any(f["title"] == "IDOR" for f in out["findings"])
    # bring-your-own key + model landed in the child env
    assert captured["env"]["LLM_API_KEY"] == "sk-user-123"
    assert captured["env"]["STRIX_LLM"] == "prov/model-x"
    # thinking architecture => instruction-file + mounted brain files
    assert "--instruction-file" in captured["cmd"]
    assert captured["cmd"].count("--workspace-file") == 5
    assert "--target" in captured["cmd"] and "https://ex.com" in captured["cmd"]


@pytest.mark.asyncio
async def test_run_strix_no_arch_uses_inline_instruction(tmp_path, monkeypatch):
    monkeypatch.setattr(sr.shutil, "which", lambda name: f"/usr/bin/{name}")
    captured = {}

    async def _fake_exec(*cmd, cwd=None, env=None, stdout=None, stderr=None):
        captured["cmd"] = list(cmd)
        return _FakeProc(cwd)

    monkeypatch.setattr(sr.asyncio, "create_subprocess_exec", _fake_exec)
    await sr.run_strix(
        _cfg(hack_runs_path=str(tmp_path), hack_thinking_arch=False),
        "ex.com", instruction="only headers", api_key="k", model="m")
    assert "--instruction-file" not in captured["cmd"]
    assert "--workspace-file" not in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--instruction") + 1] == "only headers"
