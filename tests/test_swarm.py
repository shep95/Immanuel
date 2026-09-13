import pytest

from immanuel.config import Config
from immanuel.crawler import swarm as swarm_mod
from immanuel.crawler.pipeline import ProcessResult
from immanuel.engine import Engine


class DummyFetcher:
    def __init__(self, *a, **k):
        self.client = object()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class DummyRobots:
    def __init__(self, *a, **k):
        pass


# Simulated web graph: a -> b, c ; b -> d ; others terminal.
GRAPH = {
    "https://ex.com/a": ["https://ex.com/b", "https://ex.com/c"],
    "https://ex.com/b": ["https://ex.com/d"],
}


async def fake_process_url(url, fetcher, robots, db, max_links=20,
                           collector="live", discover=True):
    links = GRAPH.get(url, [])
    # register discovered links as sources, like the real pipeline does
    if discover:
        for l in links:
            db.add_source(l, kind="discovered")
    return ProcessResult(
        url=url, stored=True, is_new_page=True, version_no=1,
        category="public_fact", title=url, domain="ex.com", links=links,
    )


@pytest.mark.asyncio
async def test_swarm_fans_out(db, monkeypatch):
    monkeypatch.setattr(swarm_mod, "Fetcher", DummyFetcher)
    monkeypatch.setattr(swarm_mod, "RobotsCache", DummyRobots)
    monkeypatch.setattr(swarm_mod, "process_url", fake_process_url)

    cfg = Config(crawler_mode="swarm", max_agents=10, recrawl_interval_seconds=9999)
    eng = Engine(db, cfg)
    db.add_source("https://ex.com/a", kind="seed")
    eng.start()

    sw = swarm_mod.AgentSwarm(eng)
    await sw.drain_once()

    # every reachable page got its own agent, exactly once each
    assert sw.visited.keys() >= {"https://ex.com/a", "https://ex.com/b",
                                 "https://ex.com/c", "https://ex.com/d"}
    assert sw.spawned == 4
    assert eng.stats["new_pages"] == 4
    assert sw.stats()["agents_active"] == 0  # all settled


@pytest.mark.asyncio
async def test_swarm_concurrency_capped(db, monkeypatch):
    monkeypatch.setattr(swarm_mod, "Fetcher", DummyFetcher)
    monkeypatch.setattr(swarm_mod, "RobotsCache", DummyRobots)
    monkeypatch.setattr(swarm_mod, "process_url", fake_process_url)

    cfg = Config(crawler_mode="swarm", max_agents=2, recrawl_interval_seconds=9999)
    eng = Engine(db, cfg)
    db.add_source("https://ex.com/a", kind="seed")
    eng.start()

    sw = swarm_mod.AgentSwarm(eng)
    await sw.drain_once()
    # never exceeded the configured agent cap
    assert sw.peak <= 2


@pytest.mark.asyncio
async def test_swarm_hop_limit(db, monkeypatch):
    monkeypatch.setattr(swarm_mod, "Fetcher", DummyFetcher)
    monkeypatch.setattr(swarm_mod, "RobotsCache", DummyRobots)

    # a -> b -> c -> d -> e (a straight chain 5 deep)
    chain = {
        "https://ex.com/a": ["https://ex.com/b"],
        "https://ex.com/b": ["https://ex.com/c"],
        "https://ex.com/c": ["https://ex.com/d"],
        "https://ex.com/d": ["https://ex.com/e"],
    }

    async def walk(url, *a, **k):
        return ProcessResult(url=url, stored=True, is_new_page=True,
                             links=chain.get(url, []))

    monkeypatch.setattr(swarm_mod, "process_url", walk)

    # max_hops=2 -> visit a(0), b(1), c(2); d(3) and e(4) must NOT be crawled
    cfg = Config(crawler_mode="swarm", max_agents=5, recrawl_interval_seconds=9999,
                 max_hops=2, auto_discover=False)
    eng = Engine(db, cfg)
    db.add_source("https://ex.com/a", kind="seed")
    eng.start()

    sw = swarm_mod.AgentSwarm(eng)
    await sw.drain_once()
    assert sw.visited.keys() == {"https://ex.com/a", "https://ex.com/b", "https://ex.com/c"}
    assert "https://ex.com/d" not in sw.visited
    assert sw.spawned == 3


@pytest.mark.asyncio
async def test_swarm_dedup_no_respawn(db, monkeypatch):
    monkeypatch.setattr(swarm_mod, "Fetcher", DummyFetcher)
    monkeypatch.setattr(swarm_mod, "RobotsCache", DummyRobots)

    # a -> b, and b -> a (cycle): must not spawn infinitely
    cyclic = {"https://ex.com/a": ["https://ex.com/b"],
              "https://ex.com/b": ["https://ex.com/a"]}

    async def cyc(url, *a, **k):
        return ProcessResult(url=url, stored=True, is_new_page=True,
                             links=cyclic.get(url, []))

    monkeypatch.setattr(swarm_mod, "process_url", cyc)

    cfg = Config(crawler_mode="swarm", max_agents=5, recrawl_interval_seconds=9999)
    eng = Engine(db, cfg)
    db.add_source("https://ex.com/a", kind="seed")
    eng.start()

    sw = swarm_mod.AgentSwarm(eng)
    await sw.drain_once()
    assert sw.spawned == 2  # a and b once each, cycle did not re-spawn
