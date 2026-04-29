from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path("data/memory.sqlite")
DEFAULT_TENANT_ID = "tenant:demo"
DEFAULT_ORGANIZATION_ID = "org:demo"
DEFAULT_VISIBILITY_POLICY = "team"
SCHEMA_VERSION = 3


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS raw_events (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'tenant:demo',
  organization_id TEXT NOT NULL DEFAULT 'org:demo',
  workspace_id TEXT,
  visibility_policy TEXT NOT NULL DEFAULT 'team',
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_url TEXT,
  source_deleted_at INTEGER,
  ingestion_status TEXT NOT NULL DEFAULT 'raw',
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
  tenant_id TEXT NOT NULL DEFAULT 'tenant:demo',
  organization_id TEXT NOT NULL DEFAULT 'org:demo',
  workspace_id TEXT,
  visibility_policy TEXT NOT NULL DEFAULT 'team',
  scope_type TEXT NOT NULL,
  scope_id TEXT NOT NULL,
  type TEXT NOT NULL,
  subject TEXT NOT NULL,
  normalized_subject TEXT NOT NULL,
  current_value TEXT NOT NULL,
  summary TEXT,
  reason TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  confidence REAL NOT NULL DEFAULT 0.5,
  importance REAL NOT NULL DEFAULT 0.5,
  owner_id TEXT,
  created_by TEXT,
  updated_by TEXT,
  schema_version INTEGER NOT NULL DEFAULT 3,
  source_event_id TEXT,
  active_version_id TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  expires_at INTEGER,
  last_recalled_at INTEGER,
  recall_count INTEGER NOT NULL DEFAULT 0,
  source_visibility_revoked_at INTEGER,
  UNIQUE(scope_type, scope_id, type, normalized_subject)
);

CREATE TABLE IF NOT EXISTS memory_versions (
  id TEXT PRIMARY KEY,
  memory_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT 'tenant:demo',
  organization_id TEXT NOT NULL DEFAULT 'org:demo',
  visibility_policy TEXT NOT NULL DEFAULT 'team',
  version_no INTEGER NOT NULL,
  value TEXT NOT NULL,
  reason TEXT,
  decision_reason TEXT,
  status TEXT NOT NULL,
  source_event_id TEXT,
  created_by TEXT,
  created_at INTEGER NOT NULL,
  supersedes_version_id TEXT,
  permission_snapshot TEXT,
  FOREIGN KEY(memory_id) REFERENCES memories(id)
);

CREATE TABLE IF NOT EXISTS memory_evidence (
  id TEXT PRIMARY KEY,
  memory_id TEXT NOT NULL,
  version_id TEXT,
  tenant_id TEXT NOT NULL DEFAULT 'tenant:demo',
  organization_id TEXT NOT NULL DEFAULT 'org:demo',
  visibility_policy TEXT NOT NULL DEFAULT 'team',
  source_type TEXT NOT NULL,
  source_url TEXT,
  source_event_id TEXT,
  quote TEXT,
  actor_id TEXT,
  actor_display TEXT,
  event_time INTEGER,
  ingested_at INTEGER NOT NULL DEFAULT 0,
  source_deleted_at INTEGER,
  redaction_state TEXT NOT NULL DEFAULT 'none',
  created_at INTEGER NOT NULL,
  FOREIGN KEY(memory_id) REFERENCES memories(id)
);

