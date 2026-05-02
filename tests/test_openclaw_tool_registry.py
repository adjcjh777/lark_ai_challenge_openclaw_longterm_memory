from __future__ import annotations

import json
import os
import stat
import subprocess
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
        delivery_helper = (PLUGIN_DIR / "feishu_card_delivery.js").read_text(encoding="utf-8")

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
        self.assertIn("./feishu_card_delivery.js", plugin_index)
        self.assertIn('api.on("before_dispatch"', plugin_index)
        self.assertIn("runPythonFeishuRouter", plugin_index)
        self.assertIn("scripts/openclaw_feishu_remember_router.py", plugin_index)
        self.assertIn("shouldRouteFeishuGroupEvent", plugin_index)
        self.assertIn('"memory_search"', plugin_index)
        self.assertIn('"memory_prefetch"', plugin_index)
        self.assertIn("sanitizeRouteResult", plugin_index)
        self.assertIn("feishu-memory-copilot route result", plugin_index)
        self.assertIn("publishInteractiveCardViaLarkCli", plugin_index)
        self.assertIn('publish.mode !== "interactive"', delivery_helper)
        self.assertIn("buildInteractiveCardRequestBody", delivery_helper)
        self.assertIn("/open-apis/im/v1/messages", delivery_helper)
        self.assertIn("receive_id_type", delivery_helper)
        self.assertIn('msg_type: "interactive"', delivery_helper)
        self.assertIn("feishu-memory-copilot card delivery", plugin_index)
        self.assertIn("openclaw_gateway_interactive_card_failed", delivery_helper)
        self.assertIn("buildCardDeliveryFailureFallback", plugin_index)
        self.assertIn("buildRouterFailureFallback", plugin_index)
        self.assertIn("card_delivery_failed", delivery_helper)
        self.assertIn("router_failed", delivery_helper)
        self.assertIn("feishu-memory-copilot router failed", plugin_index)
        self.assertIn("handle_tool_request", (ROOT / "scripts/openclaw_feishu_remember_router.py").read_text(encoding="utf-8"))

    def test_interactive_card_delivery_helper_executes_cli_and_exposes_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory(prefix="fmc_lark_cli_") as tmpdir:
            tmp_path = Path(tmpdir)
            fake_cli = tmp_path / "fake-lark-cli"
            capture_path = tmp_path / "capture.json"
            synthetic_capture_path = tmp_path / "capture-synthetic.json"
            fake_cli.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env node",
                        "const fs = require('node:fs');",
                        "const args = process.argv.slice(2);",
                        f"const capture = args.includes('/open-apis/im/v1/messages/om_demo/reply') ? {json.dumps(str(capture_path))} : {json.dumps(str(synthetic_capture_path))};",
                        "fs.writeFileSync(capture, JSON.stringify(args));",
                    ]
                ),
                encoding="utf-8",
            )
            fake_cli.chmod(fake_cli.stat().st_mode | stat.S_IXUSR)

            script = """
                import {
                  buildInteractiveCardRequestBody,
                  buildCardDeliveryFailureFallback,
                  buildRouterFailureFallback,
                  isRealFeishuMessageId,
                  larkCliEnvironment,
                  commandPreview,
                  publishInteractiveCardViaLarkCli,
                  resolveLarkCliBin,
                } from './agent_adapters/openclaw/plugin/feishu_card_delivery.js';
                const publish = {
                  mode: 'interactive',
                  delivery_mode: 'chat',
                  reply_to: 'om_demo',
                  chat_id: 'oc_demo',
                  card: { type: 'template', data: { template_id: 'tpl_demo' } },
                };
                const ok = await publishInteractiveCardViaLarkCli(publish, {
                  env: {
                    ...process.env,
                    LARK_CLI_BIN: process.env.FAKE_LARK_CLI,
                    FAKE_LARK_CAPTURE: process.env.FAKE_LARK_CAPTURE,
                    FEISHU_CARD_TIMEOUT_SECONDS: '2',
                  },
                });
                const missingTarget = await publishInteractiveCardViaLarkCli({
                  mode: 'interactive',
                  delivery_mode: 'chat',
                  card: { type: 'template' },
                }, { env: process.env });
                const syntheticReply = await publishInteractiveCardViaLarkCli({
                  mode: 'interactive',
                  delivery_mode: 'chat',
                  reply_to: 'openclaw_before_dispatch_synthetic',
                  chat_id: 'oc_demo',
                  card: { type: 'template', data: { template_id: 'tpl_demo' } },
                }, {
                  env: {
                    ...process.env,
                    LARK_CLI_BIN: process.env.FAKE_LARK_CLI,
                    FAKE_LARK_CAPTURE: process.env.FAKE_LARK_CAPTURE_SYNTHETIC,
                    FEISHU_CARD_TIMEOUT_SECONDS: '2',
                  },
                });
                console.log(JSON.stringify({
                  ok,
                  missingTarget,
                  syntheticReply,
                  realMessageId: isRealFeishuMessageId('om_demo'),
                  syntheticMessageId: isRealFeishuMessageId('openclaw_before_dispatch_synthetic'),
                  requestBody: buildInteractiveCardRequestBody({
                    card: { config: {}, elements: [{ tag: 'markdown', content: 'hello' }] },
                    chatId: 'oc_demo',
                    uuid: 'uuid_demo',
                  }),
                  commandPreview: commandPreview(['/opt/homebrew/bin/lark-cli', '--profile', 'feishu-ai-challenge', 'api', 'POST', '--data', '{"secret":"hidden"}']),
                  explicitCli: resolveLarkCliBin({ LARK_CLI_BIN: '/tmp/custom-lark-cli' }),
                  defaultCli: resolveLarkCliBin({}),
                  launchdEnv: larkCliEnvironment({ PATH: '/usr/bin:/bin' }),
                  cardFallback: buildCardDeliveryFailureFallback({
                    fallback_reason: 'boom',
                    card: {
                      header: { title: { tag: 'plain_text', content: '群级记忆设置' } },
                      elements: [{ tag: 'div', fields: [{ text: { tag: 'lark_md', content: '**当前群状态**\\ndisabled' } }] }],
                    },
                  }),
                  routerFallback: buildRouterFailureFallback(new Error('router boom')),
                }));
            """
            result = subprocess.run(
                ["node", "--input-type=module", "-e", script],
                cwd=ROOT,
                env={
                    **os.environ,
                    "FAKE_LARK_CLI": str(fake_cli),
                    "FAKE_LARK_CAPTURE": str(capture_path),
                    "FAKE_LARK_CAPTURE_SYNTHETIC": str(synthetic_capture_path),
                },
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            captured_command = json.loads(capture_path.read_text(encoding="utf-8"))
            captured_synthetic_command = json.loads(synthetic_capture_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["ok"]["ok"])
            self.assertEqual("reply_card", payload["ok"]["mode"])
            self.assertFalse(payload["ok"]["fallback_suppressed"])
            self.assertEqual("chat", payload["ok"]["delivery_mode"])
            self.assertIn("api", captured_command)
            self.assertIn("--profile", captured_command)
            self.assertIn("feishu-ai-challenge", captured_command)
            self.assertIn("--profile feishu-ai-challenge", payload["ok"]["command_preview"])
            self.assertIn("POST", captured_command)
            self.assertIn("/open-apis/im/v1/messages/om_demo/reply", captured_command)
            self.assertIn("--data", captured_command)
            self.assertTrue(payload["syntheticReply"]["ok"])
            self.assertEqual("send_card", payload["syntheticReply"]["mode"])
            self.assertTrue(payload["realMessageId"])
            self.assertFalse(payload["syntheticMessageId"])
            self.assertIn("api", captured_synthetic_command)
            self.assertIn("--profile", captured_synthetic_command)
            self.assertIn("feishu-ai-challenge", captured_synthetic_command)
            self.assertIn("--profile feishu-ai-challenge", payload["syntheticReply"]["command_preview"])
            self.assertIn("POST", captured_synthetic_command)
            self.assertIn("/open-apis/im/v1/messages", captured_synthetic_command)
            self.assertIn("--params", captured_synthetic_command)
            self.assertTrue(any('"receive_id_type":"chat_id"' in part for part in captured_synthetic_command))
            self.assertIn("--data", captured_synthetic_command)
            self.assertNotIn("+messages-reply", captured_synthetic_command)
            self.assertEqual("interactive", payload["requestBody"]["msg_type"])
            self.assertEqual("oc_demo", payload["requestBody"]["receive_id"])
            self.assertIsInstance(payload["requestBody"]["content"], str)
            self.assertIn("--data <json>", payload["commandPreview"])
            self.assertNotIn("hidden", payload["commandPreview"])
            self.assertEqual("/tmp/custom-lark-cli", payload["explicitCli"])
            self.assertIn("lark-cli", payload["defaultCli"])
            self.assertEqual("feishu-ai-challenge", payload["launchdEnv"]["LARK_CLI_PROFILE"])
            self.assertIn("/opt/homebrew/bin", payload["launchdEnv"]["PATH"])
            self.assertTrue(payload["launchdEnv"]["HOME"])
            self.assertFalse(payload["missingTarget"]["ok"])
            self.assertTrue(payload["missingTarget"]["fallback_suppressed"])
            self.assertIn("card_delivery_failed", payload["cardFallback"])
            self.assertIn("群级记忆设置", payload["cardFallback"])
            self.assertIn("当前群状态", payload["cardFallback"])
            self.assertIn("router_failed", payload["routerFallback"])

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
