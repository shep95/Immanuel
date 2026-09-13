from immanuel.crawler.secrets import scan_secrets

# Test fixtures are assembled from fragments so the raw file never contains a
# contiguous vendor-format token (avoids provider push-protection false hits).
# scan_secrets still receives the full assembled string at runtime.
_AWS = "AKIA" + "IOSFODNN7EXAMPLE"
_GOOGLE = "AIza" + "abcdefghijklmnopqrstuvwxyz012345678"
_STRIPE = "sk_" + "live_" + "abcdEFGH1234ijklMNOP5678"
_GITHUB = "ghp_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def test_detects_common_keys():
    text = f"config: {_AWS} plus google {_GOOGLE} and stripe {_STRIPE} token"
    found = {s.secret_type for s in scan_secrets(text)}
    assert "aws_access_key_id" in found
    assert "google_api_key" in found
    assert "stripe_secret_key" in found


def test_masks_and_never_returns_raw():
    raw = _STRIPE
    out = scan_secrets(f"key={raw}")
    assert out
    for s in out:
        assert raw not in s.masked
        assert raw not in s.context
        assert s.fingerprint.startswith("sha256:")


def test_ignores_placeholders():
    text = 'api_key = "your_api_key_here_placeholder"'
    assert scan_secrets(text) == []


def test_generic_assignment_needs_entropy():
    # low-entropy value should be rejected by the generic rule
    assert scan_secrets('api_key = "aaaaaaaaaaaaaaaa"') == []
    high = 'api_key = "aZ9xQ2wE7rT4yU1pL8kM3nB6vC5s"'
    assert any(s.secret_type == "generic_api_key_assignment" for s in scan_secrets(high))


def test_deterministic():
    text = _GITHUB
    assert [s.as_dict() for s in scan_secrets(text)] == \
           [s.as_dict() for s in scan_secrets(text)]
