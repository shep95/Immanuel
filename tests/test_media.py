import pytest

from immanuel.config import Config
from immanuel.crawler.fetcher import FetchResult
from immanuel.media.downloader import download_media
from immanuel.media.youtube import is_youtube, process_youtube, video_id


def test_youtube_id_detection():
    assert video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert video_id("https://youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert video_id("https://ex.com/watch") is None
    assert is_youtube("https://youtu.be/dQw4w9WgXcQ")


def test_process_youtube_thumbnail_no_network():
    out = process_youtube("https://youtu.be/dQw4w9WgXcQ")
    assert out["video_id"] == "dQw4w9WgXcQ"
    assert out["thumbnail"].endswith("dQw4w9WgXcQ/maxresdefault.jpg")


class FakeFetcher:
    def __init__(self, body=b"\x89PNG\r\n\x1a\n_data"):
        self.client = object()
        self.body = body

    async def fetch(self, url, extra_headers=None):
        return FetchResult(url, url, 200, "image/png", self.body, True)


class FakeRobots:
    async def allowed(self, url, client):
        return True


@pytest.mark.asyncio
async def test_download_media_stores(tmp_path, db):
    cfg = Config(download_media=True, media_store_path=str(tmp_path / "media"),
                 media_types={"image"}, max_media_per_page=5)
    media = [{"type": "image", "url": "https://ex.com/a.png"},
             {"type": "video", "url": "https://ex.com/skip.mp4"}]
    stored = await download_media(FakeFetcher(), FakeRobots(), db, cfg,
                                  "https://ex.com/p", media)
    assert len(stored) == 1                      # only the allowed image type
    assert stored[0]["media_type"] == "image"
    assert db.count_media_assets() == 1
    # dedup: same bytes again -> not stored twice
    stored2 = await download_media(FakeFetcher(), FakeRobots(), db, cfg,
                                   "https://ex.com/p", media)
    assert stored2 == []
    assert db.count_media_assets() == 1


@pytest.mark.asyncio
async def test_download_media_disabled(db):
    cfg = Config(download_media=False)
    stored = await download_media(FakeFetcher(), FakeRobots(), db, cfg,
                                  "https://ex.com/p",
                                  [{"type": "image", "url": "https://ex.com/a.png"}])
    assert stored == []
