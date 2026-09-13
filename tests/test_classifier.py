from immanuel.classifier import CATEGORIES, classify


def test_public_fact():
    c = classify("Government officially announced new policy",
                 "The agency confirmed the data shows GDP growth. Published in the register.")
    assert c.category == "public_fact"
    assert c.confidence > 0.5
    assert any(s.startswith("fact:") for s in c.signals)


def test_public_rumor():
    c = classify("Company reportedly planning layoffs",
                 "Sources say the public company might cut jobs, according to speculation.")
    assert c.category == "public_rumor"
    assert any(s.startswith("rumor:") for s in c.signals)


def test_private_rumor():
    c = classify("Celebrity dating rumor",
                 "Insider says the star's personal life and relationship allegedly changed; leaked DMs.")
    assert c.category == "private_rumor"


def test_private_fact():
    c = classify("Leaked internal memo confirmed",
                 "The confidential internal memo was verified; the private personal record is documented.")
    assert c.category == "private_fact"


def test_conspiracy_overrides():
    c = classify("The truth they hide",
                 "This is a false flag cover-up by the deep state; wake up sheeple, it's a hoax.")
    assert c.category == "conspiracy"
    assert c.epistemic_status == "hypothesis"


def test_empty_is_unknown():
    c = classify("", "")
    assert c.category == "unknown"
    assert c.confidence == 0.0


def test_deterministic():
    a = classify("Study shows X", "According to data, confirmed result.")
    b = classify("Study shows X", "According to data, confirmed result.")
    assert a.category == b.category and a.confidence == b.confidence


def test_all_categories_reachable():
    assert set(CATEGORIES) == {
        "public_fact", "public_rumor", "private_fact", "private_rumor", "conspiracy",
    }
