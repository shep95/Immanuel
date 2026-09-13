from immanuel.crawler.extract import extract

HTML = b"""<!doctype html><html><head><title>Hello World</title>
<meta property="article:published_time" content="2020-01-02T00:00:00Z"></head>
<body><h1>Header</h1><p>Some visible text about science.</p>
<a href="/next">next</a><a href="https://other.com/z">z</a>
<img src="/pic.png"><script>ignore()</script></body></html>"""


def test_extract_html():
    ex = extract("https://ex.com/page", "text/html", HTML)
    assert ex.kind == "html"
    assert ex.title == "Hello World"
    assert "visible text about science" in ex.text
    assert "ignore()" not in ex.text
    assert "https://ex.com/next" in ex.links
    assert "https://other.com/z" in ex.links
    assert any(m["type"] == "image" for m in ex.media)
    assert ex.timeline_ts == "2020-01-02T00:00:00Z"


def test_content_hash_stable():
    a = extract("https://ex.com/page", "text/html", HTML)
    b = extract("https://ex.com/page", "text/html", HTML)
    assert a.content_hash == b.content_hash
    assert a.content_hash.startswith("sha256:")


def test_extract_json():
    ex = extract("https://ex.com/data.json", "application/json", b'{"a": 1, "b": [2,3]}')
    assert ex.kind == "json"
    assert '"a": 1' in ex.text


def test_extract_media_binary():
    ex = extract("https://ex.com/video.mp4", "video/mp4", b"\x00\x01\x02")
    assert ex.kind == "media"
    assert ex.media[0]["type"] == "video"


def test_extract_plaintext():
    ex = extract("https://ex.com/readme.txt", "text/plain", b"just text")
    assert ex.kind == "text"
    assert ex.text == "just text"


META_HTML = b"""<!doctype html><html lang="fr"><head>
<title>Page</title>
<meta name="description" content="a description">
<meta property="og:site_name" content="Example Site">
<meta property="og:image" content="https://ex.com/og.png">
<link rel="stylesheet" href="/style.css">
<link rel="canonical" href="https://ex.com/canon">
<script src="/app.js"></script>
<script type="application/ld+json">{"@type":"Article"}</script>
<script>var inline = 1;</script>
</head><body><img src="/a.png" srcset="/a-2x.png 2x"><p>body</p></body></html>"""


def test_extract_metadata_and_code():
    ex = extract("https://ex.com/p", "text/html", META_HTML)
    assert ex.lang == "fr"
    assert ex.meta.get("description") == "a description"
    assert ex.meta.get("og:site_name") == "Example Site"
    assert ex.meta.get("canonical") == "https://ex.com/canon"
    types = {c["type"] for c in ex.code}
    assert {"js", "css", "json-ld", "inline-js"} <= types
    # og:image + img + srcset all captured as media
    media_urls = {m["url"] for m in ex.media}
    assert "https://ex.com/og.png" in media_urls
    assert "https://ex.com/a.png" in media_urls
    assert "https://ex.com/a-2x.png" in media_urls
