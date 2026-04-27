from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memory_engine.benchmark import run_benchmark
from memory_engine.copilot.service import CopilotService
from memory_engine.copilot.tools import handle_tool_request
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository


class CopilotPrefetchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "memory.sqlite"
        self.conn = connect(self.db_path)
        init_db(self.conn)
        self.repo = MemoryRepository(self.conn)
        self.service = CopilotService(repository=self.repo)

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    def test_prefetch_returns_compact_context_pack_with_evidence_and_trace(self) -> None:
        self.repo.remember(
            "project:feishu_ai_challenge",
            "生产部署必须加 --canary --region ap-shanghai，上线前检查回滚脚本。",
            source_type="unit_test",
            source_id="msg_prefetch_1",
        )

        result = handle_tool_request(
            "memory.prefetch",
            {
                "task": "生成生产部署 checklist",
                "scope": "project:feishu_ai_challenge",
                "current_context": {
                    "scope": "project:feishu_ai_challenge",
                    "intent": "准备今天的生产部署 checklist",
                    "allowed_scopes": ["project:feishu_ai_challenge"],
                },
                "top_k": 5,
            },
            service=self.service,
        )

        self.assertTrue(result["ok"])
        pack = result["context_pack"]
        self.assertFalse(pack["raw_events_included"])
        self.assertTrue(pack["stale_superseded_filtered"])
        self.assertEqual(1, len(pack["relevant_memories"]))
        self.assertIn("--canary", pack["relevant_memories"][0]["current_value"])
        self.assertTrue(pack["relevant_memories"][0]["evidence"][0]["quote"])
        self.assertEqual(["L1", "L2", "L3"], pack["trace_summary"]["layers"])
        self.assertEqual("none", result["state_mutation"])

    def test_prefetch_denies_scope_mismatch(self) -> None:
        result = handle_tool_request(
            "memory.prefetch",
            {
                "task": "生成生产部署 checklist",
                "scope": "project:feishu_ai_challenge",
                "current_context": {"scope": "project:other"},
            },
            service=self.service,
        )

        self.assertFalse(result["ok"])
        self.assertEqual("permission_denied", result["error"]["code"])

    def test_prefetch_does_not_leak_superseded_value(self) -> None:
        self.repo.remember("project:feishu_ai_challenge", "生产部署 region 固定 cn-shanghai。", source_type="unit_test")
        self.repo.remember("project:feishu_ai_challenge", "不对，生产部署 region 改成 ap-shanghai。", source_type="unit_test")

        result = handle_tool_request(
            "memory.prefetch",
            {
                "task": "生成生产部署 checklist",
                "scope": "project:feishu_ai_challenge",
                "current_context": {"intent": "生产部署 region 和发布参数"},
            },
            service=self.service,
        )

        self.assertTrue(result["ok"])
        serialized = json.dumps(result["context_pack"], ensure_ascii=False)
        self.assertIn("ap-shanghai", serialized)
        self.assertNotIn("cn-shanghai", serialized)

    def test_prefetch_benchmark_runner_reports_context_use_rate(self) -> None:
        result = run_benchmark("benchmarks/copilot_prefetch_cases.json")

        self.assertEqual("copilot_prefetch", result["benchmark_type"])
        self.assertGreaterEqual(result["summary"]["case_count"], 5)
        self.assertEqual(1.0, result["summary"]["agent_task_context_use_rate"])
        self.assertEqual(0.0, result["summary"]["stale_leakage_rate"])
        self.assertEqual({}, result["summary"]["failure_type_counts"])
        self.assertIn("actual_output_summary", result["results"][0])


if __name__ == "__main__":
    unittest.main()
