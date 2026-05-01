from __future__ import annotations

import unittest
from datetime import datetime, timezone

from scripts.check_copilot_production_db_probe import run_production_db_probe


class CopilotProductionDbProbeTest(unittest.TestCase):
    def test_probe_emits_production_db_patch_without_printing_dsn(self) -> None:
        dsn = "postgresql://memory_user:secret@db.company.internal:5432/memory"
        calls: list[tuple[list[str], str]] = []

        def runner(command: list[str], env: dict[str, str], timeout: float):
            calls.append((command, env["PGDATABASE"]))
            if command[0] == "pg_isready":
                return {"returncode": 0, "stdout": "accepting connections", "stderr": ""}
            return {"returncode": 0, "stdout": "150002\n", "stderr": ""}

        result = run_production_db_probe(
            dsn_env="DATABASE_URL",
            engine="managed_postgresql",
            migration_applied_at="2026-05-01T10:00:00+08:00",
            pitr_enabled=True,
            backup_restore_drill_at="2026-05-01T11:00:00+08:00",
            evidence_refs=["ops/db-migration-20260501", "ops/pitr-restore-drill-20260501"],
            environ={"DATABASE_URL": dsn},
            command_runner=runner,
            now=datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc),
        )

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["production_ready_claim"])
        self.assertEqual(2, len(calls))
        self.assertTrue(all(call[1] == dsn for call in calls))
        self.assertNotIn(dsn, str(result))
        self.assertNotIn("secret@", str(result))
        patch = result["production_manifest_patch"]["production_db"]
        self.assertEqual("managed_postgresql", patch["engine"])
        self.assertTrue(patch["pitr_enabled"])
        self.assertIn("db_live_probe:db.company.internal:", patch["evidence_refs"][-1])

    def test_probe_rejects_missing_or_placeholder_dsn_without_commands(self) -> None:
        called = {"runner": False}

        def runner(command: list[str], env: dict[str, str], timeout: float):
            called["runner"] = True
            return {"returncode": 0, "stdout": "150002\n", "stderr": ""}

        result = run_production_db_probe(
            dsn_env="DATABASE_URL",
            engine="postgresql",
            migration_applied_at="2026-05-01T10:00:00+08:00",
            pitr_enabled=True,
            backup_restore_drill_at="2026-05-01T11:00:00+08:00",
            evidence_refs=["ops/db-migration-20260501"],
            environ={"DATABASE_URL": "postgresql://user:pass@localhost:5432/memory"},
            command_runner=runner,
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("dsn", result["failed_checks"])
        self.assertFalse(called["runner"])
        self.assertIn("host_is_not_placeholder", result["checks"]["dsn"]["missing_or_placeholder"])

    def test_probe_rejects_low_server_version_and_bad_evidence(self) -> None:
        def runner(command: list[str], env: dict[str, str], timeout: float):
            if command[0] == "pg_isready":
                return {"returncode": 0, "stdout": "accepting connections", "stderr": ""}
            return {"returncode": 0, "stdout": "140009\n", "stderr": ""}

        result = run_production_db_probe(
            dsn_env="DATABASE_URL",
            engine="mysql",
            migration_applied_at="not-a-date",
            pitr_enabled=False,
            backup_restore_drill_at="2026-05-01T11:00:00+08:00",
            evidence_refs=["postgresql://user:password@db.company.internal/memory"],
            environ={"DATABASE_URL": "postgresql://user:pass@db.company.internal:5432/memory"},
            command_runner=runner,
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("engine", result["failed_checks"])
        self.assertIn("migration_timestamp", result["failed_checks"])
        self.assertIn("pitr", result["failed_checks"])
        self.assertIn("evidence_refs", result["failed_checks"])
        self.assertIn("psql_readonly_query", result["failed_checks"])
        self.assertIn(
            "server_version_at_least_minimum",
            result["checks"]["psql_readonly_query"]["missing_or_placeholder"],
        )


if __name__ == "__main__":
    unittest.main()
