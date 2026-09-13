from immanuel.media.filetypes import classify_media, is_file_link


def test_classify_by_extension():
    assert classify_media("https://x.com/a/pic.PNG") == "image"
    assert classify_media("https://x.com/song.mp3") == "audio"
    assert classify_media("https://x.com/clip.mp4") == "video"
    assert classify_media("https://x.com/report.pdf") == "document"
    assert classify_media("https://x.com/docs.docx") == "document"
    assert classify_media("https://x.com/bundle.zip") == "archive"
    assert classify_media("https://x.com/data.tar.gz") == "archive"


def test_classify_by_content_type_when_no_ext():
    assert classify_media("https://x.com/download?id=5",
                          content_type="application/pdf") == "document"
    assert classify_media("https://x.com/dl", content_type="image/png") == "image"
    assert classify_media("https://x.com/dl", content_type="application/zip") == "archive"


def test_declared_hint_and_other():
    assert classify_media("https://x.com/stream", declared="video") == "video"
    assert classify_media("https://x.com/page") == "other"


def test_is_file_link():
    assert is_file_link("https://x.com/a.pdf") is True
    assert is_file_link("https://x.com/a.zip") is True
    assert is_file_link("https://x.com/some/page") is False
    assert is_file_link("https://x.com/") is False
