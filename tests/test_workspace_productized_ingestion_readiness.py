from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.check_workspace_productized_ingestion_readiness import (
    DEFAULT_MANIFEST_PATH,
    run_productized_ingestion_check,
)


class WorkspaceProductizedIngestionReadinessTest(unittest.TestCase):
    def test_missing_manifest_blocks_goal(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace_productized_gate_") as temp_dir:
            report = run_productized_ingestion_check(Path(temp_dir) / "missing.json")

        self.assertFalse(report["ok"])
        self.assertFalse(report["goal_complete"])
        self.assertEqual(["manifest_file"], report["failed_checks"])
        self.assertIn("manifest", report["next_step"])

    def test_example_manifest_is_not_goal_complete(self) -> None:
        report = run_productized_ingestion_check(DEFAULT_MANIFEST_PATH)

        self.assertTrue(report["ok"])
        self.assertFalse(report["goal_complete"])
        self.assertTrue(report["example_manifest"])
        self.assertIn("source_coverage", report["warning_checks"])
        self.assertIn("live_long_run", report["warning_checks"])

    def test_complete_non_example_manifest_passes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace_productized_gate_") as temp_dir:
            manifest = Path(temp_dir) / "manifest.json"
            manifest.write_text(json.dumps(_complete_manifest()), encoding="utf-8")

            report = run_productized_ingestion_check(manifest)

        self.assertTrue(report["ok"], report["failed_checks"])
        self.assertTrue(report["goal_complete"], report["blockers"])
        self.assertEqual([], report["failed_checks"])
        self.assertEqual([], report["warning_checks"])

    def test_secret_like_values_fail(self) -> None:
        manifest_data = _complete_manifest()
        manifest_data["operations"]["evidence_refs"] = ["Bearer leaked-token"]
        with tempfile.TemporaryDirectory(prefix="workspace_productized_gate_") as temp_dir:
            manifest = Path(temp_dir) / "manifest.json"
            manifest.write_text(json.dumps(manifest_data), encoding="utf-8")

            report = run_productized_ingestion_check(manifest)

        self.assertFalse(report["ok"])
        self.assertFalse(report["goal_complete"])
        self.assertIn("secret_redaction", report["failed_checks"])

    def test_cli_require_productized_ready_fails_for_example_manifest(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/check_workspace_productized_ingestion_readiness.py",
                "--require-productized-ready",
                "--json",
            ],
            cwd=Path(__file__).resolve().parents[1],
            check=False,
            capture_output=True,
            text=True,
        )

        payload = json.loads(completed.stdout)
        self.assertEqual(1, completed.returncode)
        self.assertFalse(payload["goal_complete"])
        self.assertTrue(payload["example_manifest"])


def _complete_manifest() -> dict[str, object]:
    evidence_refs = ["logs/workspace-productized/2026-05-04/redacted-evidence.json"]
    return {
        "schema_version": "workspace_productized_ingestion_evidence/v1",
        "example": False,
        "source_coverage": {
            "source_types": {
                "document_feishu": {"organic_sample_count": 2},
                "lark_sheet": {"organic_sample_count": 1},
                "lark_bitable": {"organic_sample_count": 1},
            },
            "workspace_surfaces": {
                "document": {"organic_sample_count": 2},
                "sheet": {"organic_sample_count": 1},
                "bitable": {"organic_sample_count": 1},
                "wiki": {"organic_sample_count": 1},
            },
            "same_conclusion_across_chat_and_workspace": True,
            "conflict_negative_proven": True,
            "evidence_refs": evidence_refs,
        },
        "discovery_and_cursoring": {
            "scheduler_enabled": True,
            "cursor_resume_proven": True,
            "revision_skip_proven": True,
            "stale_marking_proven": True,
            "revocation_proven": True,
            "max_resources_per_run": 200,
            "max_pages_per_run": 10,
            "evidence_refs": evidence_refs,
        },
        "rate_limit_and_backoff": {
            "timeout_seconds": 30,
            "backoff_policy": "exponential_backoff_with_jitter",
            "rate_limit_budget": "200 resources per run; 1 run per hour",
            "throttling_or_retry_tested_at": "2026-05-04T10:00:00+08:00",
            "failed_fetch_audit_proven": True,
            "evidence_refs": evidence_refs,
        },
        "governance": {
            "review_policy_enforced": True,
            "permission_fail_closed_negative_at": "2026-05-04T10:10:00+08:00",
            "no_raw_event_embedding": True,
            "curated_only_embedding": True,
            "audit_readback_proven": True,
            "evidence_refs": evidence_refs,
        },
        "operations": {
            "single_listener_preflight_at": "2026-05-04T10:20:00+08:00",
            "monitoring_alert_tested_at": "2026-05-04T10:30:00+08:00",
            "rollback_stop_write_tested_at": "2026-05-04T10:40:00+08:00",
            "retention_policy_approved_at": "2026-05-04T10:50:00+08:00",
            "dashboard_or_report_readback": True,
            "evidence_refs": evidence_refs,
        },
        "live_long_run": {
            "started_at": "2026-05-03T10:00:00+08:00",
            "ended_at": "2026-05-04T11:00:00+08:00",
            "duration_hours": 25,
            "successful_runs": 4,
            "unresolved_failed_runs": 0,
            "evidence_refs": evidence_refs,
        },
    }


if __name__ == "__main__":
    unittest.main()
