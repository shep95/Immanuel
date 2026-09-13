from immanuel.config import Config
from immanuel.engine import PAUSED, RUNNING, STOPPED, Engine


def test_state_transitions(db):
    eng = Engine(db, Config())
    assert eng.state == STOPPED
    eng.start()
    assert eng.state == RUNNING
    assert eng.started_at is not None
    eng.pause()
    assert eng.state == PAUSED
    # pause only works from running
    assert "not running" in eng.pause()
    eng.start()
    eng.stop()
    assert eng.state == STOPPED
    # state persisted to kv
    assert db.get_state("engine_state") == STOPPED


def test_snapshot_shape(db):
    eng = Engine(db, Config())
    snap = eng.snapshot()
    for k in ("state", "uptime_seconds", "items_total", "by_category",
              "sources_total", "sources_active", "stats"):
        assert k in snap


def test_double_start(db):
    eng = Engine(db, Config())
    eng.start()
    assert "already running" in eng.start()
