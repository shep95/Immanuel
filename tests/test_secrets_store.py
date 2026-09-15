"""Uncensored-storage path: raw value persists ONLY when explicitly provided,
and the pipeline only provides it when config.secrets_uncensored is on."""
from immanuel.config import Config
from immanuel.crawler.fetcher import FetchResult
from immanuel.crawler.pipeline import process_url

_STRIPE = "sk_" + "live_" + "abcdEFGH1234ijklMNOP5678"
LEAK_HTML = (
    "<!doctype html><html><head><title>Acme Billing</title></head>"
    f"<body><script>var stripe='{_STRIPE}';</script>"
    "<a href='https://acme.example/next'>n</a></body></html>"
).encode()


def test_add_secret_persists_raw_only_when_given(db):
    db.add_secret("https://acme.example", "acme.example", "stripe_secret_key",
                  "sk_l…5678", "sha256:aa", "var stripe=…", "high",
                  company="Acme", raw=_STRIPE)
    db.add_secret("https://acme.example/2", "acme.example", "aws_access_key_id",
                  "AKIA…MPLE", "sha256:bb", "ctx", "high", company="Acme")  # no raw
    rows = {r["secret_type"]: r for r in db.recent_secrets(10)}
    assert rows["stripe_secret_key"]["secret_raw"] == _STRIPE
    assert rows["aws_access_key_id"]["secret_raw"] is None


class _Fetcher:
    def __init__(self, body, root):
        self._body = body
        self._root = root
        self.client = object()

    async def fetch(self, url, extra_headers=None):
        if url.rstrip("/") == self._root:
            return FetchResult(self._root, self._root, 200, "text/html",
                               self._body, True)
        return FetchResult(url, url, 404, "", b"", False, "HTTP 404")


class _Robots:
    async def allowed(self, url, client):
        return True


import pytest


@pytest.mark.asyncio
async def test_pipeline_uncensored_flag_controls_raw(db):
    # uncensored OFF -> no raw stored
    off = Config(scan_secrets=True, secrets_uncensored=False, deep_extract=True,
                 build_intel_report=False, publish_media=False,
                 publish_transcripts=False, enable_youtube=False)
    await process_url("https://acme.example",
                      _Fetcher(LEAK_HTML, "https://acme.example"), _Robots(), db,
                      config=off)
    row = next((r for r in db.recent_secrets(10)
                if r["domain"] == "acme.example"
                and r["secret_type"] == "stripe_secret_key"), None)
    assert row is not None
    assert row["secret_raw"] is None

    # uncensored ON (different host so the unique fingerprint+url inserts fresh)
    on = Config(scan_secrets=True, secrets_uncensored=True, deep_extract=True,
                build_intel_report=False, publish_media=False,
                publish_transcripts=False, enable_youtube=False)
    body_on = LEAK_HTML.replace(b"acme.example", b"acme-on.example")
    await process_url("https://acme-on.example",
                      _Fetcher(body_on, "https://acme-on.example"), _Robots(), db,
                      config=on)
    rows = [r for r in db.recent_secrets(10)
            if r["domain"] == "acme-on.example"
            and r["secret_type"] == "stripe_secret_key"]
    assert any(r["secret_raw"] == _STRIPE for r in rows)
