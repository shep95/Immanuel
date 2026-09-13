import time


def _item(h="sha256:aaa", url="https://ex.com/a", cat="public_fact"):
    return {
        "content_hash": h, "url": url, "source_domain": "ex.com",
        "title": "t", "content": "body", "excerpt": "body",
        "media": [{"type": "image", "url": "https://ex.com/i.png"}],
        "category": cat, "category_confidence": 0.8, "signals": ["fact:confirmed"],
        "epistemic_status": "observation", "timeline_ts": None,
        "collector": "live", "fetched_at": time.time(),
    }


def test_add_and_dedup(db):
    rid = db.add_item(_item())
    assert rid is not None
    # duplicate content_hash -> None
    assert db.add_item(_item()) is None
    assert db.count_items() == 1
    assert db.item_exists("sha256:aaa")


def test_counts_by_category(db):
    db.add_item(_item("sha256:1", cat="public_fact"))
    db.add_item(_item("sha256:2", cat="conspiracy"))
    counts = db.counts_by_category()
    assert counts["public_fact"] == 1 and counts["conspiracy"] == 1


def test_search_filters(db):
    db.add_item(_item("sha256:1", url="https://a.com/x", cat="public_fact"))
    db.add_item(_item("sha256:2", url="https://b.com/y", cat="public_rumor"))
    assert len(db.search_items(category="public_rumor")) == 1
    assert len(db.search_items(query="body")) == 2
    assert len(db.search_items(domain="ex.com")) == 2


def test_sources(db):
    assert db.add_source("https://a.com", "seed") is True
    assert db.add_source("https://a.com", "seed") is False  # dup
    due = db.due_sources(10, 0)
    assert len(due) == 1
    db.mark_source_crawled(due[0]["id"], ok=True)
    assert db.count_sources("active") == 1


def test_member_log(db):
    db.log_member_event("g1", "u1", "user#1", "join")
    db.log_member_event("g1", "u1", "user#1", "leave")
    ev = db.recent_member_events()
    assert len(ev) == 2 and ev[0]["event"] == "leave"


def test_kv_state(db):
    db.set_state("engine_state", "running")
    assert db.get_state("engine_state") == "running"
    db.set_state("engine_state", "paused")
    assert db.get_state("engine_state") == "paused"
