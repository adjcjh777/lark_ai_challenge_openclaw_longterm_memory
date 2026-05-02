from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from scripts.check_openclaw_memory_copilot_demo_preflight import (
    BOUNDARY,
    check_card_delivery_helper_syntax,
    check_feishu_channel_status,
    check_gateway_status,
    check_listener_singleton,
    check_memory_copilot_plugin,
    run_preflight,
)


class OpenClawMemoryCopilotDemoPreflightTest(unittest.TestCase):
    def test_preflight_passes_when_runtime_and_plugin_checks_pass(self) -> None:
        with patch("scripts.check_openclaw_memory_copilot_demo_preflight.run_command") as run:
            run.side_effect = [
                command("Connectivity probe: ok"),
                command("Feishu default: enabled, configured, running, works"),
                command("Feishu listener singleton check OK."),
                command(plugin_payload()),
                command(""),
                command(""),
            ]

            report = run_preflight()

        self.assertTrue(report["ok"])
        self.assertIn("local_demo_preflight_only", report["boundary"])
        self.assertIn("feishu-memory-copilot card delivery", report["next_live_gate"])

    def test_gateway_status_requires_connectivity_probe_ok(self) -> None:
        with patch(
            "scripts.check_openclaw_memory_copilot_demo_preflight.run_command",
            return_value=command("Runtime: running\nConnectivity probe: failed"),
        ):
            result = check_gateway_status()

        self.assertFalse(result["ok"])

    def test_feishu_channel_status_requires_running_and_works(self) -> None:
        with patch(
            "scripts.check_openclaw_memory_copilot_demo_preflight.run_command",
            return_value=command("Feishu default: enabled, configured, running"),
        ):
            result = check_feishu_channel_status()

        self.assertFalse(result["ok"])

    def test_listener_singleton_uses_expected_planned_listener(self) -> None:
        calls = []

        def fake_run(command_args, *, timeout=20):
            calls.append(command_args)
            return command("Feishu listener singleton check OK.")

        with patch("scripts.check_openclaw_memory_copilot_demo_preflight.run_command", side_effect=fake_run):
            result = check_listener_singleton("openclaw-websocket")

        self.assertTrue(result["ok"])
        self.assertIn("--planned-listener", calls[0])
        self.assertIn("openclaw-websocket", calls[0])

    def test_plugin_check_requires_loaded_before_dispatch_and_fmc_tools(self) -> None:
        with patch(
            "scripts.check_openclaw_memory_copilot_demo_preflight.run_command",
            return_value=command(plugin_payload(typed_hooks=[])),
        ):
            result = check_memory_copilot_plugin()

        self.assertFalse(result["ok"])
        self.assertNotIn("before_dispatch", result["detail"]["typed_hooks"])

    def test_card_delivery_syntax_check_runs_index_and_helper(self) -> None:
        calls = []

        def fake_run(command_args, *, timeout=20):
            calls.append(command_args)
            return command("")

        with patch("scripts.check_openclaw_memory_copilot_demo_preflight.run_command", side_effect=fake_run):
            result = check_card_delivery_helper_syntax()

        self.assertTrue(result["ok"])
        self.assertEqual(2, len(calls))
        self.assertIn("agent_adapters/openclaw/plugin/index.js", calls[0])
        self.assertIn("agent_adapters/openclaw/plugin/feishu_card_delivery.js", calls[1])

    def test_boundary_does_not_overclaim_live_delivery(self) -> None:
        self.assertIn("does not prove live Feishu card delivery", BOUNDARY)


def command(stdout: str, *, returncode: int = 0, stderr: str = "") -> dict:
    return {"returncode": returncode, "stdout": stdout, "stderr": stderr}


def plugin_payload(*, typed_hooks: list | None = None) -> str:
    if typed_hooks is None:
        typed_hooks = [{"name": "before_dispatch"}]
    return json.dumps(
        {
            "plugin": {
                "status": "loaded",
                "enabled": True,
                "source": "/repo/agent_adapters/openclaw/plugin/index.js",
                "toolNames": [
                    "fmc_memory_search",
                    "fmc_memory_create_candidate",
                    "fmc_memory_confirm",
                    "fmc_memory_reject",
                    "fmc_memory_explain_versions",
                    "fmc_memory_prefetch",
                    "fmc_heartbeat_review_due",
                ],
            },
            "typedHooks": typed_hooks,
        }
    )


if __name__ == "__main__":
    unittest.main()
