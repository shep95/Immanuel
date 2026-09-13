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
    fetched_at      REAL NOT NULL,
    created_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_items_domain ON items(source_domain);
CREATE INDEX IF NOT EXISTS idx_items_fetched ON items(fetched_at);

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
"""


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
            self._conn.commit()

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
                     epistemic_status, timeline_ts, collector, fetched_at, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        clauses, params = [], []
        if query:
            clauses.append("(title LIKE ? OR content LIKE ?)")
            params += [f"%{query}%", f"%{query}%"]
        if category:
            clauses.append("category = ?")
            params.append(category)
        if domain:
            clauses.append("source_domain = ?")
            params.append(domain)
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
