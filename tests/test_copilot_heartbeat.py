from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memory_engine.benchmark import run_benchmark
from memory_engine.copilot.heartbeat import HeartbeatReminderEngine, agent_run_summary_candidate
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository


SCOPE = "project:feishu_ai_challenge"


def current_context(**values: str) -> dict[str, object]:
    context: dict[str, object] = {
        "scope": SCOPE,
        "permission": {
            "request_id": "req_heartbeat_search",
            "trace_id": "trace_heartbeat_search",
            "actor": {
                "user_id": "ou_test",
                "tenant_id": "tenant:demo",
                "organization_id": "org:demo",
                "roles": ["member", "reviewer"],
            },
            "source_context": {"entrypoint": "heartbeat", "workspace_id": SCOPE},
            "requested_action": "memory.search",
            "requested_visibility": "team",
            "timestamp": "2026-05-07T00:00:00+08:00",
        },
    }
    context.update(values)
    return context


class CopilotHeartbeatTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "memory.sqlite"
        self.conn = connect(self.db_path)
        init_db(self.conn)
        self.repo = MemoryRepository(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    def test_heartbeat_generates_deadline_reminder_candidate(self) -> None:
        self.repo.remember(
            "project:feishu_ai_challenge",
            "提交材料截止时间是 2026-05-07，必须提前准备录屏。",
            source_type="unit_test",
        )

        result = HeartbeatReminderEngine(self.repo).generate(
            scope=SCOPE,
            current_context=current_context(intent="准备初赛提交材料"),
        )

        self.assertTrue(result["ok"])
        self.assertEqual("deadline", result["candidates"][0]["trigger"])
        self.assertEqual("candidate", result["candidates"][0]["status"])
        self.assertEqual("none", result["candidates"][0]["state_mutation"])

    def test_heartbeat_covers_thread_similarity_without_mutation(self) -> None:
        self.repo.remember(
            "project:feishu_ai_challenge",
            "Demo 讲解词偏好：先讲用户痛点，再讲 Agent 自动调用记忆工具。",
            source_type="unit_test",
        )

        result = HeartbeatReminderEngine(self.repo, review_due_ms=999999999999).generate(
            scope=SCOPE,
            current_context=current_context(thread_topic="Demo 讲解词"),
        )

        self.assertTrue(result["ok"])
        self.assertEqual("thread_similarity", result["candidates"][0]["trigger"])
        self.assertEqual("none", result["trace"]["state_mutation"])

    def test_heartbeat_redacts_sensitive_reminder_text(self) -> None:
        self.repo.remember(
            "project:feishu_ai_challenge",
            "OpenAPI 调试风险：api_key=abcdefghi123456789 只能放本地环境。",
            source_type="unit_test",
        )

        result = HeartbeatReminderEngine(self.repo).generate(
            scope=SCOPE,
            current_context=current_context(intent="OpenAPI 调试"),
        )

        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("abcdefghi123456789", serialized)
        self.assertIn("[REDACTED:api_key]", serialized)
        self.assertIn("sensitive_content", result["candidates"][0]["risk_flags"])

    def test_agent_run_summary_candidate_is_dry_run_only(self) -> None:
        candidate = agent_run_summary_candidate(
            task="生成 demo checklist",
            scope="project:feishu_ai_challenge",
            used_memory_ids=["mem_1"],
            missing_context=["缺少录屏路径"],
            new_candidate_hint="以后 Demo 讲解词先讲用户痛点。",
        )

        self.assertTrue(candidate["ok"])
        self.assertEqual("candidate", candidate["status"])
        self.assertEqual("none", candidate["state_mutation"])
        self.assertEqual(["mem_1"], candidate["used_memory_ids"])

    def test_heartbeat_benchmark_runner_reports_sensitive_leakage_zero(self) -> None:
        result = run_benchmark("benchmarks/copilot_heartbeat_cases.json")

        self.assertEqual("copilot_heartbeat", result["benchmark_type"])
        self.assertGreaterEqual(result["summary"]["case_count"], 5)
        self.assertEqual(0.0, result["summary"]["sensitive_reminder_leakage_rate"])
        self.assertEqual(1.0, result["summary"]["reminder_candidate_rate"])
        self.assertEqual({}, result["summary"]["failure_type_counts"])
        self.assertIn("actual_output_summary", result["results"][0])


if __name__ == "__main__":
    unittest.main()
