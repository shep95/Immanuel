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


def test_masks_and_never_returns_raw_by_default():
    raw = _STRIPE
    out = scan_secrets(f"key={raw}")
    assert out
    for s in out:
        assert raw not in s.masked
        assert raw not in s.context
        assert s.raw is None                       # default: no uncensored value
        assert "raw" not in s.as_dict()            # not exposed unless requested
        assert s.fingerprint.startswith("sha256:")


def test_keep_raw_exposes_uncensored_value_only_when_asked():
    raw = _STRIPE
    out = scan_secrets(f"key={raw}", keep_raw=True)
    assert out
    s = out[0]
    assert s.raw == raw                            # uncensored kept
    # context stays masked even when uncensored is on
    assert raw not in s.context
    d = s.as_dict(include_raw=True)
    assert d["raw"] == raw
    assert d["provider"] == "Stripe"
    assert "payments" in d["unlocks"]
    # without include_raw the value is still withheld
    assert "raw" not in s.as_dict()


def test_provider_info_maps_key_to_data():
    out = scan_secrets(f"config: {_AWS}")
    assert out[0].provider == "AWS"
    assert "s3" in out[0].unlocks


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
