from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_workspace_productized_ingestion_readiness import SCHEMA_VERSION
from scripts.check_workspace_ingestion_objective_completion import (
    run_workspace_ingestion_objective_completion_audit,
)


class WorkspaceIngestionObjectiveCompletionTest(unittest.TestCase):
    def test_default_example_manifest_keeps_goal_incomplete(self) -> None:
        result = run_workspace_ingestion_objective_completion_audit()

        self.assertFalse(result["goal_complete"])
        self.assertEqual("incomplete", result["status"])
        self.assertTrue(any(item["reason"] == "productized_gate_blocked" for item in result["blockers"]))

    def test_complete_manifest_allows_goal_complete_when_artifacts_exist(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace_objective_audit_") as temp_dir:
            manifest = Path(temp_dir) / "complete.json"
            manifest.write_text(json.dumps(_complete_manifest()), encoding="utf-8")

            result = run_workspace_ingestion_objective_completion_audit(manifest)

        self.assertTrue(result["goal_complete"], result["blockers"])
        self.assertEqual("complete", result["status"])
        self.assertEqual([], result["blockers"])


def _complete_manifest() -> dict[str, object]:
    evidence_refs = ["logs/workspace-productized/redacted-evidence"]
    return {
        "schema_version": SCHEMA_VERSION,
        "example": False,
        "source_coverage": {
            "source_types": {
                "document_feishu": {"organic_sample_count": 1},
                "lark_doc": {"organic_sample_count": 1},
                "lark_sheet": {"organic_sample_count": 1},
                "lark_bitable": {"organic_sample_count": 1},
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
            "backoff_policy": "bounded_retry_backoff_with_jitter",
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
