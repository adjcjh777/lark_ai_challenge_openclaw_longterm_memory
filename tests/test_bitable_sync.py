from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memory_engine.bitable_sync import collect_sync_payload, setup_commands, sync_payload, table_schema_spec
from memory_engine.copilot.permissions import demo_permission_context
from memory_engine.copilot.service import CopilotService
from memory_engine.copilot.tools import handle_tool_request
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository


class BitableSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "memory.sqlite"
        self.conn = connect(self.db_path)
        init_db(self.conn)
        self.repo = MemoryRepository(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    def test_collects_ledger_and_version_rows(self) -> None:
        created = self.repo.remember(
            "project:feishu_ai_challenge",
            "生产部署必须加 --canary --region cn-shanghai",
            source_type="test",
            source_id="msg_1",
        )
        self.repo.remember(
            "project:feishu_ai_challenge",
            "不对，生产部署 region 改成 ap-shanghai",
            source_type="test",
            source_id="msg_2",
        )

        payload = collect_sync_payload(self.conn)

        ledger = payload["tables"]["ledger"]
        versions = payload["tables"]["versions"]
        self.assertEqual(1, len(ledger["rows"]))
        self.assertEqual(2, len(versions["rows"]))
        self.assertEqual(created["memory_id"], ledger["rows"][0][ledger["fields"].index("memory_id")])
        self.assertEqual("active", ledger["rows"][0][ledger["fields"].index("status")])
        self.assertEqual(2, ledger["rows"][0][ledger["fields"].index("version")])

        statuses = {row[versions["fields"].index("status")] for row in versions["rows"]}
        self.assertEqual({"active", "superseded"}, statuses)

    def test_dry_run_returns_commands_without_lark_cli(self) -> None:
        self.repo.remember("project:feishu_ai_challenge", "生产部署必须加 --canary")
        payload = collect_sync_payload(self.conn)

        result = sync_payload(payload, setup_target(), dry_run=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(
            {"ledger": 1, "versions": 1, "candidate_review": 0, "benchmark": 0, "reminder_candidates": 0},
            result["tables"],
        )
        self.assertEqual(2, len(result["commands"]))

    def test_benchmark_summary_row_can_be_included(self) -> None:
        benchmark_path = Path(self.temp_dir.name) / "benchmark.json"
        benchmark_path.write_text(
            '{"summary":{"case_count":3,"case_pass_rate":1.0,"conflict_accuracy":1.0,'
            '"recall_at_3":1.0,"candidate_precision":1.0,"agent_task_context_use_rate":1.0,'
            '"l1_hot_recall_p95_ms":0.4,"sensitive_reminder_leakage_rate":0.0,'
            '"stale_leakage_rate":0.0,"evidence_coverage":1.0,"avg_latency_ms":0.2,'
            '"failure_type_counts":{}}}',
            encoding="utf-8",
        )

        payload = collect_sync_payload(self.conn, benchmark_json=benchmark_path, benchmark_name="day1")
        benchmark = payload["tables"]["benchmark"]

        self.assertEqual(1, len(benchmark["rows"]))
        self.assertEqual("day1", benchmark["rows"][0][benchmark["fields"].index("benchmark_name")])
        self.assertEqual(3, benchmark["rows"][0][benchmark["fields"].index("case_count")])
        self.assertEqual(1.0, benchmark["rows"][0][benchmark["fields"].index("recall_at_3")])
        self.assertEqual(1.0, benchmark["rows"][0][benchmark["fields"].index("agent_task_context_use_rate")])

    def test_scope_filter_limits_memory_rows(self) -> None:
        self.repo.remember("project:feishu_ai_challenge", "生产部署必须加 --canary")
        self.repo.remember("project:other", "周报优先发飞书文档")

        payload = collect_sync_payload(self.conn, scope="project:other")
        ledger = payload["tables"]["ledger"]
        versions = payload["tables"]["versions"]

        self.assertEqual(1, len(ledger["rows"]))
        self.assertEqual("project:other", ledger["rows"][0][ledger["fields"].index("scope")])
        self.assertEqual(1, len(versions["rows"]))
        self.assertEqual("project:other", versions["rows"][0][versions["fields"].index("scope")])

    def test_candidate_review_rows_include_conflict_context(self) -> None:
        self.repo.remember("project:feishu_ai_challenge", "生产部署 region 固定 cn-shanghai。", source_type="test")
        service = CopilotService(repository=self.repo)
        created = handle_tool_request(
            "memory.create_candidate",
            {
                "text": "不对，生产部署 region 以后统一改成 ap-shanghai。",
                "scope": "project:feishu_ai_challenge",
                "source": {
                    "source_type": "test",
                    "source_id": "msg_conflict",
                    "actor_id": "ou_test",
                    "created_at": "2026-05-01T10:00:00+08:00",
                    "quote": "不对，生产部署 region 以后统一改成 ap-shanghai。",
                },
                "current_context": demo_permission_context(
                    "memory.create_candidate",
                    "project:feishu_ai_challenge",
                    actor_id="ou_test",
                    entrypoint="unit_test",
                ),
            },
            service=service,
        )
        self.assertTrue(created["ok"])

        payload = collect_sync_payload(self.conn, candidate_review_outputs=[created])
        review = payload["tables"]["candidate_review"]

        self.assertEqual(1, len(review["rows"]))
        row = review["rows"][0]
        self.assertIn("ap-shanghai", row[review["fields"].index("new_value")])
        self.assertIn("cn-shanghai", row[review["fields"].index("old_value")])
        self.assertEqual("manual_review_conflict", row[review["fields"].index("recommended_action")])
        self.assertEqual("req_memory_create_candidate", row[review["fields"].index("request_id")])
        self.assertEqual("trace_memory_create_candidate", row[review["fields"].index("trace_id")])
        self.assertEqual("allow", row[review["fields"].index("permission_decision")])

    def test_candidate_review_rows_redact_permission_denied_tool_output(self) -> None:
        service = CopilotService(repository=self.repo)
        created = handle_tool_request(
            "memory.create_candidate",
            {
                "text": "决定：Bitable dry-run 只能展示授权字段。",
                "scope": "project:feishu_ai_challenge",
                "source": {
                    "source_type": "test",
                    "source_id": "msg_denied_bitable",
                    "actor_id": "ou_test",
                    "created_at": "2026-05-07T10:00:00+08:00",
                    "quote": "决定：Bitable dry-run 只能展示授权字段。",
                },
                "current_context": demo_permission_context(
                    "memory.create_candidate",
                    "project:feishu_ai_challenge",
                    actor_id="ou_test",
                    entrypoint="unit_test",
                ),
            },
            service=service,
        )
        denied_context = demo_permission_context(
            "memory.reject",
            "project:feishu_ai_challenge",
            actor_id="ou_member",
            roles=["member"],
            entrypoint="unit_test",
        )
        denied_context["permission"]["request_id"] = "req_bitable_deny"
        denied_context["permission"]["trace_id"] = "trace_bitable_deny"
        denied = handle_tool_request(
            "memory.reject",
            {
                "candidate_id": created["candidate_id"],
                "scope": "project:feishu_ai_challenge",
                "current_context": denied_context,
            },
            service=service,
        )

        payload = collect_sync_payload(self.conn, candidate_review_outputs=[denied])
        review = payload["tables"]["candidate_review"]
        row = review["rows"][0]
        rendered = "\n".join(str(value) for value in row)

        self.assertFalse(denied["ok"])
        self.assertEqual("permission_denied", row[review["fields"].index("status")])
        self.assertEqual("", row[review["fields"].index("new_value")])
        self.assertEqual("", row[review["fields"].index("evidence")])
        self.assertEqual("deny", row[review["fields"].index("permission_decision")])
        self.assertEqual("review_role_required", row[review["fields"].index("permission_reason")])
        self.assertEqual("req_bitable_deny", row[review["fields"].index("request_id")])
        self.assertEqual("trace_bitable_deny", row[review["fields"].index("trace_id")])
        self.assertNotIn("授权字段", rendered)

    def test_schema_spec_includes_review_and_reminder_tables(self) -> None:
        tables = {table["name"]: table for table in table_schema_spec()["tables"]}

        self.assertIn("Candidate Review", tables)
        self.assertIn("Reminder Candidates", tables)
        self.assertIn("Benchmark Results", tables)
        benchmark_fields = {field["name"] for field in tables["Benchmark Results"]["fields"]}
        self.assertTrue(
            {
                "recall_at_3",
                "candidate_precision",
                "agent_task_context_use_rate",
                "l1_hot_recall_p95_ms",
                "sensitive_reminder_leakage_rate",
                "failure_type_counts",
                "recommended_fix_summary",
            }
            <= benchmark_fields
        )
        candidate_fields = {field["name"] for field in tables["Candidate Review"]["fields"]}
        self.assertTrue(
            {
                "status",
                "subject",
                "new_value",
                "old_value",
                "evidence",
                "risk_flags",
                "recommended_action",
                "request_id",
                "trace_id",
                "permission_decision",
                "permission_reason",
            }
            <= candidate_fields
        )
        reminder_fields = {field["name"] for field in tables["Reminder Candidates"]["fields"]}
        self.assertTrue({"reminder_id", "memory_id", "subject", "reason", "due_at", "recommended_action"} <= reminder_fields)

    def test_reminder_candidates_can_be_included_in_dry_run_payload(self) -> None:
        reminders = [
            {
                "reminder_id": "rem_mem_1_deadline",
                "memory_id": "mem_1",
                "scope": "project:feishu_ai_challenge",
                "subject": "提交材料",
                "current_value": "提交材料截止时间是 2026-05-07。",
                "reason": "任务前提醒",
                "status": "candidate",
                "due_at": "2026-05-07",
                "evidence": {"quote": "提交材料截止时间是 2026-05-07。"},
                "recommended_action": "review_reminder_candidate",
            }
        ]

        payload = collect_sync_payload(self.conn, reminder_candidates=reminders)
        table = payload["tables"]["reminder_candidates"]

        self.assertEqual(1, len(table["rows"]))
        row = table["rows"][0]
        self.assertEqual("rem_mem_1_deadline", row[table["fields"].index("reminder_id")])
        self.assertEqual("review_reminder_candidate", row[table["fields"].index("recommended_action")])


def setup_target():
    from memory_engine.bitable_sync import BitableTarget

    return BitableTarget(base_token="app_test")


if __name__ == "__main__":
    unittest.main()
