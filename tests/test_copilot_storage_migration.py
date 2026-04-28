from __future__ import annotations

import sqlite3
import unittest

from memory_engine.storage_migration import (
    TARGET_SCHEMA_VERSION,
    apply_copilot_storage_migration,
    inspect_copilot_storage,
)


class CopilotStorageMigrationTest(unittest.TestCase):
    def test_dry_run_reports_pending_work_without_mutating_legacy_db(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        self._create_legacy_db(conn)

        report = inspect_copilot_storage(conn)

        self.assertFalse(report["ready"])
        self.assertEqual(0, report["current_schema_version"])
        self.assertIn("tenant_id", report["pending_column_additions"]["memories"])
        self.assertIn("memory_audit_events", report["missing_tables"])
        self.assertIn("idx_memories_tenant_org_scope_status", report["missing_indexes"])
        self.assertEqual(1, report["rows_needing_defaults"]["memories"])
        self.assertNotIn("tenant_id", self._columns(conn, "memories"))
        self.assertFalse(report["rollback"]["destructive_rollback_supported"])

    def test_apply_is_idempotent_and_creates_productization_indexes(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        self.addCleanup(conn.close)
        self._create_legacy_db(conn)

        first = apply_copilot_storage_migration(conn)
        second = apply_copilot_storage_migration(conn)
        after = inspect_copilot_storage(conn)

        self.assertTrue(first["applied"])
        self.assertTrue(second["applied"])
        self.assertTrue(after["ready"])
        self.assertEqual(TARGET_SCHEMA_VERSION, after["current_schema_version"])
        self.assertEqual({}, after["pending_column_additions"])
        self.assertEqual([], after["missing_indexes"])
        self.assertEqual("tenant:demo", conn.execute("SELECT tenant_id FROM memories").fetchone()[0])
        self.assertEqual(TARGET_SCHEMA_VERSION, conn.execute("PRAGMA user_version").fetchone()[0])

    def _create_legacy_db(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE raw_events (
              id TEXT PRIMARY KEY,
              source_type TEXT NOT NULL,
              source_id TEXT NOT NULL,
              scope_type TEXT NOT NULL,
              scope_id TEXT NOT NULL,
              event_time INTEGER NOT NULL,
              content TEXT NOT NULL,
              created_at INTEGER NOT NULL
            );
            CREATE TABLE memories (
              id TEXT PRIMARY KEY,
              scope_type TEXT NOT NULL,
              scope_id TEXT NOT NULL,
              type TEXT NOT NULL,
              subject TEXT NOT NULL,
              normalized_subject TEXT NOT NULL,
              current_value TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'active',
              confidence REAL NOT NULL DEFAULT 0.5,
              importance REAL NOT NULL DEFAULT 0.5,
              created_at INTEGER NOT NULL,
              updated_at INTEGER NOT NULL
            );
            CREATE TABLE memory_versions (
              id TEXT PRIMARY KEY,
              memory_id TEXT NOT NULL,
              version_no INTEGER NOT NULL,
              value TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at INTEGER NOT NULL
            );
            CREATE TABLE memory_evidence (
              id TEXT PRIMARY KEY,
              memory_id TEXT NOT NULL,
              source_type TEXT NOT NULL,
              source_event_id TEXT,
              quote TEXT,
              created_at INTEGER NOT NULL
            );
            INSERT INTO memories (
              id, scope_type, scope_id, type, subject, normalized_subject,
              current_value, created_at, updated_at
            ) VALUES (
              'mem_legacy', 'project', 'feishu_ai_challenge', 'workflow',
              '生产部署', '生产部署', '必须加 --canary', 1, 1
            );
            """
        )

    def _columns(self, conn: sqlite3.Connection, table: str) -> set[str]:
        return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


if __name__ == "__main__":
    unittest.main()
