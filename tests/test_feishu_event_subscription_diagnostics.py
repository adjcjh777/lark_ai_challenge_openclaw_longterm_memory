from __future__ import annotations

import json
import unittest

from scripts.check_feishu_event_subscription_diagnostics import run_feishu_event_subscription_diagnostics


class FeishuEventSubscriptionDiagnosticsTest(unittest.TestCase):
    def test_passes_read_only_checks_for_openclaw_owner_and_warns_on_missing_group_scope(self) -> None:
        result = run_feishu_event_subscription_diagnostics(
            planned_listener="openclaw-websocket",
            runner=_runner(
                status={"apps": [{"app_id": "cli_app", "status": "not_running", "running": False}]},
                event_list=[_message_event(scopes=["im:message.p2p_msg:readonly"])],
                schema=_message_event(scopes=["im:message.p2p_msg:readonly"]),
            ),
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual([], result["failed_checks"])
        self.assertEqual(0, result["event_status"]["active_bus_count"])
        self.assertFalse(result["message_event_schema"]["has_group_message_scope"])
        self.assertEqual(["message_schema_scope_does_not_list_group_msg_readonly"], [item["id"] for item in result["warnings"]])

    def test_fails_when_lark_cli_bus_is_running_but_openclaw_is_planned_owner(self) -> None:
        result = run_feishu_event_subscription_diagnostics(
            planned_listener="openclaw-websocket",
            runner=_runner(
                status={"apps": [{"app_id": "cli_app", "status": "running", "running": True}]},
                event_list=[_message_event(scopes=["im:message:readonly"])],
                schema=_message_event(scopes=["im:message:readonly"]),
            ),
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("listener_mode_consistent", result["failed_checks"])

    def test_fails_when_message_event_is_not_registered(self) -> None:
        result = run_feishu_event_subscription_diagnostics(
            runner=_runner(
                status={"apps": []},
                event_list=[],
                schema={"key": "im.message.receive_v1", "auth_types": ["bot"], "required_console_events": []},
            ),
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("message_event_registered", result["failed_checks"])
        self.assertIn("message_schema_requires_console_event", result["failed_checks"])


def _runner(*, status: object, event_list: object, schema: object):
    def run(command: list[str]) -> dict[str, object]:
        joined = " ".join(command)
        if "event status" in joined:
            payload = status
        elif "event list" in joined:
            payload = event_list
        elif "event schema" in joined:
            payload = schema
        else:
            payload = {}
        return {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""}

    return run


def _message_event(*, scopes: list[str]) -> dict[str, object]:
    return {
        "key": "im.message.receive_v1",
        "event_type": "im.message.receive_v1",
        "auth_types": ["bot"],
        "scopes": scopes,
        "required_console_events": ["im.message.receive_v1"],
    }


if __name__ == "__main__":
    unittest.main()
