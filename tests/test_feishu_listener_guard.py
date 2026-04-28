from __future__ import annotations

import unittest

from memory_engine.feishu_listener_guard import (
    FeishuListenerConflict,
    assert_single_feishu_listener,
    classify_listener_command,
    conflicting_listeners,
    discover_feishu_listeners,
)


class FeishuListenerGuardTest(unittest.TestCase):
    def test_classifies_known_listener_commands(self) -> None:
        self.assertEqual(
            "copilot-lark-cli",
            classify_listener_command("python3 -m memory_engine copilot-feishu listen"),
        )
        self.assertEqual(
            "legacy-lark-cli",
            classify_listener_command("python3 -m memory_engine feishu listen"),
        )
        self.assertEqual(
            "direct-lark-cli",
            classify_listener_command("lark-cli event +subscribe --event im.message.receive_v1"),
        )
        self.assertEqual(
            "openclaw-websocket",
            classify_listener_command("openclaw gateway feishu websocket"),
        )
        self.assertEqual("openclaw-gateway-unknown", classify_listener_command("openclaw-gateway"))

    def test_ignores_current_process_and_search_commands(self) -> None:
        listeners = discover_feishu_listeners(
            current_pid=101,
            process_rows=[
                "101 1 python3 -m memory_engine copilot-feishu listen",
                "102 1 rg lark-cli event +subscribe",
            ],
        )

        self.assertEqual([], listeners)

    def test_all_lark_cli_event_subscribe_instances_conflict_with_copilot_listener(self) -> None:
        listeners = discover_feishu_listeners(
            current_pid=1,
            process_rows=[
                "201 1 python3 -m memory_engine feishu listen",
                "202 201 lark-cli event +subscribe --event im.message.receive_v1",
            ],
        )

        conflicts = conflicting_listeners("copilot-lark-cli", listeners)

        self.assertEqual(["legacy-lark-cli", "direct-lark-cli"], [process.kind for process in conflicts])

    def test_openclaw_websocket_conflicts_with_repo_lark_listener(self) -> None:
        with self.assertRaises(FeishuListenerConflict) as raised:
            assert_single_feishu_listener(
                "copilot-lark-cli",
                current_pid=1,
                process_rows=["301 1 openclaw gateway feishu websocket --app Feishu Memory Engine bot"],
            )

        self.assertIn("Only one listener", str(raised.exception))

    def test_generic_openclaw_gateway_is_reported_but_not_blocking(self) -> None:
        active = assert_single_feishu_listener(
            "copilot-lark-cli",
            current_pid=1,
            process_rows=["401 1 openclaw-gateway"],
        )

        self.assertEqual(["openclaw-gateway-unknown"], [process.kind for process in active])


if __name__ == "__main__":
    unittest.main()
