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
