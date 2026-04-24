from __future__ import annotations

import os
import sqlite3
from pathlib import Path


DEFAULT_DB_PATH = Path("data/memory.sqlite")


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS raw_events (
  id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  scope_type TEXT NOT NULL,
  scope_id TEXT NOT NULL,
  sender_id TEXT,
  event_time INTEGER NOT NULL,
  content TEXT NOT NULL,
  raw_json TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY,
  scope_type TEXT NOT NULL,
  scope_id TEXT NOT NULL,
  type TEXT NOT NULL,
  subject TEXT NOT NULL,
  normalized_subject TEXT NOT NULL,
  current_value TEXT NOT NULL,
  reason TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  confidence REAL NOT NULL DEFAULT 0.5,
  importance REAL NOT NULL DEFAULT 0.5,
  source_event_id TEXT,
  active_version_id TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  expires_at INTEGER,
  last_recalled_at INTEGER,
  recall_count INTEGER NOT NULL DEFAULT 0,
  UNIQUE(scope_type, scope_id, type, normalized_subject)
);

CREATE TABLE IF NOT EXISTS memory_versions (
  id TEXT PRIMARY KEY,
  memory_id TEXT NOT NULL,
  version_no INTEGER NOT NULL,
  value TEXT NOT NULL,
  reason TEXT,
  status TEXT NOT NULL,
  source_event_id TEXT,
  created_by TEXT,
  created_at INTEGER NOT NULL,
  supersedes_version_id TEXT,
  FOREIGN KEY(memory_id) REFERENCES memories(id)
);

CREATE TABLE IF NOT EXISTS memory_evidence (
  id TEXT PRIMARY KEY,
  memory_id TEXT NOT NULL,
  version_id TEXT,
  source_type TEXT NOT NULL,
  source_url TEXT,
  source_event_id TEXT,
  quote TEXT,
  created_at INTEGER NOT NULL,
  FOREIGN KEY(memory_id) REFERENCES memories(id)
);

CREATE INDEX IF NOT EXISTS idx_raw_events_scope_time
  ON raw_events(scope_type, scope_id, event_time);

CREATE INDEX IF NOT EXISTS idx_memories_scope_status
  ON memories(scope_type, scope_id, status);

CREATE INDEX IF NOT EXISTS idx_memories_subject
  ON memories(scope_type, scope_id, type, normalized_subject);

CREATE INDEX IF NOT EXISTS idx_versions_memory_status
  ON memory_versions(memory_id, status);
"""


def db_path_from_env() -> Path:
    return Path(os.environ.get("MEMORY_DB_PATH", str(DEFAULT_DB_PATH)))


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else db_path_from_env()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()

