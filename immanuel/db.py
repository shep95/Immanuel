"""SQLite storage layer.

Synchronous and thread-safe (a single connection guarded by a lock). Async
callers should wrap calls in ``asyncio.to_thread``. FastAPI sync endpoints and
tests call these methods directly.

Design invariants (from the spec):
- Raw content is content-addressed (sha256) and deduplicated at insert (L1).
- Every stored item keeps provenance (source url, domain, fetch time) and an
  epistemic classification (category + confidence + the signals that fired).
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash    TEXT UNIQUE NOT NULL,
    url             TEXT NOT NULL,
    source_domain   TEXT,
    title           TEXT,
    content         TEXT,
    excerpt         TEXT,
    media_json      TEXT,           -- list of {type,url,...}
    category        TEXT,           -- public_fact|public_rumor|private_fact|private_rumor|conspiracy|unknown
    category_confidence REAL,
    signals_json    TEXT,
    epistemic_status TEXT,
    timeline_ts     TEXT,           -- original publication / capture time (ISO) if known
    collector       TEXT,           -- live|wayback
    company         TEXT,           -- registrable entity / brand the page belongs to
    topic           TEXT,           -- deterministic topic bucket
    meta_json       TEXT,           -- full page metadata (meta tags, og, headers)
    code_json       TEXT,           -- code assets found on the page (js/css/json/inline)
    secrets_count   INTEGER DEFAULT 0,
    lang            TEXT,           -- declared content language, if any
    fetched_at      REAL NOT NULL,
    created_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_items_domain ON items(source_domain);
CREATE INDEX IF NOT EXISTS idx_items_fetched ON items(fetched_at);
CREATE INDEX IF NOT EXISTS idx_items_company ON items(company);
CREATE INDEX IF NOT EXISTS idx_items_topic ON items(topic);

CREATE TABLE IF NOT EXISTS page_versions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url           TEXT NOT NULL,
    version_no    INTEGER NOT NULL,
    content_hash  TEXT NOT NULL,
    title         TEXT,
    excerpt       TEXT,
    diff_summary  TEXT,           -- e.g. "+12 lines, -3 lines"
    added_text    TEXT,           -- the NEW data that appeared in this version
    removed_text  TEXT,           -- data that disappeared
    changed_chars INTEGER,
    timeline_ts   TEXT,           -- source-declared publish/update time if known
    fetched_at    REAL NOT NULL,  -- when Immanuel captured this version (timestamp)
    created_at    REAL NOT NULL,
    UNIQUE(url, version_no)
);
CREATE INDEX IF NOT EXISTS idx_versions_url ON page_versions(url);
CREATE INDEX IF NOT EXISTS idx_versions_fetched ON page_versions(fetched_at);

CREATE TABLE IF NOT EXISTS sources (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url          TEXT UNIQUE NOT NULL,
    domain       TEXT,
    kind         TEXT,              -- seed|discovered
    added_by     TEXT,
    added_at     REAL NOT NULL,
    last_crawled REAL,
    status       TEXT NOT NULL DEFAULT 'active',  -- active|paused|blocked|error
    failure_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sources_status ON sources(status);

CREATE TABLE IF NOT EXISTS api_keys (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    key_prefix  TEXT UNIQUE NOT NULL,
    key_hash    TEXT NOT NULL,
    owner       TEXT,
    scopes      TEXT,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  REAL NOT NULL,
    last_used   REAL
);

CREATE TABLE IF NOT EXISTS members_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id  TEXT,
    user_id   TEXT,
    username  TEXT,
    event     TEXT,                 -- join|leave
    at        REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT
);

-- Exposed secrets / API keys found on PUBLIC pages (admin-only surface).
-- Values are stored MASKED plus a sha256 fingerprint; the raw secret is never
-- persisted, so this is a safe "these credentials are publicly leaking" ledger.
CREATE TABLE IF NOT EXISTS secrets_found (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url           TEXT NOT NULL,
    domain        TEXT,
    secret_type   TEXT NOT NULL,
    masked        TEXT NOT NULL,
    fingerprint   TEXT NOT NULL,          -- sha256 of the raw match (dedup, never the secret)
    context       TEXT,
    severity      TEXT,
    found_at      REAL NOT NULL,
    UNIQUE(fingerprint, url)
);
CREATE INDEX IF NOT EXISTS idx_secrets_domain ON secrets_found(domain);
CREATE INDEX IF NOT EXISTS idx_secrets_type ON secrets_found(secret_type);

-- Per-page intel data-report (open metadata of media/files + link graph).
CREATE TABLE IF NOT EXISTS intel_reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url           TEXT NOT NULL,
    domain        TEXT,
    report_json   TEXT NOT NULL,
    media_count   INTEGER DEFAULT 0,
    secrets_count INTEGER DEFAULT 0,
    links_count   INTEGER DEFAULT 0,
    created_at    REAL NOT NULL,
    UNIQUE(url)
);
CREATE INDEX IF NOT EXISTS idx_intel_domain ON intel_reports(domain);

-- Pattern Forge library: patterns learned by the non-AI second algorithm.
CREATE TABLE IF NOT EXISTS patterns (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_id     TEXT UNIQUE NOT NULL,   -- stable deterministic id
    name           TEXT NOT NULL,
    domain         TEXT,
    family         TEXT,
    scope          TEXT,                   -- ephemeral|task|domain|system ...
    mechanism      TEXT,
    status         TEXT NOT NULL,          -- unknown|candidate|testing|validated|active|deprecated|retired
    confidence     REAL DEFAULT 0.0,
    evidence_count INTEGER DEFAULT 0,
    data_json      TEXT,                   -- full universal pattern object
    created_at     REAL NOT NULL,
    updated_at     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_patterns_status ON patterns(status);
CREATE INDEX IF NOT EXISTS idx_patterns_domain ON patterns(domain);

-- Conditional-GET cache so a restarted crawler does not re-download unchanged
-- pages (it "knows what it collected"): sends If-None-Match / If-Modified-Since.
CREATE TABLE IF NOT EXISTS http_cache (
    url           TEXT PRIMARY KEY,
    etag          TEXT,
    last_modified TEXT,
    content_hash  TEXT,
    updated_at    REAL NOT NULL
);

-- Downloaded media assets (content-addressed on disk).
CREATE TABLE IF NOT EXISTS media_assets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256        TEXT UNIQUE NOT NULL,
    source_url    TEXT NOT NULL,
    page_url      TEXT,
    media_type    TEXT,
    content_type  TEXT,
    bytes         INTEGER,
    stored_path   TEXT,
    meta_json     TEXT,                    -- open metadata (EXIF, dimensions, etc.)
    created_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_media_page ON media_assets(page_url);
"""

