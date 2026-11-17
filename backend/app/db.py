"""SQLite database wrapper. Everything the app remembers lives in one local file."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenarios (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    slug       TEXT UNIQUE,
    name       TEXT NOT NULL,
    mode       TEXT NOT NULL,
    data       TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    title             TEXT NOT NULL DEFAULT '',
    scenario_id       INTEGER REFERENCES scenarios(id) ON DELETE SET NULL,
    scenario_snapshot TEXT NOT NULL DEFAULT '{}',
    summary           TEXT NOT NULL DEFAULT '',
    summary_upto      INTEGER NOT NULL DEFAULT 0,
    pinned_memory     TEXT NOT NULL DEFAULT '',
    created_at        REAL NOT NULL,
    updated_at        REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,
    content         TEXT NOT NULL,
    meta            TEXT NOT NULL DEFAULT '{}',
    created_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS npcs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    personality     TEXT NOT NULL DEFAULT '',
    speech_style    TEXT NOT NULL DEFAULT '',
    relationship    INTEGER NOT NULL DEFAULT 0,
    notes           TEXT NOT NULL DEFAULT '',
    active          INTEGER NOT NULL DEFAULT 1,
    is_main         INTEGER NOT NULL DEFAULT 0,
    created_at      REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_npc_name ON npcs(conversation_id, name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS game_state (
    conversation_id INTEGER PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
    data            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    message_id      INTEGER,
    text            TEXT NOT NULL,
    kind            TEXT NOT NULL DEFAULT 'event',
    importance      INTEGER NOT NULL DEFAULT 3,
    participants    TEXT NOT NULL DEFAULT '',
    embedding       BLOB,
    embed_model     TEXT,
    created_at      REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_conv ON memories(conversation_id);
CREATE INDEX IF NOT EXISTS idx_memories_msg ON memories(message_id);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    text, content='memories', content_rowid='id', tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE OF text ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO memories_fts(rowid, text) VALUES (new.id, new.text);
END;

CREATE TABLE IF NOT EXISTS skills_meta (
    name         TEXT PRIMARY KEY,
    enabled      INTEGER NOT NULL DEFAULT 1,
    source       TEXT NOT NULL DEFAULT '',
    installed_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_embeddings (
    name      TEXT PRIMARY KEY,
    hash      TEXT NOT NULL,
    model     TEXT NOT NULL,
    embedding BLOB NOT NULL
);
"""


class Database:
    """Thin, thread-safe wrapper around one SQLite connection."""

    def __init__(self, path: str | Path):
        path = str(path)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        # isolation_level=None -> autocommit; we open transactions explicitly.
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._depth = 0
        with self._lock:
            self.conn.execute("PRAGMA foreign_keys = ON")
            if path != ":memory:":
                self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.executescript(SCHEMA)
            self._migrate()

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        cols = {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def _migrate(self) -> None:
        """Bring databases created by older versions up to date (adds missing columns)."""
        self._ensure_column("conversations", "pinned_memory", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column("memories", "participants", "TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def transaction(self):
        with self._lock:
            if self._depth == 0:
                self.conn.execute("BEGIN")
            self._depth += 1
            try:
                yield
            except BaseException:
                self._depth -= 1
                if self._depth == 0:
                    self.conn.execute("ROLLBACK")
                raise
            else:
                self._depth -= 1
                if self._depth == 0:
                    self.conn.execute("COMMIT")

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.execute(sql, tuple(params))

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        with self._lock:
            cur = self.conn.execute(sql, tuple(params))
            return [dict(row) for row in cur.fetchall()]

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def close(self) -> None:
        with self._lock:
            self.conn.close()
