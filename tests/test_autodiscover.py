import pytest

from immanuel.config import Config
from immanuel.crawler.bootstrap import DEFAULT_SEEDS, bootstrap_seeds
from immanuel.crawler.domain_firehose import hosts_to_urls, parse_ct_domains
from immanuel.engine import Engine


def test_bootstrap_seeds_nonempty():
    seeds = bootstrap_seeds()
    assert len(seeds) >= 10
    assert all(s.startswith("http") for s in seeds)
    assert seeds is not DEFAULT_SEEDS  # returns a copy


@pytest.mark.asyncio
async def test_engine_auto_seeds(db):
    # auto_discover on, no manual seeds, wayback off -> loads built-in seeds
    cfg = Config(auto_discover=True, enable_wayback=False)
    eng = Engine(db, cfg)
    added = await eng.seed()
    assert added >= 10
    assert db.count_sources() >= 10
    assert db.count_domains() >= 5


@pytest.mark.asyncio
async def test_engine_no_auto_when_disabled(db):
    cfg = Config(auto_discover=False, seed_urls=["https://example.com/"])
    eng = Engine(db, cfg)
    added = await eng.seed()
    assert added == 1
    assert db.count_sources() == 1


def test_parse_ct_domains():
    payload = (
        '[{"name_value": "example.com\\nwww.example.com"},'
        ' {"name_value": "*.sub.example.org"},'
        ' {"name_value": "example.com"}]'  # duplicate ignored
    )
    hosts = parse_ct_domains(payload, limit=10)
    assert "example.com" in hosts
    assert "www.example.com" in hosts
    assert "sub.example.org" in hosts  # wildcard stripped
    assert hosts.count("example.com") == 1


def test_parse_ct_bad_json():
    assert parse_ct_domains("not json") == []


def test_hosts_to_urls():
    urls = hosts_to_urls(["example.com", "www.foo.com"])
    assert "https://example.com/" in urls
    assert "https://www.example.com/" in urls   # www variant added
    assert "https://www.foo.com/" in urls
