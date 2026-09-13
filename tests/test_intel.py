from immanuel.intel import build_intel_report


def test_build_report_counts():
    report, mc, sc, lc = build_intel_report(
        url="https://ex.com/p", title="t", category="public_fact",
        company="Ex", topic="technology", lang="en", meta={"description": "d"},
        links=["https://a.com/1", "https://b.com/2", "https://a.com/3"],
        media_refs=[{"type": "image", "url": "https://ex.com/i.png"}],
        media_assets=[{"media_type": "image", "source_url": "https://ex.com/i.png",
                       "bytes": 10, "content_type": "image/png",
                       "meta": {"width": 2, "height": 2, "has_gps": True}}],
        secrets=[{"type": "google_api_key", "masked": "AIza…vuvw", "severity": "high",
                  "fingerprint": "sha256:x"}],
        code=[{"type": "js", "url": "https://ex.com/app.js"}],
    )
    assert lc == 3
    assert sc == 1
    assert report["counts"]["linked_domains"] == 2
    assert report["counts"]["media_with_gps"] == 1
    # secrets in the report are masked only (no raw value fields)
    assert report["secrets_exposed"][0]["masked"] == "AIza…vuvw"
    assert "raw" not in report["secrets_exposed"][0]


def test_persist_and_fetch(db):
    report, mc, sc, lc = build_intel_report(
        url="https://ex.com/p", title="t", category=None, company=None,
        topic=None, lang=None, meta={}, links=[], media_refs=[],
        media_assets=[], secrets=[], code=[])
    db.upsert_intel_report("https://ex.com/p", "ex.com", report, mc, sc, lc)
    got = db.get_intel_report("https://ex.com/p")
    assert got and got["report"]["url"] == "https://ex.com/p"
    assert db.count_intel() == 1
