import pytest

from immanuel.config import Config
from immanuel.crawler.fetcher import FetchResult
from immanuel.hack.service import HackService

SECRET_HTML = (
    b"<!doctype html><html lang='en'><head><title>App</title></head>"
    b"<body><script>var k='AKIAIOSFODNN7EXAMPLE';</script>"
    b"<a href='https://ex.com/next'>n</a></body></html>"
)


class RootFetcher:
    """Doubles as the async-context-manager Fetcher (mirrors Fetcher.__aenter__)."""
    def __init__(self, root):
        self._root = root
        self.client = object()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def fetch(self, url, extra_headers=None):
        if url.rstrip("/") == "https://ex.com":
            return self._root
        return FetchResult(url, url, 404, "", b"", False, "HTTP 404")


def _cfg(tmp, **kw):
    return Config(hack_runs_path=str(tmp), hack_max_recon_pages=3,
                  hack_recon_hops=1, **kw)


@pytest.mark.asyncio
async def test_service_recon_run_persists_and_reports(db, tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, hack_engine="recon")
    svc = HackService(db, cfg)

    root = FetchResult("https://ex.com", "https://ex.com", 200, "text/html",
                       SECRET_HTML, True, headers={"server": "nginx"})

    # service.run -> recon(...) builds its own Fetcher; patch it to our fake
    # (which is both the context manager and the fetcher, like the real one).
    # importlib avoids the package re-export shadowing the submodule name.
    import importlib
    reconmod = importlib.import_module("immanuel.hack.recon")
    monkeypatch.setattr(reconmod, "Fetcher", lambda *a, **k: RootFetcher(root))

    result = await svc.run("ex.com", engine="recon", requested_by="admin")
    assert result["engine"] == "recon"
    assert result["status"] == "completed"
    assert result["secrets_count"] >= 1
    assert result["run_id"]

    # persisted
    row = db.get_hack_run(result["run_id"])
    assert row is not None
    assert row["status"] == "completed"
    assert row["findings_count"] >= 1
    assert db.count_hack_runs() == 1

    # downloadable report written, masked (never raw)
    assert row["report_path"]
    with open(row["report_path"], encoding="utf-8") as fh:
        text = fh.read()
    assert "ASHERIN / HACK REPORT" in text
    assert "AKIAIOSFODNN7EXAMPLE" not in text


@pytest.mark.asyncio
async def test_service_auto_falls_back_to_recon(db, tmp_path, monkeypatch):
    # auto + strix not ready -> recon
    import immanuel.hack.service as svcmod
    monkeypatch.setattr(svcmod, "strix_availability",
                        lambda _c: {"ready": False, "reasons": ["no docker"],
                                    "strix": False, "docker": False, "llm": False})
    cfg = _cfg(tmp_path, hack_engine="auto")
    svc = HackService(db, cfg)
    assert svc._choose_engine(None) == "recon"
    avail = svc.availability()
    assert avail["recon"]["ready"] is True
    assert avail["strix"]["ready"] is False
