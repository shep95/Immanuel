import time

import pytest
from fastapi.testclient import TestClient

from immanuel.api.app import create_app
from immanuel.keys import generate_api_key


def _seed_item(db, h, cat="public_fact"):
    db.add_item({
        "content_hash": h, "url": f"https://ex.com/{h}", "source_domain": "ex.com",
        "title": "Climate report", "content": "climate data confirmed",
        "excerpt": "climate data confirmed", "media": [],
        "category": cat, "category_confidence": 0.8, "signals": [],
        "epistemic_status": "observation", "timeline_ts": None,
        "collector": "live", "fetched_at": time.time(),
    })


@pytest.fixture()
def client(db):
    app = create_app(db, engine=None)
    return TestClient(app), db


def test_health_public(client):
    c, _ = client
    r = c.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_search_requires_key(client):
    c, _ = client
    assert c.get("/v1/search").status_code == 401


def test_search_with_key(client):
    c, db = client
    _seed_item(db, "sha256:1")
    _seed_item(db, "sha256:2", cat="conspiracy")
    key = generate_api_key(db, owner="tester")
    r = c.get("/v1/search", params={"q": "climate"}, headers={"X-API-Key": key})
    assert r.status_code == 200
    assert r.json()["count"] == 2


def test_search_category_filter(client):
    c, db = client
    _seed_item(db, "sha256:1", cat="public_fact")
    _seed_item(db, "sha256:2", cat="conspiracy")
    key = generate_api_key(db, owner="tester")
    r = c.get("/v1/search", params={"category": "conspiracy"},
              headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 200 and r.json()["count"] == 1


def test_bad_category(client):
    c, db = client
    key = generate_api_key(db, owner="tester")
    r = c.get("/v1/search", params={"category": "nope"}, headers={"X-API-Key": key})
    assert r.status_code == 400


def test_export(client):
    c, db = client
    _seed_item(db, "sha256:1")
    key = generate_api_key(db, owner="tester")
    r = c.get("/v1/export", headers={"X-API-Key": key})
    assert r.status_code == 200 and r.json()["count"] == 1
    assert "content" in r.json()["items"][0]


def _seed_org_item(db, h, company, topic):
    import time
    db.add_item({
        "content_hash": h, "url": f"https://ex.com/{h}", "source_domain": "ex.com",
        "title": "t", "content": "c", "excerpt": "c", "media": [],
        "category": "public_fact", "category_confidence": 0.8, "signals": [],
        "epistemic_status": "observation", "collector": "live",
        "company": company, "topic": topic, "meta": {}, "code": [],
        "secrets_count": 0, "fetched_at": time.time(),
    })


def test_companies_and_topics(client):
    c, db = client
    _seed_org_item(db, "sha256:1", "Acme", "technology")
    _seed_org_item(db, "sha256:2", "Acme", "technology")
    key = generate_api_key(db, owner="tester")
    rc = c.get("/v1/companies", headers={"X-API-Key": key})
    assert rc.status_code == 200
    assert rc.json()["companies"][0]["company"] == "Acme"
    rt = c.get("/v1/topics", headers={"X-API-Key": key})
    assert rt.json()["topics"][0]["topic"] == "technology"


def test_patterns_endpoint_requires_admin(client):
    c, db = client
    read_key = generate_api_key(db, owner="tester", scopes="read")
    assert c.get("/v1/patterns", headers={"X-API-Key": read_key}).status_code == 403
    admin_key = generate_api_key(db, owner="admin", scopes="read admin")
    r = c.get("/v1/patterns", headers={"X-API-Key": admin_key})
    assert r.status_code == 200 and "patterns" in r.json()


def test_secrets_requires_admin(client):
    c, db = client
    read_key = generate_api_key(db, owner="tester", scopes="read")
    assert c.get("/v1/secrets", headers={"X-API-Key": read_key}).status_code == 403
    admin_key = generate_api_key(db, owner="admin", scopes="read admin")
    db.add_secret("https://ex.com/x", "ex.com", "google_api_key", "AIza…wxyz",
                  "sha256:1", "ctx", "high")
    r = c.get("/v1/secrets", headers={"X-API-Key": admin_key})
    assert r.status_code == 200 and r.json()["count"] == 1


def test_hack_runs_requires_admin(client):
    c, db = client
    read_key = generate_api_key(db, owner="tester", scopes="read")
    assert c.get("/v1/hack/runs", headers={"X-API-Key": read_key}).status_code == 403
    admin_key = generate_api_key(db, owner="admin", scopes="read admin")
    rid = db.add_hack_run("https://ex.com", "recon", None, "admin")
    db.finish_hack_run(rid, status="completed", summary="1 finding",
                       findings=[{"severity": "low", "title": "Missing CSP"}])
    r = c.get("/v1/hack/runs", headers={"X-API-Key": admin_key})
    assert r.status_code == 200 and r.json()["count"] == 1
    assert r.json()["runs"][0]["findings_count"] == 1
    # single run
    r2 = c.get(f"/v1/hack/runs/{rid}", headers={"X-API-Key": admin_key})
    assert r2.status_code == 200 and r2.json()["engine"] == "recon"
