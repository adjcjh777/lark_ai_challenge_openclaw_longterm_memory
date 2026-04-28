from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from memory_engine.copilot.service import CopilotService
from memory_engine.copilot.tools import handle_tool_request, supported_tool_names, validate_tool_request
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository

SCHEMA_PATH = Path("agent_adapters/openclaw/memory_tools.schema.json")
EXAMPLES_DIR = Path("agent_adapters/openclaw/examples")
SCOPE = "project:feishu_ai_challenge"


def current_context(action: str, *, roles: list[str] | None = None) -> dict[str, object]:
    return {
        "scope": SCOPE,
        "permission": {
            "request_id": f"req_{action.replace('.', '_')}",
            "trace_id": f"trace_{action.replace('.', '_')}",
            "actor": {
                "user_id": "ou_test",
                "tenant_id": "tenant:demo",
                "organization_id": "org:demo",
                "roles": roles if roles is not None else ["member", "reviewer"],
            },
            "source_context": {"entrypoint": "openclaw", "workspace_id": SCOPE},
            "requested_action": action,
            "requested_visibility": "team",
            "timestamp": "2026-05-07T00:00:00+08:00",
        },
    }


class CopilotToolContractTest(unittest.TestCase):
    def test_openclaw_schema_lists_supported_tools(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        schema_tools = sorted(tool["name"] for tool in schema["tools"])

        self.assertEqual("2026-05-07", schema["version"])
        self.assertEqual("2026.4.24", schema["openclaw_version"])
        # Schema uses OpenClaw-facing names (fmc_ prefix); map to Python-side names
        openclaw_to_python = {
            "fmc_memory_search": "memory.search",
            "fmc_memory_create_candidate": "memory.create_candidate",
            "fmc_memory_confirm": "memory.confirm",
            "fmc_memory_reject": "memory.reject",
            "fmc_memory_explain_versions": "memory.explain_versions",
            "fmc_memory_prefetch": "memory.prefetch",
            "fmc_heartbeat_review_due": "heartbeat.review_due",
        }
        python_tools = sorted(openclaw_to_python.get(t, t) for t in schema_tools)
        self.assertEqual(supported_tool_names(), python_tools)

    def test_schema_matches_parser_edge_contracts(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        # Schema uses OpenClaw-facing names (fmc_ prefix)
        tools = {tool["name"]: tool["input_schema"] for tool in schema["tools"]}

        search_filters = tools["fmc_memory_search"]["properties"]["filters"]
        self.assertFalse(search_filters["additionalProperties"])

        prefetch_context = tools["fmc_memory_prefetch"]["properties"]["current_context"]
        self.assertEqual(1, prefetch_context["minProperties"])

        # Map Python-side names to OpenClaw-facing names for schema lookups
        python_to_openclaw = {
            "memory.search": "fmc_memory_search",
            "memory.create_candidate": "fmc_memory_create_candidate",
            "memory.confirm": "fmc_memory_confirm",
            "memory.reject": "fmc_memory_reject",
            "memory.explain_versions": "fmc_memory_explain_versions",
            "memory.prefetch": "fmc_memory_prefetch",
            "heartbeat.review_due": "fmc_heartbeat_review_due",
        }
        schema_tools_by_name = {tool["name"]: tool for tool in schema["tools"]}
        for tool_name in supported_tool_names():
            schema_name = python_to_openclaw.get(tool_name, tool_name)
            self.assertIn("current_context", tools[schema_name]["required"])
            self.assertIn("output_schema", schema_tools_by_name[schema_name])

        current_context = schema["$defs"]["current_context"]
        self.assertEqual(["permission"], current_context["required"])

        bridge = schema["$defs"]["bridge_metadata"]
        self.assertEqual("openclaw_tool", bridge["properties"]["entrypoint"]["const"])
        self.assertIn("permission_decision", bridge["required"])
        self.assertIn("bridge", schema["$defs"]["search_output"]["required"])
        self.assertIn("bridge", schema["$defs"]["tool_output"]["required"])
        self.assertIn("bridge", schema["error_schema"]["properties"])

    def test_validate_tool_request_accepts_search_payload(self) -> None:
        result = validate_tool_request(
            "memory.search",
            {
                "query": "production deployment region",
                "scope": SCOPE,
                "top_k": 3,
                "current_context": current_context("memory.search"),
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual("memory.search", result["tool"])
        self.assertIn("parsed_request", result)
        self.assertNotIn("results", result)
        self.assertEqual("active", result["parsed_request"]["filters"]["status"])

    def test_validate_tool_request_accepts_heartbeat_payload(self) -> None:
        result = validate_tool_request(
            "heartbeat.review_due",
            {
                "scope": SCOPE,
                "current_context": current_context("heartbeat.review_due"),
                "limit": 3,
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual("heartbeat.review_due", result["tool"])
        self.assertEqual(3, result["parsed_request"]["limit"])

    def test_handle_heartbeat_review_due_returns_candidate_only_output(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_tools_heartbeat_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(SCOPE, "提交材料截止时间是 2026-05-07，必须提前准备录屏。", source_type="unit_test")
            result = handle_tool_request(
                "heartbeat.review_due",
                {
                    "scope": SCOPE,
                    "current_context": current_context("heartbeat.review_due"),
                },
                service=CopilotService(repository=repo),
            )
            active_count = conn.execute("SELECT COUNT(*) AS count FROM memories WHERE status = 'active'").fetchone()[
                "count"
            ]
            candidate_count = conn.execute(
                "SELECT COUNT(*) AS count FROM memories WHERE status = 'candidate'"
            ).fetchone()["count"]
            conn.close()

        self.assertTrue(result["ok"])
        self.assertEqual("dry_run", result["status"])
        self.assertEqual("candidate", result["candidates"][0]["status"])
        self.assertEqual("none", result["candidates"][0]["state_mutation"])
        self.assertEqual(1, active_count)
        self.assertEqual(0, candidate_count)

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
                    "scope": SCOPE,
                    "current_context": current_context("memory.search"),
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
                    "scope": SCOPE,
                    "current_context": current_context("memory.search"),
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
                    "scope": SCOPE,
                    "top_k": 3,
                    "current_context": current_context("memory.search"),
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
        self.assertEqual(
            {
                "entrypoint": "openclaw_tool",
                "tool": "fmc_memory_search",
                "request_id": "req_memory_search",
                "trace_id": "trace_memory_search",
            },
            {
                "entrypoint": result["bridge"]["entrypoint"],
                "tool": result["bridge"]["tool"],
                "request_id": result["bridge"]["request_id"],
                "trace_id": result["bridge"]["trace_id"],
            },
        )
        self.assertEqual("allow", result["bridge"]["permission_decision"]["decision"])
        self.assertEqual("scope_access_granted", result["bridge"]["permission_decision"]["reason_code"])
        self.assertEqual("fmc_memory_search", result["bridge"]["permission_decision"]["requested_action"])
        self.assertEqual("team", result["bridge"]["permission_decision"]["requested_visibility"])
        self.assertEqual("ou_test", result["bridge"]["permission_decision"]["actor"]["user_id"])
        self.assert_search_output_matches_schema(result)

    def test_handle_memory_search_keeps_tools_layer_thin_with_injected_service(self) -> None:
        class StubService:
            def search(self, request):
                return {
                    "ok": True,
                    "query": request.query,
                    "scope": request.scope,
                    "results": [],
                    "trace": {"strategy": "stub"},
                }

        result = handle_tool_request(
            "memory.search",
            {
                "query": "部署参数",
                "scope": "project:feishu_ai_challenge",
                "current_context": current_context("memory.search"),
            },
            service=StubService(),  # type: ignore[arg-type]
        )

        self.assertTrue(result["ok"])
        self.assertEqual("stub", result["trace"]["strategy"])
        self.assertEqual("openclaw_tool", result["bridge"]["entrypoint"])
        self.assertEqual("fmc_memory_search", result["bridge"]["tool"])

    def test_handle_tool_request_bridges_all_mvp_actions_through_one_entrypoint(self) -> None:
        class StubService:
            def __init__(self) -> None:
                self.called: list[str] = []

            def search(self, request):
                self.called.append("memory.search")
                return {"ok": True, "results": [], "trace": {"strategy": "stub"}}

            def create_candidate(self, request):
                self.called.append("memory.create_candidate")
                return {"ok": True, "candidate_id": "cand_stub", "candidate": {"status": "candidate"}}

            def confirm(self, request):
                self.called.append("memory.confirm")
                return {"ok": True, "memory_id": "mem_stub", "memory": {"status": "active"}}

            def reject(self, request):
                self.called.append("memory.reject")
                return {"ok": True, "candidate_id": "cand_stub", "status": "rejected"}

            def explain_versions(self, request):
                self.called.append("memory.explain_versions")
                return {"ok": True, "versions": [], "active_version": None}

            def prefetch(self, request):
                self.called.append("memory.prefetch")
                return {"ok": True, "context_pack": {"relevant_memories": []}, "state_mutation": "none"}

            def heartbeat_review_due(self, request):
                self.called.append("heartbeat.review_due")
                return {"ok": True, "status": "dry_run", "candidates": [], "trace": {"state_mutation": "none"}}

        service = StubService()
        payloads = {
            "memory.search": {"query": "部署参数", "scope": SCOPE, "current_context": current_context("memory.search")},
            "memory.create_candidate": {
                "text": "决定：生产部署必须加 --canary。",
                "scope": SCOPE,
                "source": {
                    "source_type": "unit_test",
                    "source_id": "msg_bridge",
                    "actor_id": "ou_test",
                    "created_at": "2026-05-07T10:00:00+08:00",
                    "quote": "决定：生产部署必须加 --canary。",
                },
                "current_context": current_context("memory.create_candidate"),
            },
            "memory.confirm": {
                "candidate_id": "cand_stub",
                "scope": SCOPE,
                "current_context": current_context("memory.confirm"),
            },
            "memory.reject": {
                "candidate_id": "cand_stub",
                "scope": SCOPE,
                "current_context": current_context("memory.reject"),
            },
            "memory.explain_versions": {
                "memory_id": "mem_stub",
                "scope": SCOPE,
                "current_context": current_context("memory.explain_versions"),
            },
            "memory.prefetch": {
                "task": "生成部署 checklist",
                "scope": SCOPE,
                "current_context": current_context("memory.prefetch"),
            },
            "heartbeat.review_due": {
                "scope": SCOPE,
                "current_context": current_context("heartbeat.review_due"),
            },
        }

        python_to_openclaw = {
            "memory.search": "fmc_memory_search",
            "memory.create_candidate": "fmc_memory_create_candidate",
            "memory.confirm": "fmc_memory_confirm",
            "memory.reject": "fmc_memory_reject",
            "memory.explain_versions": "fmc_memory_explain_versions",
            "memory.prefetch": "fmc_memory_prefetch",
            "heartbeat.review_due": "fmc_heartbeat_review_due",
        }

        for tool_name, payload in payloads.items():
            with self.subTest(tool_name=tool_name):
                result = handle_tool_request(tool_name, payload, service=service)  # type: ignore[arg-type]
                self.assertTrue(result["ok"])
                schema_name = python_to_openclaw.get(tool_name, tool_name)
                self.assertEqual(schema_name, result["bridge"]["tool"])
                self.assertEqual("openclaw_tool", result["bridge"]["entrypoint"])
                self.assertEqual(f"req_{tool_name.replace('.', '_')}", result["bridge"]["request_id"])
                self.assertEqual(f"trace_{tool_name.replace('.', '_')}", result["bridge"]["trace_id"])
                self.assertEqual("allow", result["bridge"]["permission_decision"]["decision"])
                self.assert_bridge_matches_schema(result, tool_name)

        self.assertEqual(supported_tool_names(), sorted(service.called))

    def test_handle_tool_request_bridge_marks_permission_denials(self) -> None:
        result = handle_tool_request(
            "memory.search",
            {
                "query": "部署参数",
                "scope": SCOPE,
                "current_context": {
                    "permission": {
                        "request_id": "req_bad_permission",
                        "trace_id": "trace_bad_permission",
                    }
                },
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual("permission_denied", result["error"]["code"])
        self.assertEqual("deny", result["bridge"]["permission_decision"]["decision"])
        self.assertEqual("malformed_permission_context", result["bridge"]["permission_decision"]["reason_code"])
        self.assertEqual("req_bad_permission", result["bridge"]["request_id"])
        self.assertEqual("trace_bad_permission", result["bridge"]["trace_id"])
        self.assert_error_output_matches_schema(result)

    def test_feishu_source_auto_confirm_is_ignored_and_stays_candidate(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_tools_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            service = CopilotService(repository=MemoryRepository(conn))

            result = handle_tool_request(
                "memory.create_candidate",
                {
                    "text": "决定：生产部署必须加 --canary --region cn-shanghai。",
                    "scope": SCOPE,
                    "source": {
                        "source_type": "document_feishu",
                        "source_id": "doc_token#candidate-1",
                        "actor_id": "ou_test",
                        "created_at": "2026-05-07T10:00:00+08:00",
                        "quote": "决定：生产部署必须加 --canary --region cn-shanghai。",
                        "source_doc_id": "doc_token",
                    },
                    "auto_confirm": True,
                    "current_context": current_context("memory.create_candidate"),
                },
                service=service,
            )
            active_count = conn.execute("SELECT COUNT(*) AS count FROM memories WHERE status = 'active'").fetchone()[
                "count"
            ]
            candidate_count = conn.execute(
                "SELECT COUNT(*) AS count FROM memories WHERE status = 'candidate'"
            ).fetchone()["count"]
            conn.close()

        self.assertTrue(result["ok"])
        self.assertEqual("created", result["action"])
        self.assertEqual("candidate", result["status"])
        self.assertTrue(result["auto_confirm_ignored"])
        self.assertEqual("feishu_source_candidate_only", result["candidate_only_reason"])
        self.assertEqual(0, active_count)
        self.assertEqual(1, candidate_count)

    def test_handle_tool_request_omits_schema_unsafe_malformed_permission_fields(self) -> None:
        result = handle_tool_request(
            "memory.search",
            {
                "query": "部署参数",
                "scope": SCOPE,
                "current_context": {
                    "scope": SCOPE,
                    "permission": {
                        "request_id": "req_bad_visibility",
                        "trace_id": "trace_bad_visibility",
                        "actor": {
                            "user_id": "ou_test",
                            "tenant_id": "tenant:demo",
                            "organization_id": "org:demo",
                            "roles": ["member", "reviewer"],
                        },
                        "source_context": {"entrypoint": "openclaw", "workspace_id": SCOPE},
                        "requested_action": "memory.search",
                        "requested_visibility": "secret",
                        "timestamp": "2026-05-07T00:00:00+08:00",
                    },
                },
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual("permission_denied", result["error"]["code"])
        self.assertEqual("malformed_permission_context", result["error"]["details"]["reason_code"])
        self.assertEqual("deny", result["bridge"]["permission_decision"]["decision"])
        self.assertNotIn("requested_visibility", result["bridge"]["permission_decision"])
        self.assert_error_output_matches_schema(result)

    def test_handle_tool_request_omits_schema_unsafe_malformed_actor_fields(self) -> None:
        result = handle_tool_request(
            "memory.search",
            {
                "query": "部署参数",
                "scope": SCOPE,
                "current_context": {
                    "scope": SCOPE,
                    "permission": {
                        "request_id": "req_bad_actor",
                        "trace_id": "trace_bad_actor",
                        "actor": {
                            "user_id": {"nested": "bad"},
                            "tenant_id": 123,
                            "organization_id": "org:demo",
                            "roles": [1, "reviewer"],
                        },
                        "source_context": {"entrypoint": "openclaw", "workspace_id": SCOPE},
                        "requested_action": "memory.search",
                        "requested_visibility": "team",
                        "timestamp": "2026-05-07T00:00:00+08:00",
                    },
                },
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual("permission_denied", result["error"]["code"])
        self.assertEqual("malformed_permission_context", result["error"]["details"]["reason_code"])
        self.assertEqual("deny", result["bridge"]["permission_decision"]["decision"])
        self.assertEqual({"organization_id": "org:demo"}, result["bridge"]["permission_decision"]["actor"])
        self.assert_error_output_matches_schema(result)

    def test_handle_tool_request_auto_generates_default_permission_when_missing(self) -> None:
        """When permission context is missing, auto-generated default (member role) is used.
        Confirm/reject still require reviewer role."""
        ok_payloads = {
            "memory.search": {"query": "部署参数", "scope": SCOPE},
            "memory.create_candidate": {
                "text": "决定：生产部署必须加 --canary。",
                "scope": SCOPE,
                "source": {
                    "source_type": "unit_test",
                    "source_id": "msg_missing_permission",
                    "actor_id": "ou_test",
                    "created_at": "2026-05-07T10:00:00+08:00",
                    "quote": "决定：生产部署必须加 --canary。",
                },
            },
            "memory.prefetch": {
                "task": "生成部署 checklist",
                "scope": SCOPE,
                "current_context": {"scope": SCOPE},
            },
        }
        for tool_name, payload in ok_payloads.items():
            with self.subTest(tool_name=tool_name):
                result = handle_tool_request(tool_name, payload)
                self.assertTrue(result["ok"], f"{tool_name}: {result}")

        # Confirm/reject require reviewer role; auto-generated context only has member
        review_payloads = {
            "memory.confirm": {"candidate_id": "cand_missing_permission", "scope": SCOPE},
            "memory.reject": {"candidate_id": "cand_missing_permission", "scope": SCOPE},
        }
        for tool_name, payload in review_payloads.items():
            with self.subTest(tool_name=tool_name):
                result = handle_tool_request(tool_name, payload)
                self.assertFalse(result["ok"])
                self.assertEqual("permission_denied", result["error"]["code"])
                self.assertEqual("review_role_required", result["error"]["details"]["reason_code"])

    def test_handle_prefetch_keeps_tools_layer_thin_with_injected_service(self) -> None:
        class StubService:
            def prefetch(self, request):
                return {
                    "ok": True,
                    "tool": "memory.prefetch",
                    "task": request.task,
                    "scope": request.scope,
                    "context_pack": {"relevant_memories": []},
                }

        result = handle_tool_request(
            "memory.prefetch",
            {
                "task": "生成部署 checklist",
                "scope": "project:feishu_ai_challenge",
                "current_context": current_context("memory.prefetch"),
            },
            service=StubService(),  # type: ignore[arg-type]
        )

        self.assertTrue(result["ok"])
        self.assertEqual("memory.prefetch", result["tool"])
        self.assertEqual("生成部署 checklist", result["task"])

    def test_handle_prefetch_missing_scope_uses_scope_required_error(self) -> None:
        result = handle_tool_request(
            "memory.prefetch",
            {
                "task": "生成部署 checklist",
                "current_context": {"intent": "生产部署"},
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual("scope_required", result["error"]["code"])
        self.assertEqual({"tool": "memory.prefetch"}, result["error"]["details"])

    def test_handle_candidate_confirm_reject_tools(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_tools_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            service = CopilotService(repository=MemoryRepository(conn))

            created = handle_tool_request(
                "memory.create_candidate",
                {
                    "text": "决定：生产部署必须加 --canary --region cn-shanghai。",
                    "scope": SCOPE,
                    "source": {
                        "source_type": "unit_test",
                        "source_id": "msg_1",
                        "actor_id": "ou_test",
                        "created_at": "2026-04-30T10:00:00+08:00",
                        "quote": "决定：生产部署必须加 --canary --region cn-shanghai。",
                    },
                    "current_context": current_context("memory.create_candidate"),
                },
                service=service,
            )
            self.assertTrue(created["ok"])
            self.assertEqual("candidate", created["candidate"]["status"])

            confirmed = handle_tool_request(
                "memory.confirm",
                {
                    "candidate_id": created["candidate_id"],
                    "scope": SCOPE,
                    "actor_id": "ou_test",
                    "reason": "单测确认",
                    "current_context": current_context("memory.confirm"),
                },
                service=service,
            )
            self.assertTrue(confirmed["ok"])
            self.assertEqual("active", confirmed["memory"]["status"])

            rejected = handle_tool_request(
                "memory.reject",
                {
                    "candidate_id": created["candidate_id"],
                    "scope": SCOPE,
                    "actor_id": "ou_test",
                    "reason": "重复拒绝",
                    "current_context": current_context("memory.reject"),
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
                    "scope": SCOPE,
                    "source": {
                        "source_type": "unit_test",
                        "source_id": "msg_conflict",
                        "actor_id": "ou_test",
                        "created_at": "2026-05-01T10:00:00+08:00",
                        "quote": "不对，生产部署 region 以后统一改成 ap-shanghai。",
                    },
                    "current_context": current_context("memory.create_candidate"),
                },
                service=service,
            )
            handle_tool_request(
                "memory.confirm",
                {
                    "candidate_id": created["candidate_id"],
                    "scope": SCOPE,
                    "actor_id": "ou_test",
                    "current_context": current_context("memory.confirm"),
                },
                service=service,
            )
            explained = handle_tool_request(
                "memory.explain_versions",
                {
                    "memory_id": created["memory_id"],
                    "scope": SCOPE,
                    "current_context": current_context("memory.explain_versions"),
                },
                service=service,
            )
            conn.close()

        self.assertTrue(explained["ok"])
        self.assertEqual("memory.explain_versions", explained["tool"])
        self.assertIn("ap-shanghai", explained["active_version"]["value"])
        self.assertEqual(["active", "superseded"], sorted({item["status"] for item in explained["versions"]}))
        self.assertTrue(explained["supersedes"])

    def assert_search_output_matches_schema(self, response: dict[str, Any]) -> None:
        schema = self.schema()
        search_output = schema["$defs"]["search_output"]
        for field in search_output["required"]:
            self.assertIn(field, response)
        self.assertTrue(response["ok"])
        self.assertEqual(set(response) - set(search_output["properties"]), set())
        self.assert_bridge_matches_schema(response, "memory.search")

    def assert_error_output_matches_schema(self, response: dict[str, Any]) -> None:
        schema = self.schema()
        error_schema = schema["error_schema"]
        for field in error_schema["required"]:
            self.assertIn(field, response)
        self.assertFalse(response["ok"])
        self.assertIn(response["error"]["code"], error_schema["properties"]["error"]["properties"]["code"]["enum"])
        if "bridge" in response:
            self.assert_bridge_matches_schema(response, response["bridge"]["tool"])

    def assert_bridge_matches_schema(self, response: dict[str, Any], tool_name: str) -> None:
        schema = self.schema()
        bridge_schema = schema["$defs"]["bridge_metadata"]
        self.assertIn("bridge", response)
        bridge = response["bridge"]
        for field in bridge_schema["required"]:
            self.assertIn(field, bridge)
        self.assertEqual("openclaw_tool", bridge["entrypoint"])
        # Bridge uses OpenClaw-facing names (fmc_ prefix)
        python_to_openclaw = {
            "memory.search": "fmc_memory_search",
            "memory.create_candidate": "fmc_memory_create_candidate",
            "memory.confirm": "fmc_memory_confirm",
            "memory.reject": "fmc_memory_reject",
            "memory.explain_versions": "fmc_memory_explain_versions",
            "memory.prefetch": "fmc_memory_prefetch",
            "heartbeat.review_due": "fmc_heartbeat_review_due",
        }
        schema_name = python_to_openclaw.get(tool_name, tool_name)
        self.assertEqual(schema_name, bridge["tool"])
        self.assertIn(bridge["tool"], bridge_schema["properties"]["tool"]["enum"])

        decision = bridge["permission_decision"]
        for field in bridge_schema["properties"]["permission_decision"]["required"]:
            self.assertIn(field, decision)
        decision_schema = bridge_schema["properties"]["permission_decision"]["properties"]
        self.assertIn(decision["decision"], decision_schema["decision"]["enum"])
        self.assertIn(decision["requested_action"], decision_schema["requested_action"]["enum"])
        if "requested_visibility" in decision:
            self.assertIn(decision["requested_visibility"], decision_schema["requested_visibility"]["enum"])
        if "actor" in decision:
            actor = decision["actor"]
            for key in ("user_id", "open_id", "tenant_id", "organization_id"):
                if key in actor:
                    self.assertIsInstance(actor[key], str)
            if "roles" in actor:
                self.assertIsInstance(actor["roles"], list)
                self.assertTrue(all(isinstance(role, str) for role in actor["roles"]))

    def schema(self) -> dict[str, Any]:
        if not hasattr(self, "_schema_cache"):
            self._schema_cache = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        return self._schema_cache

    def test_examples_only_use_declared_tools(self) -> None:
        supported = set(supported_tool_names())
        # OpenClaw-facing tool names use fmc_ prefix; map them back to Python-side names
        openclaw_to_python = {
            "fmc_memory_search": "memory.search",
            "fmc_memory_create_candidate": "memory.create_candidate",
            "fmc_memory_confirm": "memory.confirm",
            "fmc_memory_reject": "memory.reject",
            "fmc_memory_explain_versions": "memory.explain_versions",
            "fmc_memory_prefetch": "memory.prefetch",
            "fmc_heartbeat_review_due": "heartbeat.review_due",
        }
        example_paths = sorted(EXAMPLES_DIR.glob("*.json"))

        self.assertGreaterEqual(len(example_paths), 3)
        for path in example_paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for step in payload["steps"]:
                tool_name = step["tool"]
                python_name = openclaw_to_python.get(tool_name, tool_name)
                self.assertIn(python_name, supported, msg=f"{path}: {tool_name}")


if __name__ == "__main__":
    unittest.main()
