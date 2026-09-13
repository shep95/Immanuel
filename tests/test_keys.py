from immanuel.keys import generate_api_key, verify_api_key


def test_generate_and_verify(db):
    raw = generate_api_key(db, owner="tester")
    assert raw.startswith("imk_")
    rec = verify_api_key(db, raw)
    assert rec is not None and rec["owner"] == "tester"


def test_wrong_key_rejected(db):
    generate_api_key(db, owner="tester")
    assert verify_api_key(db, "imk_deadbeef_wrongsecret") is None
    assert verify_api_key(db, None) is None
    assert verify_api_key(db, "not-a-key") is None


def test_revoked_key_rejected(db):
    raw = generate_api_key(db, owner="tester")
    prefix = raw.split("_")[1]
    assert db.revoke_api_key(prefix) is True
    assert verify_api_key(db, raw) is None


def test_tampered_secret_rejected(db):
    raw = generate_api_key(db, owner="tester")
    tampered = raw[:-1] + ("A" if raw[-1] != "A" else "B")
    assert verify_api_key(db, tampered) is None
