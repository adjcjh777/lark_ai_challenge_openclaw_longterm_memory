from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_cognee_embedding_sampler_status import check_cognee_embedding_sampler_status


class CogneeEmbeddingSamplerStatusTest(unittest.TestCase):
    def test_running_sampler_with_incomplete_window_is_warning_not_complete(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cognee_sampler_status_") as temp_dir:
            sample_log = Path(temp_dir) / "samples.ndjson"
            pid_file = Path(temp_dir) / "sampler.pid"
            sample_log.write_text(json.dumps(_sample("2026-05-01T00:00:00+00:00")) + "\n", encoding="utf-8")
            pid_file.write_text("12345", encoding="utf-8")

            result = check_cognee_embedding_sampler_status(
                embedding_sample_log=sample_log,
                pid_file=pid_file,
                process_alive=lambda pid: pid == 12345,
                process_command=lambda _pid: (
                    "python scripts/sample_cognee_embedding_health.py --sample-count 3 "
                    "--sample-interval-seconds 43200 --output samples.ndjson --json"
                ),
            )

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["completion_ready"])
        self.assertEqual("pass", result["checks"]["sampler_process_alive"]["status"])
        self.assertEqual("warning", result["checks"]["embedding_successful_samples"]["status"])
        self.assertEqual("warning", result["checks"]["embedding_window"]["status"])
        self.assertIn("more successful samples", result["next_step"])
        self.assertEqual(
            {
                "sample_count": "3",
                "sample_interval_seconds": "43200",
                "output": "samples.ndjson",
            },
            result["sampler_schedule"],
        )
        self.assertEqual("2026-05-01T12:00:00+00:00", result["next_expected_sample_at"])
        self.assertEqual("2026-05-02T00:00:00+00:00", result["final_scheduled_sample_at"])
        self.assertIn("collect_cognee_embedding_long_run_evidence.py", result["collector_command_template"])
        self.assertIn(str(sample_log), result["collector_command_template"])

    def test_dead_sampler_with_incomplete_evidence_fails(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cognee_sampler_status_") as temp_dir:
            sample_log = Path(temp_dir) / "samples.ndjson"
            pid_file = Path(temp_dir) / "sampler.pid"
            sample_log.write_text(json.dumps(_sample("2026-05-01T00:00:00+00:00")) + "\n", encoding="utf-8")
            pid_file.write_text("12345", encoding="utf-8")

            result = check_cognee_embedding_sampler_status(
                embedding_sample_log=sample_log,
                pid_file=pid_file,
                process_alive=lambda _pid: False,
            )

        self.assertFalse(result["ok"])
        self.assertFalse(result["completion_ready"])
        self.assertIn("sampler_process_alive", result["failed_checks"])
        self.assertIn("embedding_successful_samples", result["failed_checks"])
        self.assertIn("embedding_window", result["failed_checks"])

    def test_completed_evidence_passes_even_without_live_pid(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cognee_sampler_status_") as temp_dir:
            sample_log = Path(temp_dir) / "samples.ndjson"
            sample_log.write_text(
                "\n".join(
                    [
                        json.dumps(_sample("2026-05-01T00:00:00+00:00")),
                        json.dumps(_sample("2026-05-01T12:30:00+00:00")),
                        json.dumps(_sample("2026-05-02T01:00:00+00:00")),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = check_cognee_embedding_sampler_status(
                embedding_sample_log=sample_log,
                min_window_hours=24,
                min_sample_count=3,
            )

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["completion_ready"])
        self.assertEqual([], result["failed_checks"])
        self.assertEqual("pass", result["checks"]["sampler_process_alive"]["status"])
        self.assertEqual("2026-05-02T00:00:00+00:00", result["estimated_ready_at"])
        self.assertIn("--persistent-readback-report", result["collector_command_template"])


def _sample(sampled_at: str) -> dict[str, object]:
    return {
        "ok": True,
        "status": "ready",
        "sampled_at": sampled_at,
        "model": "openai/text-embedding-v4",
        "expected_dimensions": 1024,
        "actual_dimensions": 1024,
    }


if __name__ == "__main__":
    unittest.main()
