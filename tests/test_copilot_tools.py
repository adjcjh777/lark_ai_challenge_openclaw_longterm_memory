from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memory_engine.copilot.service import CopilotService
from memory_engine.copilot.tools import handle_tool_request, supported_tool_names, validate_tool_request
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository


SCHEMA_PATH = Path("agent_adapters/openclaw/memory_tools.schema.json")
EXAMPLES_DIR = Path("agent_adapters/openclaw/examples")


class CopilotToolContractTest(unittest.TestCase):
    def test_openclaw_schema_lists_supported_tools(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        schema_tools = sorted(tool["name"] for tool in schema["tools"])

        self.assertEqual("2026.4.24", schema["openclaw_version"])
        self.assertEqual(supported_tool_names(), schema_tools)

    def test_schema_matches_parser_edge_contracts(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        tools = {tool["name"]: tool["input_schema"] for tool in schema["tools"]}

        search_filters = tools["memory.search"]["properties"]["filters"]
        self.assertFalse(search_filters["additionalProperties"])

        prefetch_context = tools["memory.prefetch"]["properties"]["current_context"]
        self.assertEqual(1, prefetch_context["minProperties"])

    def test_validate_tool_request_accepts_search_payload(self) -> None:
        result = validate_tool_request(
            "memory.search",
            {
                "query": "production deployment region",
                "scope": "project:feishu_ai_challenge",
                "top_k": 3,
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual("memory.search", result["tool"])
        self.assertIn("parsed_request", result)
        self.assertNotIn("results", result)
        self.assertEqual("active", result["parsed_request"]["filters"]["status"])

    def test_validate_tool_request_uses_standard_error_shape(self) -> None:
        result = validate_tool_request("memory.search", {"query": "deployment"})

        self.assertFalse(result["ok"])
        self.assertEqual("validation_error", result["error"]["code"])
        self.assertFalse(result["error"]["retryable"])
        self.assertEqual({"tool": "memory.search"}, result["error"]["details"])

    def test_handle_memory_search_returns_scope_required_before_validation(self) -> None:
        result = handle_tool_request("memory.search", {"query": "deployment"})

        self.assertFalse(result["ok"])
        self.assertEqual("scope_required", result["error"]["code"])
        self.assertEqual({"tool": "memory.search"}, result["error"]["details"])

    def test_handle_memory_search_denies_context_scope_mismatch(self) -> None:
        result = handle_tool_request(
            "memory.search",
            {
                "query": "deployment",
                "scope": "project:feishu_ai_challenge",
                "current_context": {"scope": "project:other"},
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual("permission_denied", result["error"]["code"])

    def test_handle_memory_search_rejects_unsupported_layer(self) -> None:
        result = handle_tool_request(
            "memory.search",
            {
                "query": "deployment",
                "scope": "project:feishu_ai_challenge",
                "filters": {"layer": "L4"},
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual("validation_error", result["error"]["code"])
        self.assertIn("filters.layer", result["error"]["message"])

    def test_handle_memory_search_status_filter_does_not_leak_old_values(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_tools_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(
                "project:feishu_ai_challenge",
                "生产部署必须加 --canary --region cn-shanghai",
                source_type="unit_test",
            )

            result = handle_tool_request(
                "memory.search",
                {
                    "query": "生产部署参数",
                    "scope": "project:feishu_ai_challenge",
                    "filters": {"status": "superseded"},
                },
                service=CopilotService(repository=repo),
            )
            conn.close()

        self.assertTrue(result["ok"])
        self.assertEqual([], result["results"])
        self.assertEqual("no_active_memory_with_evidence", result["trace"]["final_reason"])
        self.assertEqual("default_search_excludes_non_active_memory", result["trace"]["steps"][1]["note"])

    def test_handle_memory_search_no_result_keeps_ok_trace_shape(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_tools_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            result = handle_tool_request(
                "memory.search",
                {
                    "query": "不存在的部署规则",
                    "scope": "project:feishu_ai_challenge",
                },
                service=CopilotService(repository=MemoryRepository(conn)),
            )
            conn.close()

        self.assertTrue(result["ok"])
        self.assertEqual([], result["results"])
        self.assertEqual("no_active_memory_with_evidence", result["trace"]["final_reason"])
        self.assertEqual(["L1", "L2", "L3"], result["trace"]["layers"])

    def test_handle_memory_search_uses_hybrid_retrieval_over_repository_data(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_tools_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(
                "project:feishu_ai_challenge",
                "生产部署必须加 --canary --region cn-shanghai",
                source_type="unit_test",
            )

            result = handle_tool_request(
                "memory.search",
                {
                    "query": "生产部署参数",
                    "scope": "project:feishu_ai_challenge",
                    "top_k": 3,
                },
                service=CopilotService(repository=repo),
            )
            conn.close()

        self.assertTrue(result["ok"])
        self.assertEqual("project:feishu_ai_challenge", result["scope"])
        self.assertEqual(1, len(result["results"]))
        self.assertEqual("active", result["results"][0]["status"])
        self.assertEqual("生产部署", result["results"][0]["subject"])
        self.assertIn("--canary", result["results"][0]["current_value"])
        self.assertIn(result["results"][0]["layer"], {"L1", "L2"})
        self.assertTrue(result["results"][0]["evidence"][0]["quote"])
        self.assertIn("matched_via", result["results"][0])
        self.assertIn("why_ranked", result["results"][0])
        self.assertEqual("L0->L1->L2->L3->merge->rerank->top_k", result["trace"]["strategy"])
        self.assertEqual("hybrid_retrieval", result["trace"]["backend"])
        self.assertIn("L1", result["trace"]["layers"])
        self.assertIn("keyword", result["trace"]["stages"])
        self.assertFalse(result["trace"]["fallback_used"])

    def test_handle_memory_search_keeps_tools_layer_thin_with_injected_service(self) -> None:
        class StubService:
            def search(self, request):
                return {"ok": True, "query": request.query, "scope": request.scope, "results": [], "trace": {"strategy": "stub"}}

        result = handle_tool_request(
            "memory.search",
            {"query": "部署参数", "scope": "project:feishu_ai_challenge"},
            service=StubService(),  # type: ignore[arg-type]
        )

        self.assertTrue(result["ok"])
        self.assertEqual("stub", result["trace"]["strategy"])

    def test_handle_candidate_confirm_reject_tools(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_tools_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            service = CopilotService(repository=MemoryRepository(conn))

            created = handle_tool_request(
                "memory.create_candidate",
                {
                    "text": "决定：生产部署必须加 --canary --region cn-shanghai。",
                    "scope": "project:feishu_ai_challenge",
                    "source": {
                        "source_type": "unit_test",
                        "source_id": "msg_1",
                        "actor_id": "ou_test",
                        "created_at": "2026-04-30T10:00:00+08:00",
                        "quote": "决定：生产部署必须加 --canary --region cn-shanghai。",
                    },
                },
                service=service,
            )
            self.assertTrue(created["ok"])
            self.assertEqual("candidate", created["candidate"]["status"])

            confirmed = handle_tool_request(
                "memory.confirm",
                {
                    "candidate_id": created["candidate_id"],
                    "scope": "project:feishu_ai_challenge",
                    "actor_id": "ou_test",
                    "reason": "单测确认",
                },
                service=service,
            )
            self.assertTrue(confirmed["ok"])
            self.assertEqual("active", confirmed["memory"]["status"])

            rejected = handle_tool_request(
                "memory.reject",
                {
                    "candidate_id": created["candidate_id"],
                    "scope": "project:feishu_ai_challenge",
                    "actor_id": "ou_test",
                    "reason": "重复拒绝",
                },
                service=service,
            )
            conn.close()

        self.assertFalse(rejected["ok"])
        self.assertEqual("candidate_not_confirmable", rejected["error"]["code"])

    def test_handle_explain_versions_returns_active_and_superseded_chain(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_tools_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            service = CopilotService(repository=repo)
            repo.remember(
                "project:feishu_ai_challenge",
                "生产部署 region 固定 cn-shanghai。",
                source_type="unit_test",
            )
            created = handle_tool_request(
                "memory.create_candidate",
                {
                    "text": "不对，生产部署 region 以后统一改成 ap-shanghai。",
                    "scope": "project:feishu_ai_challenge",
                    "source": {
                        "source_type": "unit_test",
                        "source_id": "msg_conflict",
                        "actor_id": "ou_test",
                        "created_at": "2026-05-01T10:00:00+08:00",
                        "quote": "不对，生产部署 region 以后统一改成 ap-shanghai。",
                    },
                },
                service=service,
            )
            handle_tool_request(
                "memory.confirm",
                {
                    "candidate_id": created["candidate_id"],
                    "scope": "project:feishu_ai_challenge",
                    "actor_id": "ou_test",
                },
                service=service,
            )
            explained = handle_tool_request(
                "memory.explain_versions",
                {
                    "memory_id": created["memory_id"],
                    "scope": "project:feishu_ai_challenge",
                },
                service=service,
            )
            conn.close()

        self.assertTrue(explained["ok"])
        self.assertEqual("memory.explain_versions", explained["tool"])
        self.assertIn("ap-shanghai", explained["active_version"]["value"])
        self.assertEqual(["active", "superseded"], sorted({item["status"] for item in explained["versions"]}))
        self.assertTrue(explained["supersedes"])

    def test_examples_only_use_declared_tools(self) -> None:
        supported = set(supported_tool_names())
        example_paths = sorted(EXAMPLES_DIR.glob("*.json"))

        self.assertGreaterEqual(len(example_paths), 3)
        for path in example_paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for step in payload["steps"]:
                self.assertIn(step["tool"], supported, msg=str(path))


if __name__ == "__main__":
    unittest.main()
