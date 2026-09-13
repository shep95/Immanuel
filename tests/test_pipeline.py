import pytest

from immanuel.crawler.fetcher import FetchResult
from immanuel.crawler.pipeline import process_url

HTML = (b"<!doctype html><html><head><title>Confirmed official report</title></head>"
        b"<body><p>The agency confirmed the data shows growth.</p>"
        b"<a href='https://more.com/a'>a</a></body></html>")


class FakeFetcher:
    def __init__(self, result):
        self._result = result
        self.client = object()

    async def fetch(self, url):
        return self._result


class FakeRobots:
    def __init__(self, allow=True):
        self.allow = allow

    async def allowed(self, url, client):
        return self.allow


@pytest.mark.asyncio
async def test_process_stores_and_classifies(db):
    res = FetchResult("https://ex.com/p", "https://ex.com/p", 200, "text/html", HTML, True)
    out = await process_url("https://ex.com/p", FakeFetcher(res), FakeRobots(), db)
    assert out.stored is True
    assert out.category == "public_fact"
    assert db.count_items() == 1
    assert out.discovered >= 1  # discovered https://more.com/a as a source


@pytest.mark.asyncio
async def test_process_dedup(db):
    res = FetchResult("https://ex.com/p", "https://ex.com/p", 200, "text/html", HTML, True)
    out1 = await process_url("https://ex.com/p", FakeFetcher(res), FakeRobots(), db)
    assert out1.is_new_page is True
    out2 = await process_url("https://ex.com/p", FakeFetcher(res), FakeRobots(), db)
    assert out2.stored is False
    assert out2.unchanged is True
    assert db.count_items() == 1        # content-addressed: still one blob
    assert db.count_versions() == 1     # unchanged -> no new version


@pytest.mark.asyncio
async def test_robots_block(db):
    res = FetchResult("https://ex.com/p", "https://ex.com/p", 200, "text/html", HTML, True)
    out = await process_url("https://ex.com/p", FakeFetcher(res), FakeRobots(allow=False), db)
    assert out.skipped is True
    assert "robots" in out.reason
    assert db.count_items() == 0


@pytest.mark.asyncio
async def test_fetch_failure(db):
    res = FetchResult("https://ex.com/p", "https://ex.com/p", 0, "", b"", False, "boom")
    out = await process_url("https://ex.com/p", FakeFetcher(res), FakeRobots(), db)
    assert out.stored is False and out.skipped is True
