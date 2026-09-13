import pytest

from immanuel.config import Config
from immanuel.crawler.fetcher import FetchResult
from immanuel.hack.recon import normalize_target, recon

RECON_HTML = (
    b"<!doctype html><html lang='en'><head><title>Login</title>"
    b"<meta name='generator' content='WordPress 6.1'></head>"
    b"<body><h1>Login</h1>"
    b"<script>var k='AKIAIOSFODNN7EXAMPLE';</script>"
    b"<a href='https://ex.com/admin'>admin</a></body></html>"
)


class OneShotFetcher:
    """Returns a fixed result for the root, empty 404s for everything else."""
    def __init__(self, root):
        self._root = root
        self.client = object()

    async def fetch(self, url, extra_headers=None):
        if url.rstrip("/") == "https://ex.com":
            return self._root
        return FetchResult(url, url, 404, "", b"", False, "HTTP 404")


class OkRobots:
    async def allowed(self, url, client):
        return True


def _cfg(**kw):
    return Config(hack_max_recon_pages=5, hack_recon_hops=1, **kw)


def test_normalize_target():
    assert normalize_target("ex.com") == "https://ex.com"
    assert normalize_target("https://ex.com/x") == "https://ex.com/x"
    assert normalize_target("1.2.3.4") == "https://1.2.3.4"


@pytest.mark.asyncio
async def test_recon_headers_secret_and_tech():
    root = FetchResult(
        "https://ex.com", "https://ex.com", 200, "text/html", RECON_HTML, True,
        headers={"server": "nginx/1.18.0", "x-powered-by": "PHP/8.1"})
    out = await recon(_cfg(), "ex.com", fetcher=OneShotFetcher(root),
                      robots=OkRobots())
    assert out["engine"] == "recon" and out["status"] == "completed"
    titles = " ".join(f["title"] for f in out["findings"])
    # missing security headers detected
    assert "HSTS" in titles
    assert "Content-Security-Policy" in titles
    # tech fingerprint from headers + meta generator
    assert out["tech"].get("server", "").startswith("nginx")
    assert out["tech"].get("generator", "").startswith("WordPress")
    # exposed AWS key detected + masked (never raw)
    assert out["secrets_count"] >= 1
    assert any(f["kind"] == "exposed-secret" for f in out["findings"])
    assert "AKIAIOSFODNN7EXAMPLE" not in str(out["findings"])


@pytest.mark.asyncio
async def test_recon_unreachable_target_is_graceful():
    dead = FetchResult("https://nope.tld", "https://nope.tld", 0, "", b"", False,
                       "timeout")

    class Dead:
        client = object()

        async def fetch(self, url, extra_headers=None):
            return dead

    out = await recon(_cfg(), "nope.tld", fetcher=Dead(), robots=OkRobots())
    assert out["status"] == "completed"  # never crashes
    assert out["secrets_count"] == 0
