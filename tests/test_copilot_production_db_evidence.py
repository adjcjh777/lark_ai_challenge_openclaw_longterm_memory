from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.collect_copilot_production_db_evidence import collect_production_db_evidence


class CopilotProductionDbEvidenceTest(unittest.TestCase):
    def test_collects_safe_production_db_manifest_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            migration_report = Path(tmp) / "migration.json"
            restore_report = Path(tmp) / "restore.json"
            migration_report.write_text(
                json.dumps({"ok": True, "after": {"ready": True}, "boundary": "production migration log"}),
                encoding="utf-8",
            )
            restore_report.write_text(
                json.dumps({"ok": True, "integrity_check": "ok", "storage_ready": True}),
                encoding="utf-8",
            )

            result = collect_production_db_evidence(
                engine="managed_postgresql",
                migration_applied_at="2026-05-01T10:00:00+08:00",
                pitr_enabled=True,
                backup_restore_drill_at="2026-05-01T11:00:00+08:00",
                evidence_refs=["ops/db-migration-20260501", "ops/pitr-restore-drill-20260501"],
                migration_report=migration_report,
                restore_report=restore_report,
            )

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["production_ready_claim"], result)
        patch = result["production_manifest_patch"]["production_db"]
        self.assertEqual("managed_postgresql", patch["engine"])
        self.assertTrue(patch["pitr_enabled"])
        self.assertEqual(2, len(patch["evidence_refs"]))
        self.assertEqual([], result["failed_checks"])

    def test_rejects_placeholder_or_secret_like_evidence_refs(self) -> None:
        result = collect_production_db_evidence(
            engine="postgresql",
            migration_applied_at="2026-05-01T10:00:00+08:00",
            pitr_enabled=True,
            backup_restore_drill_at="2026-05-01T11:00:00+08:00",
            evidence_refs=["postgresql://user:password@host/db"],
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("evidence_refs", result["failed_checks"])

    def test_rejects_missing_pitr_and_bad_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad_report = Path(tmp) / "missing.json"
            result = collect_production_db_evidence(
                engine="postgresql",
                migration_applied_at="__FILL_ISO8601__",
                pitr_enabled=False,
                backup_restore_drill_at="2026-05-01T11:00:00+08:00",
                evidence_refs=["ops/db-migration-20260501"],
                migration_report=bad_report,
            )

        self.assertFalse(result["ok"], result)
        self.assertIn("migration_timestamp", result["failed_checks"])
        self.assertIn("pitr_enabled", result["failed_checks"])
        self.assertIn("attached_reports", result["failed_checks"])


if __name__ == "__main__":
    unittest.main()
