from __future__ import annotations

import sqlite3
from typing import Any

from .db import MIGRATIONS, SCHEMA_VERSION, init_db


TARGET_SCHEMA_VERSION = SCHEMA_VERSION
CORE_TABLES = ("raw_events", "memories", "memory_versions", "memory_evidence")
REQUIRED_TABLES = (*CORE_TABLES, "memory_audit_events")
REQUIRED_INDEXES = {
    "idx_memories_tenant_org_scope_status",
    "idx_memories_visibility_status",
    "idx_evidence_source",
    "idx_audit_request_trace",
}


def inspect_copilot_storage(conn: sqlite3.Connection) -> dict[str, Any]:
    """Inspect storage migration readiness without changing the database."""

    tables = _tables(conn)
    pending_column_additions: dict[str, list[str]] = {}
    rows_needing_defaults: dict[str, int] = {}
    for table, columns in MIGRATIONS.items():
        if table not in tables:
            continue
        existing = _columns(conn, table)
        missing = [name for name, _definition in columns if name not in existing]
        if missing:
            pending_column_additions[table] = missing
        rows_needing_defaults[table] = _count_rows_needing_defaults(conn, table, existing)

    missing_tables = [table for table in REQUIRED_TABLES if table not in tables]
    existing_indexes = _indexes(conn)
    missing_indexes = sorted(REQUIRED_INDEXES - existing_indexes)
    user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    ready = (
        user_version >= TARGET_SCHEMA_VERSION
        and not missing_tables
        and not pending_column_additions
        and not missing_indexes
        and all(count == 0 for count in rows_needing_defaults.values())
    )
    return {
        "ready": ready,
        "current_schema_version": user_version,
        "target_schema_version": TARGET_SCHEMA_VERSION,
        "tables": sorted(tables),
        "missing_tables": missing_tables,
        "pending_column_additions": pending_column_additions,
        "rows_needing_defaults": rows_needing_defaults,
        "audit": _audit_status(conn, tables),
        "indexes": {
            "required": sorted(REQUIRED_INDEXES),
            "available": sorted(REQUIRED_INDEXES & existing_indexes),
            "missing": missing_indexes,
        },
        "missing_indexes": missing_indexes,
        "rollback": rollback_plan(),
        "boundary": "本迁移入口只处理本地 SQLite 兼容迁移和上线试点前检查；不等于生产级多租户数据库部署。",
    }


def apply_copilot_storage_migration(conn: sqlite3.Connection) -> dict[str, Any]:
    before = inspect_copilot_storage(conn)
    init_db(conn)
    after = inspect_copilot_storage(conn)
    return {
        "applied": True,
        "ready": after["ready"],
        "before": before,
        "after": after,
        "rollback": rollback_plan(),
    }


def rollback_plan() -> dict[str, Any]:
    return {
        "destructive_rollback_supported": False,
        "safe_rollback": [
            "停止真实 Feishu ingestion / OpenClaw websocket 写入入口。",
            "用迁移前备份文件恢复 SQLite 数据库，或切回 seed/local demo 数据库。",
            "保留新增列和审计表；不要自动 DROP columns，以免破坏已写入审计证据。",
        ],
        "reason": "SQLite 兼容迁移只向前新增列、表和索引；自动回滚删除结构风险高。",
    }


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row["name"] if isinstance(row, sqlite3.Row) else row[0]) for row in rows}


def _indexes(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
    return {str(row["name"] if isinstance(row, sqlite3.Row) else row[0]) for row in rows}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"] if isinstance(row, sqlite3.Row) else row[1]) for row in rows}


def _count_rows_needing_defaults(conn: sqlite3.Connection, table: str, columns: set[str]) -> int:
    required_defaults = [column for column in ("tenant_id", "organization_id", "visibility_policy") if column in columns]
    if not required_defaults:
        try:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        except sqlite3.OperationalError:
            return 0
    predicates = " OR ".join(f"{column} IS NULL OR {column} = ''" for column in required_defaults)
    return int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {predicates}").fetchone()[0])


def _audit_status(conn: sqlite3.Connection, tables: set[str]) -> dict[str, Any]:
    if "memory_audit_events" not in tables:
        return {
            "available": False,
            "event_count": 0,
            "recent_failure_count": 0,
            "permission_deny_count": 0,
            "redaction_count": 0,
        }
    event_count = int(conn.execute("SELECT COUNT(*) FROM memory_audit_events").fetchone()[0])
    permission_deny_count = int(
        conn.execute("SELECT COUNT(*) FROM memory_audit_events WHERE permission_decision = 'deny'").fetchone()[0]
    )
    redaction_count = int(
        conn.execute(
            "SELECT COUNT(*) FROM memory_audit_events WHERE permission_decision IN ('redact', 'withhold')"
        ).fetchone()[0]
    )
    recent_failure_count = int(
        conn.execute(
            """
            SELECT COUNT(*) FROM memory_audit_events
            WHERE permission_decision = 'deny'
               OR reason_code LIKE '%failed%'
               OR reason_code LIKE '%error%'
            """
        ).fetchone()[0]
    )
    return {
        "available": True,
        "event_count": event_count,
        "recent_failure_count": recent_failure_count,
        "permission_deny_count": permission_deny_count,
        "redaction_count": redaction_count,
    }
