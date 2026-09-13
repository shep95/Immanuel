import pytest

from immanuel.config import Config
from immanuel.discordbot.publisher import UPDATES_CHANNEL, Publisher


class FakeChannel:
    def __init__(self, name):
        self.name = name
        self.sent = []

    async def send(self, *args, embed=None, **kwargs):
        self.sent.append(embed)
        return object()


class FakeBot:
    def __init__(self, channels):
        # channels: name -> FakeChannel ; assign ids
        self._by_id = {}
        self.name_to_id = {}
        for i, (name, ch) in enumerate(channels.items(), start=1000):
            self._by_id[i] = ch
            self.name_to_id[name] = i
        self.guilds = []

    def get_guild(self, gid):
        return None

    def get_channel(self, cid):
        return self._by_id.get(cid)


@pytest.fixture()
def wired(db):
    channels = {
        "public-facts": FakeChannel("public-facts"),
        "conspiracies": FakeChannel("conspiracies"),
        UPDATES_CHANNEL: FakeChannel(UPDATES_CHANNEL),
    }
    bot = FakeBot(channels)
    pub = Publisher(bot, db, Config())
    # pre-seed the channel cache so we skip guild creation
    for name, cid in bot.name_to_id.items():
        pub._chan_cache[name] = cid
    return pub, channels


@pytest.mark.asyncio
async def test_publish_new_routes_to_category(wired):
    pub, channels = wired
    await pub.publish({
        "kind": "new", "url": "https://ex.com/a", "domain": "ex.com",
        "title": "Official report", "category": "public_fact", "version_no": 1,
        "excerpt": "confirmed data", "fetched_at": 1_700_000_000, "media": [],
    })
    assert len(channels["public-facts"].sent) == 1
    emb = channels["public-facts"].sent[0]
    assert emb.title == "Official report"


@pytest.mark.asyncio
async def test_publish_new_conspiracy(wired):
    pub, channels = wired
    await pub.publish({
        "kind": "new", "url": "https://ex.com/c", "domain": "ex.com",
        "title": "Hidden truth", "category": "conspiracy", "version_no": 1,
        "excerpt": "cover-up", "fetched_at": 1_700_000_000, "media": [],
    })
    assert len(channels["conspiracies"].sent) == 1


@pytest.mark.asyncio
async def test_publish_update_routes_to_updates(wired):
    pub, channels = wired
    await pub.publish({
        "kind": "update", "url": "https://ex.com/a", "domain": "ex.com",
        "title": "Official report", "category": "public_fact", "version_no": 2,
        "diff_summary": "+3 lines", "added_text": "brand new paragraph",
        "excerpt": "x", "fetched_at": 1_700_000_100, "media": [],
    })
    assert len(channels[UPDATES_CHANNEL].sent) == 1
    emb = channels[UPDATES_CHANNEL].sent[0]
    assert "Updated" in emb.title
