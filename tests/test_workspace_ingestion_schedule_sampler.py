from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.sample_workspace_ingestion_schedule import sample_workspace_ingestion_schedule


class WorkspaceIngestionScheduleSamplerTest(unittest.TestCase):
    def test_samples_sanitized_reports_and_status(self) -> None:
        reports = [
            _schedule_report("2026-05-03T00:00:00+00:00"),
            _schedule_report("2026-05-03T12:30:00+00:00"),
            _schedule_report("2026-05-04T01:00:00+00:00"),
        ]
        with tempfile.TemporaryDirectory(prefix="workspace_sampler_") as temp_dir:
            with patch("scripts.sample_workspace_ingestion_schedule.run_schedule", side_effect=reports):
                result = sample_workspace_ingestion_schedule(
                    config_path=Path("schedule.json"),
                    output_dir=Path(temp_dir),
                    execute=True,
                    sample_count=3,
                    interval_seconds=0,
                    evidence_refs=["logs/workspace-sampler/redacted"],
                )

            self.assertTrue(result["ok"], result)
            self.assertTrue(result["collector"]["ok"], result["collector"])
            self.assertEqual(3, result["collector"]["successful_run_count"])
            self.assertTrue(Path(result["index_path"]).exists())
            self.assertTrue(Path(result["status_path"]).exists())
            self.assertEqual(3, len(list(Path(temp_dir).glob("schedule-report-*.json"))))

    def test_rejects_invalid_sample_count(self) -> None:
        result = sample_workspace_ingestion_schedule(sample_count=0)

        self.assertFalse(result["ok"])
        self.assertEqual("sample_count_must_be_positive", result["reason"])

    def test_sleeps_between_samples_only_when_needed(self) -> None:
        reports = [
            _schedule_report("2026-05-03T00:00:00+00:00"),
            _schedule_report("2026-05-03T00:01:00+00:00"),
        ]
        with tempfile.TemporaryDirectory(prefix="workspace_sampler_") as temp_dir:
            with patch("scripts.sample_workspace_ingestion_schedule.run_schedule", side_effect=reports):
                with patch("scripts.sample_workspace_ingestion_schedule.time.sleep") as sleep:
                    result = sample_workspace_ingestion_schedule(
                        output_dir=Path(temp_dir),
                        sample_count=2,
                        interval_seconds=1.5,
                    )

        self.assertTrue(result["ok"], result)
        sleep.assert_called_once_with(1.5)


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
                "command": [
                    "python3",
                    "scripts/feishu_workspace_ingest.py",
                    "--max-pages",
                    "3",
                    "--resume-cursor",
                ],
                "result": {
                    "ok": True,
                    "resource_count": 10,
                    "resource_type_counts": {"docx": 5, "sheet": 2},
                    "skipped_unchanged_count": 1,
                    "stale_marked_count": 1,
                    "failed_count": 0,
                },
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
