from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.run_workspace_ingestion_schedule import DEFAULT_CONFIG_PATH, run_schedule


class WorkspaceIngestionScheduleTest(unittest.TestCase):
    def test_default_example_builds_plan_without_execution(self) -> None:
        with patch("scripts.run_workspace_ingestion_schedule.subprocess.run") as run:
            report = run_schedule(DEFAULT_CONFIG_PATH, execute=False)

        self.assertTrue(report["ok"], report["failed_jobs"])
        self.assertEqual("plan", report["mode"])
        self.assertEqual(1, report["enabled_job_count"])
        job = report["jobs"][0]
        self.assertEqual("planned", job["status"])
        self.assertIn("--dry-run", job["command"])
        self.assertIn("--resume-cursor", job["command"])
        run.assert_not_called()

    def test_execute_runs_enabled_jobs_sequentially(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace_schedule_") as temp_dir:
            config = Path(temp_dir) / "schedule.json"
            config.write_text(json.dumps(_schedule_config()), encoding="utf-8")
            completed = Mock(returncode=0, stdout=json.dumps({"ok": True, "run_id": "run_1"}), stderr="")
            with patch("scripts.run_workspace_ingestion_schedule.subprocess.run", return_value=completed) as run:
                report = run_schedule(config, execute=True)

        self.assertTrue(report["ok"], report["failed_jobs"])
        self.assertEqual("execute", report["mode"])
        self.assertEqual("pass", report["jobs"][0]["status"])
        self.assertEqual({"ok": True, "run_id": "run_1"}, report["jobs"][0]["result"])
        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertIn("--actor-open-id", command)
        self.assertIn("--mark-missing-stale", command)

    def test_non_dry_run_requires_actor(self) -> None:
        data = _schedule_config()
        data["jobs"][0].pop("actor_open_id")
        with tempfile.TemporaryDirectory(prefix="workspace_schedule_") as temp_dir:
            config = Path(temp_dir) / "schedule.json"
            config.write_text(json.dumps(data), encoding="utf-8")
            report = run_schedule(config, execute=False)

        self.assertFalse(report["ok"])
        self.assertEqual("actor_required_for_non_dry_run_job", report["failed_jobs"][0]["reason"])

    def test_secret_like_config_is_rejected(self) -> None:
        data = _schedule_config()
        data["defaults"]["profile"] = "Bearer leaked-token"
        with tempfile.TemporaryDirectory(prefix="workspace_schedule_") as temp_dir:
            config = Path(temp_dir) / "schedule.json"
            config.write_text(json.dumps(data), encoding="utf-8")
            report = run_schedule(config, execute=False)

        self.assertFalse(report["ok"])
        self.assertEqual("secret_like_value_present", report["failed_jobs"][0]["reason"])

    def test_disabled_job_is_skipped(self) -> None:
        data = _schedule_config()
        data["jobs"][0]["enabled"] = False
        with tempfile.TemporaryDirectory(prefix="workspace_schedule_") as temp_dir:
            config = Path(temp_dir) / "schedule.json"
            config.write_text(json.dumps(data), encoding="utf-8")
            report = run_schedule(config, execute=False)

        self.assertTrue(report["ok"])
        self.assertEqual("skipped", report["jobs"][0]["status"])
        self.assertEqual(0, report["enabled_job_count"])


def _schedule_config() -> dict[str, object]:
    return {
        "schema_version": "workspace_ingestion_schedule/v1",
        "defaults": {
            "profile": "feishu-ai-challenge",
            "as_identity": "user",
            "tenant_id": "tenant:demo",
            "organization_id": "org:demo",
            "roles": "member,reviewer",
            "scope": "project:feishu_ai_challenge",
            "limit": 10,
            "max_pages": 2,
            "timeout_seconds": 60,
            "dry_run": False,
        },
        "jobs": [
            {
                "name": "project_workspace",
                "query": "OpenClaw",
                "doc_types": ["docx", "sheet", "bitable"],
                "opened_since": "30d",
                "actor_open_id": "ou_reviewer",
                "resume_cursor": True,
                "mark_missing_stale": True,
                "resources": ["sheet:sht_1:Project Sheet"],
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
