from immanuel.organize import company_for, slugify, topic_for


def test_company_from_domain():
    assert company_for("https://www.bbc.co.uk/news") == "Bbc"
    assert company_for("https://openai.com/blog") == "Openai"


def test_company_prefers_site_name():
    c = company_for("https://x.example.com/a", {"og:site_name": "Acme Corp"})
    assert c == "Acme Corp"


def test_topic_scoring():
    topic, hits = topic_for("New ransomware breach hits hospital",
                            "attackers used an exploit and phishing")
    assert topic == "security-cyber"
    assert hits


def test_topic_default_general():
    topic, hits = topic_for("hello", "nothing in particular here")
    assert topic == "general"


def test_slugify():
    assert slugify("Health & Medicine!") == "health-medicine"
    assert slugify("") == "misc"
