from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.run_workspace_ingestion_schedule import DEFAULT_CONFIG_PATH, run_schedule, sanitize_report


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

    def test_execute_retries_failed_job_with_backoff(self) -> None:
        data = _schedule_config()
        data["defaults"]["retry_attempts"] = 1
        data["defaults"]["retry_backoff_seconds"] = 2
        with tempfile.TemporaryDirectory(prefix="workspace_schedule_") as temp_dir:
            config = Path(temp_dir) / "schedule.json"
            config.write_text(json.dumps(data), encoding="utf-8")
            failed = Mock(returncode=1, stdout=json.dumps({"ok": False}), stderr="temporary")
            passed = Mock(returncode=0, stdout=json.dumps({"ok": True, "run_id": "run_2"}), stderr="")
            with (
                patch("scripts.run_workspace_ingestion_schedule.subprocess.run", side_effect=[failed, passed]) as run,
                patch("scripts.run_workspace_ingestion_schedule.time.sleep") as sleep,
            ):
                report = run_schedule(config, execute=True)

        self.assertTrue(report["ok"], report["failed_jobs"])
        job = report["jobs"][0]
        self.assertEqual("pass", job["status"])
        self.assertEqual(2, job["attempt_count"])
        self.assertEqual([False, True], [attempt["ok"] for attempt in job["attempts"]])
        self.assertEqual({"ok": True, "run_id": "run_2"}, job["result"])
        self.assertEqual(2, run.call_count)
        sleep.assert_called_once_with(2)

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

    def test_sanitized_report_redacts_resource_tokens_and_urls(self) -> None:
        report = {
            "ok": True,
            "jobs": [
                {
                    "name": "dry_run_job",
                    "command": [
                        "python3",
                        "scripts/feishu_workspace_ingest.py",
                        "--resource",
                        "sheet:sht_1",
                        "--actor-open-id",
                        "ou_reviewer",
                    ],
                    "command_preview": [
                        "python3",
                        "scripts/feishu_workspace_ingest.py",
                        "--resource",
                        "<redacted>",
                        "--actor-open-id",
                        "<redacted>",
                    ],
                    "result": {
                        "resources": [
                            {
                                "resource_type": "sheet",
                                "route_type": "sheet",
                                "title": "Project Sheet",
                                "token": "sht_1",
                                "url": "https://example.feishu.cn/sheets/sht_1",
                            },
                            {
                                "resource_type": "docx",
                                "route_type": "document",
                                "title": "Project Doc",
                                "token": "doc_1",
                                "url": "https://example.feishu.cn/docx/doc_1",
                            },
                        ]
                    },
                    "attempts": [
                        {
                            "result": {
                                "resources": [
                                    {
                                        "resource_type": "sheet",
                                        "route_type": "sheet",
                                        "title": "Project Sheet",
                                        "token": "sht_1",
                                        "url": "https://example.feishu.cn/sheets/sht_1",
                                    }
                                ]
                            }
                        }
                    ],
                }
            ],
        }

        sanitized = sanitize_report(report)

        job = sanitized["jobs"][0]
        self.assertEqual(
            [
                "python3",
                "scripts/feishu_workspace_ingest.py",
                "--resource",
                "<redacted>",
                "--actor-open-id",
                "<redacted>",
            ],
            job["command"],
        )
        self.assertNotIn("command_preview", job)
        self.assertEqual({"docx": 1, "sheet": 1}, job["result"]["resource_type_counts"])
        self.assertEqual("<redacted>", job["result"]["resources"][0]["token"])
        self.assertEqual("<redacted>", job["result"]["resources"][0]["url"])
        self.assertEqual("<redacted>", job["attempts"][0]["result"]["resources"][0]["token"])

    def test_sanitized_report_redacts_non_dry_run_results_and_cursor_tokens(self) -> None:
        report = {
            "ok": True,
            "jobs": [
                {
                    "name": "ingest_job",
                    "command": [
                        "python3",
                        "scripts/feishu_workspace_ingest.py",
                        "--actor-open-id",
                        "ou_reviewer",
                        "--chat-ids",
                        "oc_private",
                    ],
                    "command_preview": [
                        "python3",
                        "scripts/feishu_workspace_ingest.py",
                        "--actor-open-id",
                        "<redacted>",
                        "--chat-ids",
                        "<redacted>",
                    ],
                    "result": {
                        "ok": True,
                        "discovery": {
                            "start_page_token": "page_start_secret",
                            "next_page_token": "page_next_secret",
                            "cursor_before": {"page_token": "page_before_secret"},
                            "cursor_after": {"page_token": "page_after_secret"},
                        },
                        "results": [
                            {
                                "resource": {
                                    "resource_type": "sheet",
                                    "route_type": "sheet",
                                    "title": "Project Sheet",
                                    "token": "sht_1",
                                    "url": "https://example.feishu.cn/sheets/sht_1",
                                },
                                "source": {
                                    "source_type": "lark_sheet",
                                    "source_id": "sht_1#Sheet1",
                                    "title": "Project Sheet",
                                },
                                "ok": True,
                                "candidate_count": 2,
                            },
                            {
                                "resource": {
                                    "resource_type": "docx",
                                    "route_type": "document",
                                    "title": "Project Doc",
                                    "token": "doc_1",
                                    "url": "https://example.feishu.cn/docx/doc_1",
                                },
                                "ok": False,
                                "stage": "fetch",
                                "error": "document doc_1 at https://example.feishu.cn/docx/doc_1 failed",
                            },
                        ],
                    },
                }
            ],
        }

        sanitized = sanitize_report(report)

        payload = json.dumps(sanitized, ensure_ascii=False)
        self.assertNotIn("sht_1", payload)
        self.assertNotIn("doc_1", payload)
        self.assertNotIn("page_start_secret", payload)
        self.assertNotIn("page_next_secret", payload)
        self.assertNotIn("ou_reviewer", payload)
        self.assertEqual({"lark_sheet": 1}, sanitized["jobs"][0]["result"]["source_type_counts"])
        self.assertEqual({"docx": 1, "sheet": 1}, sanitized["jobs"][0]["result"]["resource_type_counts"])
        self.assertEqual("<redacted>", sanitized["jobs"][0]["result"]["discovery"]["next_page_token"])
        self.assertEqual("<redacted>", sanitized["jobs"][0]["result"]["results"][0]["resource"]["token"])
        self.assertEqual("<redacted>", sanitized["jobs"][0]["result"]["results"][0]["source"]["source_id"])
        self.assertIn("<redacted>", sanitized["jobs"][0]["result"]["results"][1]["error"])

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
            "retry_attempts": 0,
            "retry_backoff_seconds": 0,
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
