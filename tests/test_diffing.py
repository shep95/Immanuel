from immanuel.crawler.diffing import compute_diff


def test_no_change():
    d = compute_diff("line a\nline b", "line a\nline b")
    assert not d.changed
    assert d.summary == "no textual change"


def test_added_lines():
    d = compute_diff("line a", "line a\nline b\nline c")
    assert d.changed
    assert d.added_lines == 2
    assert "line b" in d.added_text and "line c" in d.added_text
    assert "+2 lines" in d.summary


def test_removed_lines():
    d = compute_diff("a\nb\nc", "a")
    assert d.removed_lines == 2
    assert "-2 lines" in d.summary


def test_replace_counts_both():
    d = compute_diff("old headline\nbody", "new headline\nbody")
    assert d.added_lines >= 1 and d.removed_lines >= 1
    assert "new headline" in d.added_text
