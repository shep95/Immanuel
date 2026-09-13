import pytest

from immanuel.crawler.fetcher import FetchResult
from immanuel.crawler.pipeline import process_url


class MutableFetcher:
    """Fetcher stub whose returned body can change between calls."""
    def __init__(self, body: bytes):
        self.body = body
        self.client = object()

    def set_body(self, body: bytes):
        self.body = body

    async def fetch(self, url):
        return FetchResult(url, url, 200, "text/html", self.body, True)


class AllowRobots:
    async def allowed(self, url, client):
        return True


def _html(title, body):
    return f"<html><head><title>{title}</title></head><body><p>{body}</p></body></html>".encode()


@pytest.mark.asyncio
async def test_version_lifecycle(db):
    url = "https://ex.com/page"
    f = MutableFetcher(_html("News", "The agency confirmed the first report."))
    r = AllowRobots()

    # v1: brand new page
    res1 = await process_url(url, f, r, db, discover=False)
    assert res1.is_new_page is True
    assert res1.version_no == 1
    assert db.count_versions() == 1

    # same content again -> unchanged, no new version
    res2 = await process_url(url, f, r, db, discover=False)
    assert res2.unchanged is True
    assert db.count_versions() == 1

    # content changes -> update, v2, with the new data captured
    f.set_body(_html("News", "The agency confirmed the first report. A second official update was added."))
    res3 = await process_url(url, f, r, db, discover=False)
    assert res3.is_update is True
    assert res3.version_no == 2
    assert "second official update" in res3.added_text
    assert db.count_updates() == 1

    # timestamps present and ordered
    ts = db.url_timestamps(url)
    assert ts["versions"] == 2
    assert ts["first_seen"] <= ts["last_seen"]


@pytest.mark.asyncio
async def test_event_payload(db):
    url = "https://ex.com/p2"
    f = MutableFetcher(_html("Official", "confirmed data shows growth"))
    res = await process_url(url, f, AllowRobots(), db, discover=False)
    ev = res.event()
    assert ev["kind"] == "new"
    assert ev["url"] == url
    assert ev["category"] == "public_fact"
    assert ev["version_no"] == 1