# Columns added after v0.1 — applied idempotently to already-created DBs.
_ITEM_MIGRATIONS = {
    "company": "ALTER TABLE items ADD COLUMN company TEXT",
    "topic": "ALTER TABLE items ADD COLUMN topic TEXT",
    "meta_json": "ALTER TABLE items ADD COLUMN meta_json TEXT",
    "code_json": "ALTER TABLE items ADD COLUMN code_json TEXT",
    "secrets_count": "ALTER TABLE items ADD COLUMN secrets_count INTEGER DEFAULT 0",
    "lang": "ALTER TABLE items ADD COLUMN lang TEXT",
}


class Database:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            parent = os.path.dirname(os.path.abspath(path))
            os.makedirs(parent, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self) -> None:
        """Add columns introduced after the first release (idempotent)."""
        cols = {r["name"] for r in self._conn.execute(
            "PRAGMA table_info(items)").fetchall()}
        for col, ddl in _ITEM_MIGRATIONS.items():
            if col not in cols:
                try:
                    self._conn.execute(ddl)
                except sqlite3.OperationalError:
                    pass

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ----------------------------------------------------------------- items
    def add_item(self, item: dict[str, Any]) -> int | None:
        """Insert an item; returns row id, or None if it was a duplicate (L1)."""
        now = time.time()
        with self._lock:
            try:
                cur = self._conn.execute(
                    """INSERT INTO items
                    (content_hash, url, source_domain, title, content, excerpt,
                     media_json, category, category_confidence, signals_json,
                     epistemic_status, timeline_ts, collector, company, topic,
                     meta_json, code_json, secrets_count, lang, fetched_at, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        item["content_hash"],
                        item["url"],
                        item.get("source_domain"),
                        item.get("title"),
                        item.get("content"),
                        item.get("excerpt"),
                        json.dumps(item.get("media", [])),
                        item.get("category"),
                        item.get("category_confidence"),
                        json.dumps(item.get("signals", [])),
                        item.get("epistemic_status"),
                        item.get("timeline_ts"),
                        item.get("collector", "live"),
                        item.get("company"),
                        item.get("topic"),
                        json.dumps(item.get("meta", {})),
                        json.dumps(item.get("code", [])),
                        item.get("secrets_count", 0),
                        item.get("lang"),
                        item.get("fetched_at", now),
                        now,
                    ),
                )
                self._conn.commit()
                return cur.lastrowid
            except sqlite3.IntegrityError:
                return None  # duplicate content_hash

    def item_exists(self, content_hash: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM items WHERE content_hash=? LIMIT 1", (content_hash,)
            ).fetchone()
            return row is not None

    def count_items(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

    def counts_by_category(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT category, COUNT(*) c FROM items GROUP BY category"
            ).fetchall()
        return {r["category"] or "unknown": r["c"] for r in rows}

    def search_items(
        self,
        query: str | None = None,
        category: str | None = None,
        domain: str | None = None,
        company: str | None = None,
        topic: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        clauses, params = [], []
        if query:
            clauses.append("(title LIKE ? OR content LIKE ? OR url LIKE ?)")
            params += [f"%{query}%", f"%{query}%", f"%{query}%"]
        if category:
            clauses.append("category = ?")
            params.append(category)
        if domain:
            clauses.append("source_domain = ?")
            params.append(domain)
        if company:
            clauses.append("company = ?")
            params.append(company)
        if topic:
            clauses.append("topic = ?")
            params.append(topic)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            f"SELECT * FROM items {where} ORDER BY fetched_at DESC LIMIT ? OFFSET ?"
        )
        params += [limit, offset]
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [self._item_row(r) for r in rows]

    def iter_all_items(self) -> Iterable[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM items ORDER BY id ASC"
            ).fetchall()
        for r in rows:
            yield self._item_row(r)

    @staticmethod
    def _item_row(r: sqlite3.Row) -> dict[str, Any]:
        d = dict(r)
        d["media"] = json.loads(d.pop("media_json") or "[]")
        d["signals"] = json.loads(d.pop("signals_json") or "[]")
        d["meta"] = json.loads(d.pop("meta_json", None) or "{}")
        d["code"] = json.loads(d.pop("code_json", None) or "[]")
        return d

    def get_item_content_by_hash(self, content_hash: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT content FROM items WHERE content_hash=? LIMIT 1",
                (content_hash,),
            ).fetchone()
        return row["content"] if row else None

    # ------------------------------------------------------- page_versions
    def get_latest_version(self, url: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM page_versions WHERE url=? "
                "ORDER BY version_no DESC LIMIT 1",
                (url,),
            ).fetchone()
        return dict(row) if row else None

    def add_page_version(self, url: str, version_no: int, content_hash: str,
                         title: str | None, excerpt: str | None,
                         diff_summary: str | None, added_text: str | None,
                         removed_text: str | None, changed_chars: int,
                         timeline_ts: str | None, fetched_at: float) -> int:
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO page_versions
                   (url, version_no, content_hash, title, excerpt, diff_summary,
                    added_text, removed_text, changed_chars, timeline_ts,
                    fetched_at, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (url, version_no, content_hash, title, excerpt, diff_summary,
                 added_text, removed_text, changed_chars, timeline_ts,
                 fetched_at, now),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_versions(self, url: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM page_versions WHERE url=? "
                "ORDER BY version_no ASC LIMIT ?",
                (url, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def url_timestamps(self, url: str) -> dict[str, Any]:
        """first_seen / last_seen / version count for a URL."""
        with self._lock:
            row = self._conn.execute(
                "SELECT MIN(fetched_at) first_seen, MAX(fetched_at) last_seen, "
                "COUNT(*) versions FROM page_versions WHERE url=?",
                (url,),
            ).fetchone()
        return dict(row) if row else {"first_seen": None, "last_seen": None, "versions": 0}

    def recent_updates(self, limit: int = 25) -> list[dict[str, Any]]:
        """Most recent page updates (version_no > 1), newest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM page_versions WHERE version_no > 1 "
                "ORDER BY fetched_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_versions(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM page_versions"
            ).fetchone()[0]

    def count_updates(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM page_versions WHERE version_no > 1"
            ).fetchone()[0]

    # --------------------------------------------------------------- sources
    def add_source(self, url: str, kind: str = "seed", added_by: str | None = None,
                   domain: str | None = None) -> bool:
        """Add a source; returns True if newly inserted, False if it existed."""
        now = time.time()
        with self._lock:
            try:
                self._conn.execute(
                    """INSERT INTO sources (url, domain, kind, added_by, added_at, status)
                       VALUES (?,?,?,?,?, 'active')""",
                    (url, domain, kind, added_by, now),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def list_sources(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            if status:
                rows = self._conn.execute(
                    "SELECT * FROM sources WHERE status=? ORDER BY id DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM sources ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(r) for r in rows]

    def due_sources(self, limit: int, min_interval_seconds: float) -> list[dict[str, Any]]:
        """Active sources never crawled or crawled longer ago than the interval."""
        cutoff = time.time() - min_interval_seconds
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM sources
                   WHERE status='active' AND (last_crawled IS NULL OR last_crawled < ?)
                   ORDER BY (last_crawled IS NULL) DESC, last_crawled ASC
                   LIMIT ?""",
                (cutoff, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_source_crawled(self, source_id: int, ok: bool = True) -> None:
        now = time.time()
        with self._lock:
            if ok:
                self._conn.execute(
                    "UPDATE sources SET last_crawled=?, failure_count=0 WHERE id=?",
                    (now, source_id),
                )
            else:
                self._conn.execute(
                    """UPDATE sources
                       SET last_crawled=?, failure_count=failure_count+1,
                           status=CASE WHEN failure_count+1 >= 5 THEN 'error' ELSE status END
                       WHERE id=?""",
                    (now, source_id),
                )
            self._conn.commit()

    def mark_url_crawled(self, url: str, ok: bool = True) -> None:
        now = time.time()
        with self._lock:
            if ok:
                self._conn.execute(
                    "UPDATE sources SET last_crawled=?, failure_count=0 WHERE url=?",
                    (now, url),
                )
            else:
                self._conn.execute(
                    "UPDATE sources SET last_crawled=?, failure_count=failure_count+1 "
                    "WHERE url=?",
                    (now, url),
                )
            self._conn.commit()

    def count_sources(self, status: str | None = None) -> int:
        with self._lock:
            if status:
                return self._conn.execute(
                    "SELECT COUNT(*) FROM sources WHERE status=?", (status,)
                ).fetchone()[0]
            return self._conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]

    def count_domains(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(DISTINCT domain) FROM sources WHERE domain IS NOT NULL"
            ).fetchone()[0]

    # -------------------------------------------------------------- api_keys
    def store_api_key(self, key_prefix: str, key_hash: str, owner: str | None,
                      scopes: str = "read") -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO api_keys (key_prefix, key_hash, owner, scopes, active, created_at)
                   VALUES (?,?,?,?,1,?)""",
                (key_prefix, key_hash, owner, scopes, now),
            )
            self._conn.commit()

    def get_api_key_by_prefix(self, key_prefix: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM api_keys WHERE key_prefix=? AND active=1", (key_prefix,)
            ).fetchone()
        return dict(row) if row else None

    def touch_api_key(self, key_prefix: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE api_keys SET last_used=? WHERE key_prefix=?",
                (time.time(), key_prefix),
            )
            self._conn.commit()

    def revoke_api_key(self, key_prefix: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE api_keys SET active=0 WHERE key_prefix=?", (key_prefix,)
            )
            self._conn.commit()
            return cur.rowcount > 0

    def list_api_keys(self, owner: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if owner:
                rows = self._conn.execute(
                    "SELECT key_prefix, owner, scopes, active, created_at, last_used "
                    "FROM api_keys WHERE owner=? ORDER BY id DESC",
                    (owner,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT key_prefix, owner, scopes, active, created_at, last_used "
                    "FROM api_keys ORDER BY id DESC"
                ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------ members_log
    def log_member_event(self, guild_id: str, user_id: str, username: str,
                         event: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO members_log (guild_id, user_id, username, event, at) "
                "VALUES (?,?,?,?,?)",
                (guild_id, user_id, username, event, time.time()),
            )
            self._conn.commit()

    def recent_member_events(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM members_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # -------------------------------------------------------------------- kv
    def set_state(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO kv (key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self._conn.commit()

    def get_state(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM kv WHERE key=?", (key,)
            ).fetchone()
        return row["value"] if row else default

    # ------------------------------------------------- companies / topics
    def list_companies(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT company, COUNT(*) c FROM items "
                "WHERE company IS NOT NULL AND company != '' "
                "GROUP BY company ORDER BY c DESC LIMIT ?", (limit,),
            ).fetchall()
        return [{"company": r["company"], "count": r["c"]} for r in rows]

    def list_topics(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT topic, COUNT(*) c FROM items "
                "WHERE topic IS NOT NULL AND topic != '' "
                "GROUP BY topic ORDER BY c DESC LIMIT ?", (limit,),
            ).fetchall()
        return [{"topic": r["topic"], "count": r["c"]} for r in rows]

    # --------------------------------------------------------- secrets_found
    def add_secret(self, url: str, domain: str | None, secret_type: str,
                   masked: str, fingerprint: str, context: str | None,
                   severity: str = "medium") -> bool:
        with self._lock:
            try:
                self._conn.execute(
                    """INSERT INTO secrets_found
                       (url, domain, secret_type, masked, fingerprint, context,
                        severity, found_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (url, domain, secret_type, masked, fingerprint,
                     (context or "")[:400], severity, time.time()),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def recent_secrets(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM secrets_found ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def count_secrets(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM secrets_found").fetchone()[0]

    # --------------------------------------------------------- intel_reports
    def upsert_intel_report(self, url: str, domain: str | None, report: dict[str, Any],
                            media_count: int, secrets_count: int,
                            links_count: int) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO intel_reports
                   (url, domain, report_json, media_count, secrets_count,
                    links_count, created_at)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(url) DO UPDATE SET
                     report_json=excluded.report_json,
                     media_count=excluded.media_count,
                     secrets_count=excluded.secrets_count,
                     links_count=excluded.links_count,
                     created_at=excluded.created_at""",
                (url, domain, json.dumps(report), media_count, secrets_count,
                 links_count, time.time()),
            )
            self._conn.commit()

    def get_intel_report(self, url: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM intel_reports WHERE url=?", (url,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["report"] = json.loads(d.pop("report_json") or "{}")
        return d

    def recent_intel(self, limit: int = 25) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT url, domain, media_count, secrets_count, links_count, "
                "created_at FROM intel_reports ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def count_intel(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM intel_reports").fetchone()[0]

    # -------------------------------------------------------------- patterns
    def upsert_pattern(self, p: dict[str, Any]) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO patterns
                   (pattern_id, name, domain, family, scope, mechanism, status,
                    confidence, evidence_count, data_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(pattern_id) DO UPDATE SET
                     name=excluded.name, domain=excluded.domain,
                     family=excluded.family, scope=excluded.scope,
                     mechanism=excluded.mechanism, status=excluded.status,
                     confidence=excluded.confidence,
                     evidence_count=excluded.evidence_count,
                     data_json=excluded.data_json, updated_at=excluded.updated_at""",
                (p["pattern_id"], p.get("name"), p.get("domain"), p.get("family"),
                 p.get("scope"), p.get("mechanism"), p.get("status", "candidate"),
                 float(p.get("confidence", 0.0)), int(p.get("evidence_count", 0)),
                 json.dumps(p.get("data", {})), now, now),
            )
            self._conn.commit()

    def get_pattern(self, pattern_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM patterns WHERE pattern_id=?", (pattern_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["data"] = json.loads(d.pop("data_json") or "{}")
        return d

    def list_patterns(self, status: str | None = None,
                      limit: int = 1000) -> list[dict[str, Any]]:
        with self._lock:
            if status:
                rows = self._conn.execute(
                    "SELECT * FROM patterns WHERE status=? "
                    "ORDER BY confidence DESC, evidence_count DESC LIMIT ?",
                    (status, limit)).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM patterns "
                    "ORDER BY confidence DESC, evidence_count DESC LIMIT ?",
                    (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["data"] = json.loads(d.pop("data_json") or "{}")
            out.append(d)
        return out

    def count_patterns(self, status: str | None = None) -> int:
        with self._lock:
            if status:
                return self._conn.execute(
                    "SELECT COUNT(*) FROM patterns WHERE status=?",
                    (status,)).fetchone()[0]
            return self._conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0]

    # ------------------------------------------------------------ http_cache
    def get_http_cache(self, url: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM http_cache WHERE url=?", (url,)
            ).fetchone()
        return dict(row) if row else None

    def set_http_cache(self, url: str, etag: str | None,
                       last_modified: str | None, content_hash: str | None) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO http_cache (url, etag, last_modified, content_hash, updated_at)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(url) DO UPDATE SET
                     etag=excluded.etag, last_modified=excluded.last_modified,
                     content_hash=excluded.content_hash, updated_at=excluded.updated_at""",
                (url, etag, last_modified, content_hash, time.time()),
            )
            self._conn.commit()

    # ---------------------------------------------------------- media_assets
    def add_media_asset(self, sha256: str, source_url: str, page_url: str | None,
                        media_type: str | None, content_type: str | None,
                        num_bytes: int, stored_path: str | None,
                        meta: dict[str, Any] | None) -> bool:
        with self._lock:
            try:
                self._conn.execute(
                    """INSERT INTO media_assets
                       (sha256, source_url, page_url, media_type, content_type,
                        bytes, stored_path, meta_json, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (sha256, source_url, page_url, media_type, content_type,
                     num_bytes, stored_path, json.dumps(meta or {}), time.time()),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    # ----------------------------------------------- pattern-forge aggregates
    def agg_topic_category(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT topic, category, COUNT(*) c FROM items "
                "WHERE topic IS NOT NULL GROUP BY topic, category"
            ).fetchall()
        return [dict(r) for r in rows]

    def agg_company_topic(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT company, topic, COUNT(*) c FROM items "
                "WHERE company IS NOT NULL AND topic IS NOT NULL "
                "GROUP BY company, topic"
            ).fetchall()
        return [dict(r) for r in rows]

    def agg_domain_items(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT source_domain domain, COUNT(*) c FROM items "
                "WHERE source_domain IS NOT NULL GROUP BY source_domain"
            ).fetchall()
        return [dict(r) for r in rows]

    def agg_secret_domains(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT domain, COUNT(*) c, COUNT(DISTINCT secret_type) types "
                "FROM secrets_found WHERE domain IS NOT NULL GROUP BY domain"
            ).fetchall()
        return [dict(r) for r in rows]

    def agg_url_versions(self, min_versions: int = 2,
                         limit: int = 5000) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT url, MAX(version_no) v FROM page_versions "
                "GROUP BY url HAVING v >= ? ORDER BY v DESC LIMIT ?",
                (min_versions, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def media_exists(self, sha256: str) -> bool:
        with self._lock:
            return self._conn.execute(
                "SELECT 1 FROM media_assets WHERE sha256=? LIMIT 1", (sha256,)
            ).fetchone() is not None

    def count_media_assets(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM media_assets").fetchone()[0]
