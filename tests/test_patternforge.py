import time

from immanuel.patternforge import forge
from immanuel.patternforge.skills import render_skills


def _seed(db, n, topic, category, company="Acme"):
    for i in range(n):
        db.add_item({
            "content_hash": f"sha256:{topic}-{category}-{i}",
            "url": f"https://acme.com/{topic}/{i}", "source_domain": "acme.com",
            "title": "t", "content": "c", "excerpt": "c", "media": [],
            "category": category, "category_confidence": 0.8, "signals": [],
            "epistemic_status": "observation", "collector": "live",
            "company": company, "topic": topic, "meta": {}, "code": [],
            "secrets_count": 0, "fetched_at": time.time(),
        })


def test_topic_category_pattern(db):
    _seed(db, 8, "security-cyber", "public_fact")
    _seed(db, 2, "security-cyber", "conspiracy")
    summary = forge.run_pass(db, min_evidence=3, min_confidence=0.5)
    assert summary["patterns_seen"] >= 1
    pats = db.list_patterns()
    tc = [p for p in pats if p["family"] == "topic_category"]
    assert tc and "security-cyber" in tc[0]["name"]
    # 8/10 dominant -> should reach validated at min_confidence 0.5
    assert tc[0]["status"] in ("validated", "active")


def test_lifecycle_starts_candidate(db):
    _seed(db, 2, "sports", "public_fact")   # below min_evidence
    forge.run_pass(db, min_evidence=3, min_confidence=0.6)
    pats = [p for p in db.list_patterns() if p["family"] == "topic_category"
            and "sports" in p["name"]]
    # only 2 observations -> stays candidate (not enough evidence)
    assert not pats or pats[0]["status"] == "candidate"


def test_secret_exposure_pattern(db):
    for i in range(3):
        db.add_secret(f"https://leak.com/{i}", "leak.com", "aws_access_key_id",
                      "AKIA…XMPL", f"sha256:{i}", "ctx", "high")
    forge.run_pass(db, min_evidence=2, min_confidence=0.5)
    se = [p for p in db.list_patterns() if p["family"] == "secret_exposure"]
    assert se and se[0]["domain"] == "security"


def test_skills_export_renders(db):
    _seed(db, 5, "ai-ml", "public_fact")
    forge.run_pass(db)
    text = render_skills(db)
    assert "Pattern Forge skill export" in text
    assert "SKILL:" in text


def test_pass_is_idempotent_on_ids(db):
    _seed(db, 6, "technology", "public_fact")
    forge.run_pass(db)
    n1 = db.count_patterns()
    forge.run_pass(db)
    n2 = db.count_patterns()
    assert n1 == n2  # stable ids -> update, not duplicate
