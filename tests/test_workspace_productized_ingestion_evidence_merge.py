from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_workspace_productized_ingestion_readiness import DEFAULT_MANIFEST_PATH
from scripts.merge_workspace_productized_ingestion_evidence import (
    merge_workspace_productized_ingestion_evidence_patches,
)


class WorkspaceProductizedIngestionEvidenceMergeTest(unittest.TestCase):
    def test_merges_complete_patch_set_into_goal_complete_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace_productized_merge_") as temp_dir:
            root = Path(temp_dir)
            patch_paths = _write_complete_patch_set(root)
            output_path = root / "workspace-productized-evidence.json"

            result = merge_workspace_productized_ingestion_evidence_patches(
                base_manifest=DEFAULT_MANIFEST_PATH,
                patch_paths=patch_paths,
                output_path=output_path,
            )

            self.assertTrue(result["ok"], result)
            self.assertFalse(result["productized_ready_claim"], result)
            self.assertTrue(result["validation"]["goal_complete"], result["validation"])
            self.assertEqual(
                [
                    "discovery_and_cursoring",
                    "governance",
                    "live_long_run",
                    "operations",
                    "rate_limit_and_backoff",
                    "source_coverage",
                ],
                result["merged_sections"],
            )
            merged = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertFalse(merged["example"])
            self.assertEqual(2, merged["source_coverage"]["source_types"]["document_feishu"]["organic_sample_count"])

    def test_partial_merge_runs_gate_but_remains_blocked(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace_productized_merge_") as temp_dir:
            root = Path(temp_dir)
            patch = root / "long-run.json"
            patch.write_text(json.dumps({"production_manifest_patch": _long_run_patch()}), encoding="utf-8")

            result = merge_workspace_productized_ingestion_evidence_patches(
                base_manifest=DEFAULT_MANIFEST_PATH,
                patch_paths=[patch],
            )

            self.assertTrue(result["ok"], result)
            self.assertFalse(result["validation"]["goal_complete"], result["validation"])
            self.assertIn("source_coverage", result["validation"]["failed_checks"])

    def test_rejects_unknown_section(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace_productized_merge_") as temp_dir:
            patch = Path(temp_dir) / "bad.json"
            patch.write_text(
                json.dumps({"production_manifest_patch": {"unexpected_section": {"ok": True}}}),
                encoding="utf-8",
            )

            result = merge_workspace_productized_ingestion_evidence_patches(
                base_manifest=DEFAULT_MANIFEST_PATH,
                patch_paths=[patch],
            )

            self.assertFalse(result["ok"], result)
            self.assertEqual("unknown_manifest_sections", result["errors"][0]["error"])

    def test_rejects_placeholder_or_secret_like_patch_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace_productized_merge_") as temp_dir:
            patch = Path(temp_dir) / "secret.json"
            patch.write_text(
                json.dumps(
                    {
                        "production_manifest_patch": {
                            "operations": {
                                "single_listener_preflight_at": "2026-05-04T10:20:00+08:00",
                                "evidence_refs": ["Bearer leaked-token"],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = merge_workspace_productized_ingestion_evidence_patches(
                base_manifest=DEFAULT_MANIFEST_PATH,
                patch_paths=[patch],
            )

            self.assertFalse(result["ok"], result)
            self.assertEqual("patch_contains_placeholder_or_secret_like_value", result["errors"][0]["error"])


def _write_complete_patch_set(root: Path) -> list[Path]:
    patches = {
        "source.json": _source_patch(),
        "long-run.json": _long_run_patch(),
        "ops.json": _ops_patch(),
    }
    paths: list[Path] = []
    for name, patch in patches.items():
        path = root / name
        path.write_text(json.dumps({"production_manifest_patch": patch}), encoding="utf-8")
        paths.append(path)
    return paths


def _source_patch() -> dict[str, object]:
    evidence_refs = ["logs/workspace-productized/source-coverage-redacted"]
    return {
        "source_coverage": {
            "source_types": {
                "document_feishu": {"organic_sample_count": 2},
                "lark_sheet": {"organic_sample_count": 1},
                "lark_bitable": {"organic_sample_count": 1},
            },
            "workspace_surfaces": {
                "document": {"organic_sample_count": 1},
                "sheet": {"organic_sample_count": 1},
                "bitable": {"organic_sample_count": 1},
                "wiki": {"organic_sample_count": 1},
            },
            "same_conclusion_across_chat_and_workspace": True,
            "conflict_negative_proven": True,
            "evidence_refs": evidence_refs,
        }
    }


def _long_run_patch() -> dict[str, object]:
    evidence_refs = ["logs/workspace-productized/long-run-redacted"]
    return {
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
        "live_long_run": {
            "started_at": "2026-05-03T10:00:00+08:00",
            "ended_at": "2026-05-04T11:00:00+08:00",
            "duration_hours": 25,
            "successful_runs": 4,
            "unresolved_failed_runs": 0,
            "evidence_refs": evidence_refs,
        },
    }


def _ops_patch() -> dict[str, object]:
    evidence_refs = ["logs/workspace-productized/ops-redacted"]
    return {
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
    }


if __name__ == "__main__":
    unittest.main()
