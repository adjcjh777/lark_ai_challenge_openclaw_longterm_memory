from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.collect_workspace_ingestion_long_run_evidence import (
    _load_reports,
    collect_workspace_ingestion_long_run_evidence,
)


class WorkspaceIngestionLongRunEvidenceTest(unittest.TestCase):
    def test_collects_manifest_patch_for_full_window(self) -> None:
        reports = [
            _report("2026-05-03T00:00:00+00:00", resource_count=10, counts={"docx": 4, "sheet": 1}),
            _report("2026-05-03T12:30:00+00:00", resource_count=12, counts={"docx": 5, "bitable": 2}),
            _report("2026-05-04T01:00:00+00:00", resource_count=9, counts={"wiki": 1, "sheet": 2}),
        ]

        result = collect_workspace_ingestion_long_run_evidence(
            reports=reports,
            evidence_refs=["logs/workspace-ingestion/2026-05-04/sanitized"],
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual([], result["failed_checks"])
        self.assertEqual(3, result["successful_run_count"])
        self.assertGreaterEqual(result["window_hours"], 24)
        self.assertEqual({"bitable": 2, "docx": 9, "sheet": 3, "wiki": 1}, result["resource_type_counts"])
        patch = result["production_manifest_patch"]
        self.assertEqual(3, patch["live_long_run"]["successful_runs"])
        self.assertEqual(0, patch["live_long_run"]["unresolved_failed_runs"])
        self.assertTrue(patch["discovery_and_cursoring"]["scheduler_enabled"])
        self.assertTrue(patch["discovery_and_cursoring"]["cursor_resume_proven"])
        self.assertEqual(12, patch["discovery_and_cursoring"]["max_resources_per_run"])

    def test_fails_when_window_is_too_short(self) -> None:
        result = collect_workspace_ingestion_long_run_evidence(
            reports=[
                _report("2026-05-03T00:00:00+00:00"),
                _report("2026-05-03T01:00:00+00:00"),
                _report("2026-05-03T02:00:00+00:00"),
            ],
            evidence_refs=["logs/workspace-ingestion/short-window"],
        )

        self.assertFalse(result["ok"])
        self.assertIn("long_run_window", result["failed_checks"])

    def test_failed_schedule_report_blocks_evidence(self) -> None:
        failed = _report("2026-05-04T00:00:00+00:00")
        failed["ok"] = False
        failed["failed_jobs"] = [{"name": "workspace", "reason": "timeout"}]

        result = collect_workspace_ingestion_long_run_evidence(
            reports=[
                _report("2026-05-03T00:00:00+00:00"),
                _report("2026-05-03T12:30:00+00:00"),
                failed,
            ],
            evidence_refs=["logs/workspace-ingestion/failed-run"],
        )

        self.assertFalse(result["ok"])
        self.assertIn("no_unresolved_failed_runs", result["failed_checks"])
        self.assertEqual(1, result["unresolved_failed_run_count"])

    def test_evidence_refs_are_required(self) -> None:
        result = collect_workspace_ingestion_long_run_evidence(
            reports=[
                _report("2026-05-03T00:00:00+00:00"),
                _report("2026-05-03T12:30:00+00:00"),
                _report("2026-05-04T01:00:00+00:00"),
            ],
            evidence_refs=[],
        )

        self.assertFalse(result["ok"])
        self.assertIn("evidence_refs_present", result["failed_checks"])

    def test_load_reports_accepts_absolute_glob(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "schedule-report.json"
            path.write_text(json.dumps(_report("2026-05-04T00:00:00+00:00")), encoding="utf-8")

            reports = _load_reports([], [str(Path(temp_dir) / "*.json")])

        self.assertEqual(1, len(reports))
        self.assertEqual("execute", reports[0]["mode"])


def _report(
    generated_at: str,
    *,
    resource_count: int = 10,
    counts: dict[str, int] | None = None,
) -> dict[str, object]:
    return {
        "ok": True,
        "mode": "execute",
        "status": "pass",
        "generated_at": generated_at,
        "failed_jobs": [],
        "jobs": [
            {
                "name": "workspace_recent_opened",
                "status": "pass",
                "command": [
                    "python3",
                    "scripts/feishu_workspace_ingest.py",
                    "--max-pages",
                    "3",
                    "--resume-cursor",
                ],
                "result": {
                    "ok": True,
                    "resource_count": resource_count,
                    "resource_type_counts": counts or {"docx": resource_count},
                    "skipped_unchanged_count": 1,
                    "stale_marked_count": 1,
                    "failed_count": 0,
                },
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
