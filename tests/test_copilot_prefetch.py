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

SCOPE = "project:feishu_ai_challenge"


def current_context(*, intent: str = "生产部署", chat_id: str | None = None) -> dict[str, object]:
    source_context = {"entrypoint": "unit_test", "workspace_id": SCOPE}
    if chat_id:
        source_context["chat_id"] = chat_id
    return {
        "scope": SCOPE,
        "intent": intent,
        **({"chat_id": chat_id} if chat_id else {}),
        "allowed_scopes": [SCOPE],
        "permission": {
            "request_id": "req_memory_prefetch",
            "trace_id": "trace_memory_prefetch",
            "actor": {
                "user_id": "ou_test",
                "tenant_id": "tenant:demo",
                "organization_id": "org:demo",
                "roles": ["member", "reviewer"],
            },
            "source_context": source_context,
            "requested_action": "fmc_memory_prefetch",
            "requested_visibility": "team",
            "timestamp": "2026-05-07T00:00:00+08:00",
        },
    }


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
                "scope": SCOPE,
                "current_context": current_context(intent="准备今天的生产部署 checklist"),
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
        self.assertEqual([], pack["graph_context"]["related_people"])
        self.assertEqual(["L1", "L2", "L3"], pack["trace_summary"]["layers"])
        self.assertEqual("none", result["state_mutation"])

    def test_prefetch_includes_graph_context_for_related_chat_members(self) -> None:
        chat_id = "oc_prefetch_graph"
        ts = 1777600000000
        self.conn.execute(
            """
            INSERT INTO knowledge_graph_nodes (
              id, tenant_id, organization_id, node_type, node_key, label,
              visibility_policy, status, metadata_json, first_seen_at, last_seen_at
            )
            VALUES
              ('node_chat_prefetch_graph', 'tenant:demo', 'org:demo', 'feishu_chat', ?, 'prefetch graph chat', 'team', 'active', '{}', ?, ?),
              ('node_user_prefetch_graph', 'tenant:demo', 'org:demo', 'feishu_user', 'ou_prefetch_owner', 'prefetch owner', 'team', 'active', '{}', ?, ?)
            """,
            (chat_id, ts, ts, ts, ts),
        )
        self.conn.execute(
            """
            INSERT INTO knowledge_graph_edges (
              id, tenant_id, organization_id, source_node_id, target_node_id,
              edge_type, metadata_json, first_seen_at, last_seen_at
            )
            VALUES (
              'edge_user_chat_prefetch_graph', 'tenant:demo', 'org:demo',
              'node_user_prefetch_graph', 'node_chat_prefetch_graph',
              'member_of_feishu_chat', '{}', ?, ?
            )
            """,
            (ts, ts),
        )
        self.repo.remember(SCOPE, "生产部署必须加 --canary。", source_type="unit_test")

        result = handle_tool_request(
            "memory.prefetch",
            {
                "task": "生成生产部署 checklist",
                "scope": SCOPE,
                "current_context": current_context(intent="生产部署", chat_id=chat_id),
            },
            service=self.service,
        )

        self.assertTrue(result["ok"])
        graph_context = result["context_pack"]["graph_context"]
        self.assertEqual(chat_id, graph_context["source_chat_id"])
        self.assertEqual(["ou_prefetch_owner"], graph_context["related_people"])
        self.assertFalse(graph_context["raw_message_content_included"])

    def test_prefetch_denies_scope_mismatch(self) -> None:
        result = handle_tool_request(
            "memory.prefetch",
            {
                "task": "生成生产部署 checklist",
                "scope": SCOPE,
                "current_context": {"scope": "project:other"},
            },
            service=self.service,
        )

        self.assertFalse(result["ok"])
        self.assertEqual("permission_denied", result["error"]["code"])

    def test_prefetch_does_not_leak_superseded_value(self) -> None:
        self.repo.remember("project:feishu_ai_challenge", "生产部署 region 固定 cn-shanghai。", source_type="unit_test")
        self.repo.remember(
            "project:feishu_ai_challenge", "不对，生产部署 region 改成 ap-shanghai。", source_type="unit_test"
        )

        result = handle_tool_request(
            "memory.prefetch",
            {
                "task": "生成生产部署 checklist",
                "scope": SCOPE,
                "current_context": current_context(intent="生产部署 region 和发布参数"),
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
        self.assertEqual(20, result["summary"]["case_count"])
        self.assertEqual(18, result["summary"]["context_required_case_count"])
        self.assertEqual(1.0, result["summary"]["case_pass_rate"])
        self.assertEqual(1.0, result["summary"]["agent_task_context_use_rate"])
        self.assertEqual(1.0, result["summary"]["evidence_coverage"])
        self.assertEqual(0.0, result["summary"]["stale_leakage_rate"])
        self.assertIn("failure_type_counts", result["summary"])
        self.assertEqual({}, result["summary"]["failure_type_counts"])
        self.assertIn("actual_output_summary", result["results"][0])

    def test_prefetch_benchmark_allows_empty_context_when_no_memory_expected(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
            json.dump(
                [
                    {
                        "case_id": "prefetch_empty_unit",
                        "type": "copilot_prefetch",
                        "task": "调研一个全新方向",
                        "current_context": {"intent": "全新方向"},
                        "events": [],
                        "expected_memory_keyword": "",
                    }
                ],
                handle,
                ensure_ascii=False,
            )
            handle.flush()

            result = run_benchmark(handle.name)

        self.assertEqual(1.0, result["summary"]["case_pass_rate"])
        self.assertEqual(0, result["summary"]["context_required_case_count"])
        self.assertEqual(1.0, result["summary"]["agent_task_context_use_rate"])
        self.assertTrue(result["results"][0]["passed"])
        self.assertFalse(result["results"][0]["used_context"])


if __name__ == "__main__":
    unittest.main()
