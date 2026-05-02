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

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "agent_adapters" / "openclaw" / "plugin"
SCOPE = "project:feishu_ai_challenge"


class OpenClawToolRegistryTest(unittest.TestCase):
    def test_registry_entries_match_supported_copilot_tools(self) -> None:
        registrations = native_tool_registrations()

        # Schema uses fmc_xxx names; translate to Python-side memory.xxx for comparison
        schema_names = sorted(registration.name for registration in registrations)
        self.assertTrue(all(name.startswith("fmc_") for name in schema_names))
        self.assertNotIn("memory.search", schema_names)
        self.assertNotIn("memory_search", schema_names)
        translated_names = sorted(OPENCLAW_TO_PYTHON.get(name, name) for name in schema_names)
        self.assertEqual(supported_tool_names(), translated_names)
        self.assertTrue(all(registration.input_schema["type"] == "object" for registration in registrations))
        self.assertTrue(all(registration.output_schema for registration in registrations))

    def test_plugin_manifest_points_to_installable_openclaw_plugin(self) -> None:
        manifest = openclaw_plugin_manifest()
        package_json = json.loads((PLUGIN_DIR / "package.json").read_text(encoding="utf-8"))
        plugin_json = json.loads((PLUGIN_DIR / "openclaw.plugin.json").read_text(encoding="utf-8"))
        plugin_index = (PLUGIN_DIR / "index.js").read_text(encoding="utf-8")

        self.assertEqual("feishu-memory-copilot", manifest["plugin_id"])
        self.assertEqual("2026.4.24", manifest["openclaw_version"])
        self.assertEqual("agent_adapters/openclaw/plugin", manifest["plugin_dir"])
        self.assertEqual("2026.4.24", package_json["engines"]["openclaw"])
        self.assertEqual("feishu-memory-copilot", plugin_json["id"])
        self.assertIn("configSchema", plugin_json)
        self.assertIn("./index.js", package_json["openclaw"]["extensions"])
        self.assertIn("definePluginEntry", plugin_index)
        self.assertIn("api.registerTool", plugin_index)
        self.assertIn("memory_engine.copilot.openclaw_tool_runner", plugin_index)
        self.assertIn("startAdminDashboard", plugin_index)
        self.assertIn("adminDashboardEnabled", plugin_index)
        self.assertIn("FEISHU_MEMORY_COPILOT_ADMIN_ENABLED", plugin_index)
        self.assertIn('["1", "true", "yes", "on"]', plugin_index)
        self.assertIn("scripts/start_copilot_admin.py", plugin_index)
        self.assertIn('api.on("before_dispatch"', plugin_index)
        self.assertIn("runPythonFeishuRouter", plugin_index)
        self.assertIn("scripts/openclaw_feishu_remember_router.py", plugin_index)
        self.assertIn("shouldRouteFeishuGroupEvent", plugin_index)
        self.assertIn('"memory_search"', plugin_index)
        self.assertIn('"memory_prefetch"', plugin_index)
        self.assertIn("sanitizeRouteResult", plugin_index)
        self.assertIn("feishu-memory-copilot route result", plugin_index)
        self.assertIn("publishInteractiveCardViaLarkCli", plugin_index)
        self.assertIn('publish.mode !== "interactive"', plugin_index)
        self.assertIn('"+messages-reply"', plugin_index)
        self.assertIn('"--msg-type", "interactive"', plugin_index)
        self.assertIn("feishu-memory-copilot card delivery", plugin_index)
        self.assertIn("openclaw_gateway_interactive_card_failed", plugin_index)
        self.assertIn("buildCardDeliveryFailureFallback", plugin_index)
        self.assertIn("buildRouterFailureFallback", plugin_index)
        self.assertIn("card_delivery_failed", plugin_index)
        self.assertIn("router_failed", plugin_index)
        self.assertIn("feishu-memory-copilot router failed", plugin_index)
        self.assertIn("handle_tool_request", (ROOT / "scripts/openclaw_feishu_remember_router.py").read_text(encoding="utf-8"))

    def test_runner_invokes_copilot_service_and_preserves_bridge_metadata(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="openclaw_tool_registry_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(
                SCOPE, "决定：first-class OpenClaw 工具必须保留 request_id 和 trace_id。", source_type="unit_test"
            )
            conn.close()

            response = run_envelope(
                {
                    "tool": "memory.search",
                    "db_path": tmp.name,
                    "payload": {
                        "query": "first-class OpenClaw 工具要保留什么",
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
        self.assertEqual("openclaw_tool", response["bridge"]["entrypoint"])
        self.assertEqual("allow", response["bridge"]["permission_decision"]["decision"])
        self.assertEqual("req_memory_search", response["bridge"]["request_id"])
        self.assertEqual("trace_memory_search", response["bridge"]["trace_id"])


if __name__ == "__main__":
    unittest.main()
