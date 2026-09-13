"""API key generation and verification.

A key looks like:  imk_<prefix>_<secret>
Only the sha256 of the full key is stored (plus the public prefix for lookup),
so the raw key is shown to the user exactly once.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from .db import Database

PREFIX_BYTES = 6
SECRET_BYTES = 24


def _hash(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key(db: Database, owner: str | None, scopes: str = "read") -> str:
    """Create and store a new key; return the raw key (shown once)."""
    prefix = secrets.token_hex(PREFIX_BYTES)
    secret = secrets.token_urlsafe(SECRET_BYTES)
    raw_key = f"imk_{prefix}_{secret}"
    db.store_api_key(prefix, _hash(raw_key), owner, scopes)
    return raw_key


def verify_api_key(db: Database, raw_key: str | None) -> dict | None:
    """Return the key record if valid+active, else None. Updates last_used."""
    if not raw_key or not raw_key.startswith("imk_"):
        return None
    parts = raw_key.split("_", 2)
    if len(parts) != 3:
        return None
    _, prefix, _secret = parts
    rec = db.get_api_key_by_prefix(prefix)
    if not rec:
        return None
    if not hmac.compare_digest(rec["key_hash"], _hash(raw_key)):
        return None
    db.touch_api_key(prefix)
    return rec
