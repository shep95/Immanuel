import pytest

from immanuel.config import Config
from immanuel.crawler.fetcher import FetchResult
from immanuel.crawler.pipeline import process_url

DEEP_HTML = (
    b"<!doctype html><html lang='en'><head><title>Ransomware breach at hospital</title>"
    b"<meta name='description' content='exploit and phishing incident'>"
    b"<meta property='og:site_name' content='Acme News'>"
    b"<script>var k='AKIAIOSFODNN7EXAMPLE';</script>"
    b"<script src='https://cdn.acme.com/app.js'></script></head>"
    b"<body><h1>Breach</h1><p>attackers used an exploit and phishing.</p>"
    b"<img src='/i.png'><a href='https://other.com/z'>z</a></body></html>"
)


class FakeFetcher:
    def __init__(self, result):
        self._result = result
        self.client = object()

    async def fetch(self, url, extra_headers=None):
        return self._result


class FakeRobots:
    async def allowed(self, url, client):
        return True


def _cfg(**kw):
    return Config(download_media=False, enable_youtube=False,
                  scan_secrets=True, build_intel_report=True, **kw)


@pytest.mark.asyncio
async def test_deep_extract_stores_company_topic_secrets(db):
    res = FetchResult("https://acme.com/p", "https://acme.com/p", 200,
                      "text/html", DEEP_HTML, True)
    out = await process_url("https://acme.com/p", FakeFetcher(res), FakeRobots(),
                            db, config=_cfg())
    assert out.company == "Acme News"          # from og:site_name
    assert out.topic == "security-cyber"       # from keywords
    assert out.secrets                          # AWS key detected
    assert out.intel is True

    # item persisted with organization + secrets_count
    rows = db.search_items(company="Acme News")
    assert rows and rows[0]["topic"] == "security-cyber"
    assert rows[0]["secrets_count"] >= 1
    assert rows[0]["lang"] == "en"

    # secret recorded (masked) + intel report persisted
    assert db.count_secrets() >= 1
    assert db.get_intel_report("https://acme.com/p") is not None
    findings = db.recent_secrets()
    assert "AKIAIOSFODNN7EXAMPLE" not in str(findings)  # never stored raw


@pytest.mark.asyncio
async def test_304_not_modified_is_unchanged(db):
    # prime the cache
    db.set_http_cache("https://acme.com/p", etag='"abc"', last_modified=None,
                      content_hash="sha256:x")
    res = FetchResult("https://acme.com/p", "https://acme.com/p", 304, "", b"",
                      False, "HTTP 304", etag='"abc"')
    out = await process_url("https://acme.com/p", FakeFetcher(res), FakeRobots(),
                            db, config=_cfg())
    assert out.unchanged is True
    assert out.stored is False


@pytest.mark.asyncio
async def test_legacy_no_config_unchanged_behavior(db):
    res = FetchResult("https://acme.com/p", "https://acme.com/p", 200,
                      "text/html", DEEP_HTML, True)
    out = await process_url("https://acme.com/p", FakeFetcher(res), FakeRobots(), db)
    # without config: no deep fields computed
    assert out.company is None and out.topic is None and out.secrets == []
    assert out.media_items == [] and out.transcript is None


MEDIA_HTML = (
    b"<!doctype html><html lang='en'><head><title>Downloads</title></head>"
    b"<body><img src='https://cdn.acme.com/pic.png'>"
    b"<a href='https://acme.com/report.pdf'>report</a>"
    b"<a href='https://acme.com/audio/clip.mp3'>audio</a>"
    b"<a href='https://acme.com/bundle.zip'>zip</a>"
    b"<a href='https://acme.com/about'>about</a></body></html>"
)


@pytest.mark.asyncio
async def test_media_catalog_covers_all_file_types(db):
    res = FetchResult("https://acme.com/dl", "https://acme.com/dl", 200,
                      "text/html", MEDIA_HTML, True)
    out = await process_url("https://acme.com/dl", FakeFetcher(res), FakeRobots(),
                            db, config=_cfg())
    buckets = {it["type"] for it in out.media_items}
    assert {"image", "document", "audio", "archive"}.issubset(buckets)
    # the plain page link is not treated as a file
    assert all("/about" not in it["url"] for it in out.media_items)
    # media_event is well-formed for the publisher
    ev = out.media_event()
    assert ev["kind"] == "media" and ev["items"] and ev["page_url"].endswith("/dl")
