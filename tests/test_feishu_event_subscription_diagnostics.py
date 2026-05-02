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
        self.assertEqual(
            ["message_schema_scope_does_not_list_group_msg_readonly"], [item["id"] for item in result["warnings"]]
        )
        self.assertTrue(result["remediation"]["requires_external_console_change"])
        self.assertEqual(
            ["im:message.group_msg:readonly"],
            result["remediation"]["required_scopes_any_of"],
        )
        self.assertEqual(["im:message.p2p_msg:readonly"], result["remediation"]["current_scopes"])

    def test_can_require_group_message_scope_for_passive_live_preflight(self) -> None:
        result = run_feishu_event_subscription_diagnostics(
            planned_listener="openclaw-websocket",
            require_group_message_scope=True,
            runner=_runner(
                status={"apps": [{"app_id": "cli_app", "status": "not_running", "running": False}]},
                event_list=[_message_event(scopes=["im:message.p2p_msg:readonly"])],
                schema=_message_event(scopes=["im:message.p2p_msg:readonly"]),
            ),
        )

        self.assertFalse(result["ok"], result)
        self.assertTrue(result["require_group_message_scope"])
        self.assertIn("message_schema_group_message_scope", result["failed_checks"])
        self.assertIn("group-message readonly scope", result["next_step"])

    def test_broad_enabled_message_scope_does_not_satisfy_group_message_preflight(self) -> None:
        result = run_feishu_event_subscription_diagnostics(
            planned_listener="openclaw-websocket",
            require_group_message_scope=True,
            runner=_runner(
                status={"apps": [{"app_id": "cli_app", "status": "not_running", "running": False}]},
                event_list=[_message_event(scopes=["im:message.p2p_msg:readonly"])],
                schema=_message_event(scopes=["im:message.p2p_msg:readonly"]),
                auth_scopes={"appId": "cli_app", "userScopes": ["im:message:readonly"]},
            ),
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("message_schema_group_message_scope", result["failed_checks"])
        self.assertFalse(result["message_event_schema"]["has_group_message_scope_from_schema"])
        self.assertFalse(result["message_event_schema"]["has_group_message_scope_from_enabled_scopes"])
        self.assertIn("im:message:readonly", result["remediation"]["enabled_scopes"])
        self.assertEqual(
            ["message_schema_scope_does_not_list_group_msg_readonly"],
            [item["id"] for item in result["warnings"]],
        )

    def test_exact_enabled_group_message_scope_can_satisfy_preflight_when_schema_scope_is_stale(self) -> None:
        result = run_feishu_event_subscription_diagnostics(
            planned_listener="openclaw-websocket",
            require_group_message_scope=True,
            runner=_runner(
                status={"apps": [{"app_id": "cli_app", "status": "not_running", "running": False}]},
                event_list=[_message_event(scopes=["im:message.p2p_msg:readonly"])],
                schema=_message_event(scopes=["im:message.p2p_msg:readonly"]),
                auth_scopes={"appId": "cli_app", "userScopes": ["im:message.group_msg:readonly"]},
            ),
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual([], result["failed_checks"])
        self.assertFalse(result["message_event_schema"]["has_group_message_scope_from_schema"])
        self.assertTrue(result["message_event_schema"]["has_group_message_scope_from_enabled_scopes"])
        self.assertIn("im:message.group_msg:readonly", result["remediation"]["enabled_scopes"])
        self.assertEqual(
            ["message_schema_scope_missing_but_enabled_scope_present"],
            [item["id"] for item in result["warnings"]],
        )

    def test_target_chat_probe_fails_when_bot_cannot_read_group_messages(self) -> None:
        result = run_feishu_event_subscription_diagnostics(
            planned_listener="openclaw-websocket",
            require_group_message_scope=True,
            target_chat_id="oc_target_group",
            runner=_runner(
                status={"apps": [{"app_id": "cli_app", "status": "not_running", "running": False}]},
                event_list=[_message_event(scopes=["im:message.p2p_msg:readonly"])],
                schema=_message_event(scopes=["im:message.p2p_msg:readonly"]),
                auth_scopes={"appId": "cli_app", "userScopes": ["im:message.group_msg:readonly"]},
                bot_group_messages={
                    "ok": False,
                    "error": {"type": "permission", "code": 230027, "message": "Permission denied [230027]"},
                },
                bot_group_messages_returncode=1,
            ),
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("target_bot_group_messages_readable", result["failed_checks"])
        self.assertEqual(230027, result["target_group_probe"]["error_code"])
        self.assertTrue(result["remediation"]["target_group_access_action_required"])
        self.assertIn("target_bot_group_messages_unreadable", [item["id"] for item in result["warnings"]])

    def test_target_chat_probe_passes_when_bot_can_read_group_messages(self) -> None:
        result = run_feishu_event_subscription_diagnostics(
            planned_listener="openclaw-websocket",
            require_group_message_scope=True,
            target_chat_id="oc_target_group",
            runner=_runner(
                status={"apps": [{"app_id": "cli_app", "status": "not_running", "running": False}]},
                event_list=[_message_event(scopes=["im:message.p2p_msg:readonly"])],
                schema=_message_event(scopes=["im:message.p2p_msg:readonly"]),
                auth_scopes={"appId": "cli_app", "userScopes": ["im:message.group_msg:readonly"]},
                bot_group_messages={"ok": True, "data": {"messages": []}},
            ),
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual([], result["failed_checks"])
        self.assertTrue(result["target_group_probe"]["ok"])
        self.assertFalse(result["remediation"]["target_group_access_action_required"])

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
        self.assertTrue(result["remediation"]["single_listener_action_required"])

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


def _runner(
    *,
    status: object,
    event_list: object,
    schema: object,
    auth_scopes: object | None = None,
    bot_group_messages: object | None = None,
    bot_group_messages_returncode: int = 0,
):
    def run(command: list[str]) -> dict[str, object]:
        joined = " ".join(command)
        if "event status" in joined:
            payload = status
            returncode = 0
        elif "event list" in joined:
            payload = event_list
            returncode = 0
        elif "event schema" in joined:
            payload = schema
            returncode = 0
        elif "auth scopes" in joined:
            payload = auth_scopes or {}
            returncode = 0
        elif "+chat-messages-list" in joined:
            payload = bot_group_messages or {}
            returncode = bot_group_messages_returncode
        else:
            payload = {}
            returncode = 0
        return {"returncode": returncode, "stdout": json.dumps(payload), "stderr": ""}

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
