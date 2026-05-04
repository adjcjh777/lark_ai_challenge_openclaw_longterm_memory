from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.collect_workspace_ops_governance_evidence import (
    collect_workspace_ops_governance_evidence,
    main,
)


class WorkspaceOpsGovernanceEvidenceTest(unittest.TestCase):
    def test_collects_complete_patch(self) -> None:
        result = collect_workspace_ops_governance_evidence(**_complete_kwargs())

        self.assertTrue(result["ok"], result["failed_checks"])
        patch = result["production_manifest_patch"]
        self.assertEqual(30, patch["rate_limit_and_backoff"]["timeout_seconds"])
        self.assertTrue(patch["governance"]["curated_only_embedding"])
        self.assertTrue(patch["operations"]["dashboard_or_report_readback"])
        self.assertFalse(result["production_ready_claim"])

    def test_rejects_missing_flags_and_placeholder_refs(self) -> None:
        kwargs = _complete_kwargs()
        kwargs["failed_fetch_audit_proven"] = False
        kwargs["rate_limit_evidence_refs"] = ["__FILL_WITH_EVIDENCE__"]

        result = collect_workspace_ops_governance_evidence(**kwargs)

        self.assertFalse(result["ok"])
        self.assertEqual(["rate_limit_and_backoff"], result["failed_checks"])
        self.assertIn("failed_fetch_audit_proven", result["checks"]["rate_limit_and_backoff"]["failed_subchecks"])
        self.assertIn("evidence_refs_present", result["checks"]["rate_limit_and_backoff"]["failed_subchecks"])

    def test_cli_writes_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace_ops_evidence_") as temp_dir:
            output = Path(temp_dir) / "ops-evidence.json"
            argv = [
                "collect_workspace_ops_governance_evidence.py",
                "--timeout-seconds",
                "30",
                "--backoff-policy",
                "bounded_retry_backoff_with_jitter",
                "--rate-limit-budget",
                "200 resources per run; 1 run per hour",
                "--throttling-or-retry-tested-at",
                "2026-05-04T10:00:00+08:00",
                "--failed-fetch-audit-proven",
                "--rate-limit-evidence-ref",
                "logs/workspace-productized/rate-limit-redacted",
                "--review-policy-enforced",
                "--permission-fail-closed-negative-at",
                "2026-05-04T10:10:00+08:00",
                "--no-raw-event-embedding",
                "--curated-only-embedding",
                "--audit-readback-proven",
                "--governance-evidence-ref",
                "logs/workspace-productized/governance-redacted",
                "--single-listener-preflight-at",
                "2026-05-04T10:20:00+08:00",
                "--monitoring-alert-tested-at",
                "2026-05-04T10:30:00+08:00",
                "--rollback-stop-write-tested-at",
                "2026-05-04T10:40:00+08:00",
                "--retention-policy-approved-at",
                "2026-05-04T10:50:00+08:00",
                "--dashboard-or-report-readback",
                "--operations-evidence-ref",
                "logs/workspace-productized/ops-redacted",
                "--output",
                str(output),
                "--json",
            ]
            with patch("sys.argv", argv), redirect_stdout(StringIO()):
                exit_code = main()

            self.assertEqual(0, exit_code)
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(written["ok"])


def _complete_kwargs() -> dict[str, object]:
    return {
        "timeout_seconds": 30,
        "backoff_policy": "bounded_retry_backoff_with_jitter",
        "rate_limit_budget": "200 resources per run; 1 run per hour",
        "throttling_or_retry_tested_at": "2026-05-04T10:00:00+08:00",
        "failed_fetch_audit_proven": True,
        "rate_limit_evidence_refs": ["logs/workspace-productized/rate-limit-redacted"],
        "review_policy_enforced": True,
        "permission_fail_closed_negative_at": "2026-05-04T10:10:00+08:00",
        "no_raw_event_embedding": True,
        "curated_only_embedding": True,
        "audit_readback_proven": True,
        "governance_evidence_refs": ["logs/workspace-productized/governance-redacted"],
        "single_listener_preflight_at": "2026-05-04T10:20:00+08:00",
        "monitoring_alert_tested_at": "2026-05-04T10:30:00+08:00",
        "rollback_stop_write_tested_at": "2026-05-04T10:40:00+08:00",
        "retention_policy_approved_at": "2026-05-04T10:50:00+08:00",
        "dashboard_or_report_readback": True,
        "operations_evidence_refs": ["logs/workspace-productized/ops-redacted"],
    }


if __name__ == "__main__":
    unittest.main()
