"""Tests for Feishu DM → plugin tool routing.

Validates that:
1. Plugin tools are registered with correct fmc_xxx names
2. Plugin translates fmc_xxx → memory.xxx for Python runner
3. Python runner handles tool requests and returns bridge metadata
4. OpenClaw JSON-string current_context compatibility does not bypass fail-closed permission
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_adapters.openclaw.tool_registry import (
    OPENCLAW_TO_PYTHON,
    native_tool_registrations,
    openclaw_plugin_manifest,
)
from memory_engine.copilot.openclaw_tool_runner import run_envelope
from memory_engine.copilot.permissions import demo_permission_context
from memory_engine.copilot.tools import supported_tool_names
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository
from scripts.check_feishu_dm_routing import BOUNDARY, format_human_result

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "agent_adapters" / "openclaw" / "plugin"
SCOPE = "project:feishu_ai_challenge"


class FeishuDMRoutingTest(unittest.TestCase):
    """Test Feishu DM → plugin tool routing."""

    def test_dm_routing_check_output_keeps_no_overclaim_boundary(self) -> None:
        output = format_human_result(
            {
                "ok": True,
                "summary": "6/6 checks passed",
                "boundary": BOUNDARY,
                "checks": [{"name": "python_tests", "ok": True, "detail": "exit_code=0"}],
            }
        )

        self.assertIn("Local/staging", output)
        self.assertIn("Do not claim stable live Feishu routing", output)
        self.assertNotIn("working correctly", output)

    def test_plugin_tools_registered_with_fmc_names(self) -> None:
        """Verify plugin tools use fmc_xxx naming convention."""
        registrations = native_tool_registrations()
        for reg in registrations:
            self.assertTrue(
                reg.name.startswith("fmc_"),
                f"Tool {reg.name} should start with 'fmc_' prefix",
            )

    def test_all_fmc_tools_have_python_mapping(self) -> None:
        """Verify all fmc_xxx tools map to Python-side memory.xxx names."""
        registrations = native_tool_registrations()
        for reg in registrations:
            self.assertIn(
                reg.name,
                OPENCLAW_TO_PYTHON,
                f"Tool {reg.name} missing from OPENCLAW_TO_PYTHON mapping",
            )

    def test_translated_names_match_supported_copilot_tools(self) -> None:
        """Verify translated names match Python-side supported tools."""
        registrations = native_tool_registrations()
        translated = sorted(OPENCLAW_TO_PYTHON.get(r.name, r.name) for r in registrations)
        self.assertEqual(supported_tool_names(), translated)

    def test_runner_receives_correct_envelope_from_plugin(self) -> None:
        """Verify plugin sends correct envelope to Python runner."""
        with tempfile.NamedTemporaryFile(prefix="dm_routing_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(SCOPE, "测试路由记忆", source_type="test")
            conn.close()

            # Simulate what plugin/index.js does: translate fmc_xxx → memory.xxx
            response = run_envelope(
                {
                    "tool": "memory.search",  # Python-side name
                    "db_path": tmp.name,
                    "payload": {
                        "query": "路由",
                        "scope": SCOPE,
                        "top_k": 3,
                        "current_context": demo_permission_context(
                            "memory.search",
                            SCOPE,
                            actor_id="ou_test",
                            entrypoint="openclaw_native_tool",
                        ),
                    },
                }
            )

        self.assertTrue(response["ok"])
        self.assertEqual("fmc_memory_search", response["bridge"]["tool"])

    def test_runner_returns_bridge_metadata_for_search(self) -> None:
        """Verify memory.search returns complete bridge metadata."""
        with tempfile.NamedTemporaryFile(prefix="dm_routing_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            conn.close()

            response = run_envelope(
                {
                    "tool": "memory.search",
                    "db_path": tmp.name,
                    "payload": {
                        "query": "test",
                        "scope": SCOPE,
                        "current_context": demo_permission_context("memory.search", SCOPE),
                    },
                }
            )

        self.assertTrue(response["ok"])
        bridge = response["bridge"]
        self.assertEqual("openclaw_tool", bridge["entrypoint"])
        self.assertEqual("fmc_memory_search", bridge["tool"])
        self.assertIn("permission_decision", bridge)
        self.assertIn("request_id", bridge)
        self.assertIn("trace_id", bridge)

    def test_runner_returns_bridge_metadata_for_create_candidate(self) -> None:
        """Verify memory.create_candidate returns complete bridge metadata."""
        with tempfile.NamedTemporaryFile(prefix="dm_routing_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            conn.close()

            response = run_envelope(
                {
                    "tool": "memory.create_candidate",
                    "db_path": tmp.name,
                    "payload": {
                        "text": "测试候选",
                        "scope": SCOPE,
                        "source": {
                            "source_type": "test",
                            "source_id": "test_001",
                            "actor_id": "ou_test",
                            "created_at": "2026-04-28T00:00:00Z",
                            "quote": "测试候选",
                        },
                        "current_context": demo_permission_context("memory.create_candidate", SCOPE),
                    },
                }
            )

        self.assertTrue(response["ok"])
        bridge = response["bridge"]
        self.assertEqual("fmc_memory_create_candidate", bridge["tool"])
        self.assertIn("permission_decision", bridge)

    def test_runner_returns_bridge_metadata_for_prefetch(self) -> None:
        """Verify memory.prefetch returns complete bridge metadata."""
        with tempfile.NamedTemporaryFile(prefix="dm_routing_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            conn.close()

            response = run_envelope(
                {
                    "tool": "memory.prefetch",
                    "db_path": tmp.name,
                    "payload": {
                        "task": "test_task",
                        "scope": SCOPE,
                        "current_context": demo_permission_context("memory.prefetch", SCOPE),
                    },
                }
            )

        self.assertTrue(response["ok"])
        bridge = response["bridge"]
        self.assertEqual("fmc_memory_prefetch", bridge["tool"])

    def test_runner_missing_permission_context_fails_closed(self) -> None:
        """Verify runner does not bypass fail-closed permission checks."""
        with tempfile.NamedTemporaryFile(prefix="dm_routing_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            conn.close()

            response = run_envelope(
                {
                    "tool": "memory.search",
                    "db_path": tmp.name,
                    "payload": {
                        "query": "test",
                        "scope": SCOPE,
                        "current_context": {"scope": SCOPE},
                    },
                }
            )

        self.assertFalse(response["ok"])
        self.assertEqual("permission_denied", response["error"]["code"])
        self.assertEqual("missing_permission_context", response["error"]["details"]["reason_code"])

    def test_runner_accepts_json_string_current_context(self) -> None:
        """Verify MiMo/OpenAI-completions JSON-string context is parsed before validation."""
        with tempfile.NamedTemporaryFile(prefix="dm_routing_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(SCOPE, "Copilot live sandbox 验收口径：真实 DM 必须调用 fmc_memory_search", source_type="test")
            conn.close()

            response = run_envelope(
                {
                    "tool": "memory.search",
                    "db_path": tmp.name,
                    "payload": {
                        "query": "Copilot live sandbox 验收口径",
                        "scope": SCOPE,
                        "current_context": json.dumps(
                            demo_permission_context("memory.search", SCOPE),
                            ensure_ascii=False,
                        ),
                    },
                }
            )

        self.assertTrue(response["ok"])
        self.assertEqual("allow", response["bridge"]["permission_decision"]["decision"])
        self.assertEqual("fmc_memory_search", response["bridge"]["tool"])

    def test_runner_malformed_json_string_current_context_fails_closed(self) -> None:
        """Verify malformed context strings are not converted to permissive defaults."""
        with tempfile.NamedTemporaryFile(prefix="dm_routing_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            conn.close()

            response = run_envelope(
                {
                    "tool": "memory.search",
                    "db_path": tmp.name,
                    "payload": {
                        "query": "test",
                        "scope": SCOPE,
                        "current_context": "{\"scope\":",
                    },
                }
            )

        self.assertFalse(response["ok"])
        self.assertEqual("validation_error", response["error"]["code"])
        self.assertIn("current_context must be an object", response["error"]["message"])

    def test_openclaw_to_python_mapping_completeness(self) -> None:
        """Verify OPENCLAW_TO_PYTHON covers all registered tools."""
        registrations = native_tool_registrations()
        for reg in registrations:
            self.assertIn(reg.name, OPENCLAW_TO_PYTHON)

    def test_plugin_manifest_includes_all_fmc_tools(self) -> None:
        """Verify plugin manifest includes all fmc_xxx tools."""
        manifest = openclaw_plugin_manifest()
        tool_names = [t["name"] for t in manifest["tools"]]
        expected = [
            "fmc_memory_search",
            "fmc_memory_create_candidate",
            "fmc_memory_confirm",
            "fmc_memory_reject",
            "fmc_memory_explain_versions",
            "fmc_memory_prefetch",
            "fmc_heartbeat_review_due",
        ]
        self.assertEqual(sorted(expected), sorted(tool_names))

    def test_plugin_manifest_embeds_current_context_definitions(self) -> None:
        """Verify manifest consumers receive a resolvable permission context schema."""
        manifest = openclaw_plugin_manifest()
        for tool in manifest["tools"]:
            input_schema = tool["input_schema"]
            self.assertEqual("#/$defs/current_context_payload", input_schema["properties"]["current_context"]["$ref"])
            self.assertIn("$defs", input_schema)
            self.assertIn("current_context_payload", input_schema["$defs"])
            self.assertIn("permission_context", input_schema["$defs"])


if __name__ == "__main__":
    unittest.main()
