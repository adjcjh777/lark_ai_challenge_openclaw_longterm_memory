from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_workspace_ingestion_long_run_tick import run_workspace_ingestion_long_run_tick


class WorkspaceIngestionLongRunTickTest(unittest.TestCase):
    def test_tick_writes_sanitized_report_and_collects_current_window(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace_long_run_tick_") as temp_dir:
            output_dir = Path(temp_dir)
            with patch(
                "scripts.run_workspace_ingestion_long_run_tick.run_schedule",
                return_value=_schedule_report("2026-05-04T00:00:00+00:00"),
            ):
                result = run_workspace_ingestion_long_run_tick(
                    config_path=Path("schedule.json"),
                    output_dir=output_dir,
                    evidence_refs=["logs/workspace-ingestion-productized-probe/long-run-active"],
                )

            self.assertTrue(result["ok"], result)
            self.assertFalse(result["collector_ok"])
            self.assertEqual(1, result["schedule_report_count"])
            report_path = Path(result["report_path"])
            self.assertTrue(report_path.exists())
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["sanitized"])
            self.assertTrue((output_dir / "samples.ndjson").exists())
            self.assertTrue((output_dir / "long-run-evidence.partial.json").exists())

    def test_tick_merges_when_collector_window_is_ready(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace_long_run_tick_") as temp_dir:
            output_dir = Path(temp_dir)
            patch_path = output_dir / "source-patch.json"
            patch_path.write_text(
                json.dumps({"production_manifest_patch": {"source_coverage": {"evidence_refs": ["logs/source"]}}}),
                encoding="utf-8",
            )
            existing = _schedule_report("2026-05-03T00:00:00+00:00")
            (output_dir / "schedule-report-existing-1.json").write_text(json.dumps(existing), encoding="utf-8")
            existing_later = _schedule_report("2026-05-03T12:30:00+00:00")
            (output_dir / "schedule-report-existing-2.json").write_text(json.dumps(existing_later), encoding="utf-8")
            with (
                patch(
                    "scripts.run_workspace_ingestion_long_run_tick.run_schedule",
                    return_value=_schedule_report("2026-05-04T01:00:00+00:00"),
                ),
                patch(
                    "scripts.run_workspace_ingestion_long_run_tick.merge_workspace_productized_ingestion_evidence_patches",
                    return_value={"ok": True, "validation": {"goal_complete": True}},
                ) as merge,
                patch(
                    "scripts.run_workspace_ingestion_long_run_tick.run_workspace_ingestion_objective_completion_audit",
                    return_value={"goal_complete": True, "status": "complete"},
                ) as objective,
            ):
                result = run_workspace_ingestion_long_run_tick(
                    config_path=Path("schedule.json"),
                    output_dir=output_dir,
                    evidence_refs=["logs/workspace-ingestion-productized-probe/long-run-active"],
                    merge_patch_paths=[patch_path],
                    merged_output=output_dir / "merged.json",
                )

            self.assertTrue(result["ok"], result)
            self.assertTrue(result["collector_ok"], result)
            self.assertIn("Workspace objective completion audit is complete", result["next_step"])
            self.assertTrue(Path(result["objective_output"]).exists())
            merge.assert_called_once()
            objective.assert_called_once_with(output_dir / "merged.json")


def _schedule_report(generated_at: str) -> dict[str, object]:
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
                "command": ["python3", "scripts/feishu_workspace_ingest.py", "--max-pages", "1", "--resume-cursor"],
                "result": {
                    "ok": True,
                    "resource_count": 8,
                    "resource_type_counts": {"docx": 1, "sheet": 1, "bitable": 1},
                    "skipped_unchanged_count": 1,
                    "stale_marked_count": 1,
                    "failed_count": 0,
                },
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
