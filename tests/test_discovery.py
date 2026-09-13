from immanuel.crawler.discovery import (
    candidate_sources_for,
    expand_paths,
    expand_subdomains,
    registrable_domain,
)


def test_registrable_domain():
    assert registrable_domain("www.example.com") == "example.com"
    assert registrable_domain("blog.example.com") == "example.com"
    assert registrable_domain("a.b.example.co.uk") == "example.co.uk"
    assert registrable_domain("example.com") == "example.com"


def test_expand_subdomains():
    urls = expand_subdomains("example.com")
    assert "https://example.com/" in urls
    assert "https://www.example.com/" in urls
    assert "https://blog.example.com/" in urls
    assert "https://api.example.com/" in urls
    # no duplicates
    assert len(urls) == len(set(urls))


def test_expand_paths():
    paths = expand_paths("https://example.com/some/page")
    assert "https://example.com/" in paths
    assert "https://example.com/sitemap.xml" in paths


def test_candidate_sources_for():
    cands = candidate_sources_for("https://example.com/x")
    assert any("blog.example.com" in c for c in cands)
    assert any(c.endswith("/feed") for c in cands)
    assert len(cands) == len(set(cands))