CREATE TABLE IF NOT EXISTS memory_audit_events (
  audit_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  action TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT,
  memory_id TEXT,
  candidate_id TEXT,
  actor_id TEXT NOT NULL,
  actor_roles TEXT NOT NULL DEFAULT '[]',
  tenant_id TEXT NOT NULL DEFAULT 'tenant:demo',
  organization_id TEXT NOT NULL DEFAULT 'org:demo',
  scope TEXT,
  permission_decision TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  request_id TEXT NOT NULL,
  trace_id TEXT NOT NULL,
  visible_fields TEXT NOT NULL DEFAULT '[]',
  redacted_fields TEXT NOT NULL DEFAULT '[]',
  source_context TEXT NOT NULL DEFAULT '{}',
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_graph_nodes (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'tenant:demo',
  organization_id TEXT NOT NULL DEFAULT 'org:demo',
  node_type TEXT NOT NULL,
  node_key TEXT NOT NULL,
  label TEXT NOT NULL,
  visibility_policy TEXT NOT NULL DEFAULT 'team',
  status TEXT NOT NULL DEFAULT 'active',
  metadata_json TEXT NOT NULL DEFAULT '{}',
  first_seen_at INTEGER NOT NULL,
  last_seen_at INTEGER NOT NULL,
  observation_count INTEGER NOT NULL DEFAULT 1,
  UNIQUE(tenant_id, organization_id, node_type, node_key)
);

CREATE TABLE IF NOT EXISTS knowledge_graph_edges (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL DEFAULT 'tenant:demo',
  organization_id TEXT NOT NULL DEFAULT 'org:demo',
  source_node_id TEXT NOT NULL,
  target_node_id TEXT NOT NULL,
  edge_type TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  first_seen_at INTEGER NOT NULL,
  last_seen_at INTEGER NOT NULL,
  observation_count INTEGER NOT NULL DEFAULT 1,
  UNIQUE(tenant_id, organization_id, source_node_id, target_node_id, edge_type),
  FOREIGN KEY(source_node_id) REFERENCES knowledge_graph_nodes(id),
  FOREIGN KEY(target_node_id) REFERENCES knowledge_graph_nodes(id)
);

CREATE INDEX IF NOT EXISTS idx_raw_events_scope_time
  ON raw_events(scope_type, scope_id, event_time);

CREATE INDEX IF NOT EXISTS idx_raw_events_source
  ON raw_events(source_type, source_id);

CREATE INDEX IF NOT EXISTS idx_memories_scope_status
  ON memories(scope_type, scope_id, status);

CREATE INDEX IF NOT EXISTS idx_memories_subject
  ON memories(scope_type, scope_id, type, normalized_subject);

CREATE INDEX IF NOT EXISTS idx_versions_memory_status
  ON memory_versions(memory_id, status);

CREATE INDEX IF NOT EXISTS idx_kg_nodes_tenant_org_type_key
  ON knowledge_graph_nodes(tenant_id, organization_id, node_type, node_key);

CREATE INDEX IF NOT EXISTS idx_kg_edges_tenant_org_type
  ON knowledge_graph_edges(tenant_id, organization_id, edge_type);
"""


MIGRATIONS: dict[str, list[tuple[str, str]]] = {
    "raw_events": [
        ("tenant_id", "TEXT NOT NULL DEFAULT 'tenant:demo'"),
        ("organization_id", "TEXT NOT NULL DEFAULT 'org:demo'"),
        ("workspace_id", "TEXT"),
        ("visibility_policy", "TEXT NOT NULL DEFAULT 'team'"),
        ("source_url", "TEXT"),
        ("source_deleted_at", "INTEGER"),
        ("ingestion_status", "TEXT NOT NULL DEFAULT 'raw'"),
    ],
    "memories": [
        ("tenant_id", "TEXT NOT NULL DEFAULT 'tenant:demo'"),
        ("organization_id", "TEXT NOT NULL DEFAULT 'org:demo'"),
        ("workspace_id", "TEXT"),
        ("visibility_policy", "TEXT NOT NULL DEFAULT 'team'"),
        ("summary", "TEXT"),
        ("owner_id", "TEXT"),
        ("created_by", "TEXT"),
        ("updated_by", "TEXT"),
        ("schema_version", "INTEGER NOT NULL DEFAULT 3"),
        ("source_visibility_revoked_at", "INTEGER"),
    ],
    "memory_versions": [
        ("tenant_id", "TEXT NOT NULL DEFAULT 'tenant:demo'"),
        ("organization_id", "TEXT NOT NULL DEFAULT 'org:demo'"),
        ("visibility_policy", "TEXT NOT NULL DEFAULT 'team'"),
        ("decision_reason", "TEXT"),
        ("permission_snapshot", "TEXT"),
    ],
    "memory_evidence": [
        ("tenant_id", "TEXT NOT NULL DEFAULT 'tenant:demo'"),
        ("organization_id", "TEXT NOT NULL DEFAULT 'org:demo'"),
        ("visibility_policy", "TEXT NOT NULL DEFAULT 'team'"),
        ("actor_id", "TEXT"),
        ("actor_display", "TEXT"),
        ("event_time", "INTEGER"),
        ("ingested_at", "INTEGER NOT NULL DEFAULT 0"),
        ("source_deleted_at", "INTEGER"),
        ("redaction_state", "TEXT NOT NULL DEFAULT 'none'"),
    ],
}


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
    _migrate_existing_tables(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def _migrate_existing_tables(conn: sqlite3.Connection) -> None:
    for table, columns in MIGRATIONS.items():
        existing = _columns(conn, table)
        for name, definition in columns:
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        _backfill_table_defaults(conn, table)
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_memories_tenant_org_scope_status
          ON memories(tenant_id, organization_id, scope_type, scope_id, status);

        CREATE INDEX IF NOT EXISTS idx_memories_visibility_status
          ON memories(tenant_id, organization_id, visibility_policy, status);

        CREATE INDEX IF NOT EXISTS idx_evidence_source
          ON memory_evidence(tenant_id, organization_id, source_type, source_event_id);

        CREATE INDEX IF NOT EXISTS idx_audit_request_trace
          ON memory_audit_events(request_id, trace_id);
        """
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"] if isinstance(row, sqlite3.Row) else row[1]) for row in rows}


def _backfill_table_defaults(conn: sqlite3.Connection, table: str) -> None:
    existing = _columns(conn, table)
    if "tenant_id" in existing:
        conn.execute(
            f"UPDATE {table} SET tenant_id = ? WHERE tenant_id IS NULL OR tenant_id = ''",
            (DEFAULT_TENANT_ID,),
        )
    if "organization_id" in existing:
        conn.execute(
            f"UPDATE {table} SET organization_id = ? WHERE organization_id IS NULL OR organization_id = ''",
            (DEFAULT_ORGANIZATION_ID,),
        )
    if "visibility_policy" in existing:
        conn.execute(
            f"UPDATE {table} SET visibility_policy = ? WHERE visibility_policy IS NULL OR visibility_policy = ''",
            (DEFAULT_VISIBILITY_POLICY,),
        )
    if "schema_version" in existing:
        conn.execute(
            f"UPDATE {table} SET schema_version = ? WHERE schema_version IS NULL OR schema_version < ?",
            (SCHEMA_VERSION, SCHEMA_VERSION),
        )
    if "ingestion_status" in existing:
        conn.execute(
            f"UPDATE {table} SET ingestion_status = 'raw' WHERE ingestion_status IS NULL OR ingestion_status = ''"
        )
    if "ingested_at" in existing and "created_at" in existing:
        conn.execute(f"UPDATE {table} SET ingested_at = created_at WHERE ingested_at IS NULL OR ingested_at = 0")
    if "redaction_state" in existing:
        conn.execute(
            f"UPDATE {table} SET redaction_state = 'none' WHERE redaction_state IS NULL OR redaction_state = ''"
        )
