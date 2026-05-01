from __future__ import annotations

import json
import unittest

from scripts.check_feishu_permission_negative_gate import check_permission_negative_events


CHAT_ID = "oc_permission_negative_gate"
ACTOR_ID = "ou_non_reviewer"


def _denied_result(*, chat_id: str = CHAT_ID, actor_id: str | None = ACTOR_ID) -> dict:
    tool_result = {
        "ok": False,
        "tool": "copilot.group_enable_memory",
        "status": "permission_denied",
        "error": {"code": "permission_denied", "reason_code": "reviewer_or_admin_required"},
        "group_policy": {"chat_id": chat_id, "status": "pending_onboarding"},
    }
    if actor_id:
        tool_result["actor_id"] = actor_id
    return {
        "type": "copilot_live_event_result",
        "result": {
            "ok": False,
            "message_id": "om_denied_enable_memory",
            "tool": "copilot.group_enable_memory",
            "routing_reason": "explicit_group_memory_enable",
            "tool_result": tool_result,
            "publish": {"ok": True, "mode": "interactive", "chat_id": chat_id},
        },
    }


def _allowed_result() -> dict:
    return {
        "result": {
            "ok": True,
            "message_id": "om_allowed_enable_memory",
            "tool": "copilot.group_enable_memory",
            "tool_result": {"ok": True, "status": "enabled", "group_policy": {"chat_id": CHAT_ID}},
            "publish": {"ok": True, "mode": "interactive", "chat_id": CHAT_ID},
        }
    }


def _audit_only() -> dict:
    return {
        "event_type": "feishu_group_policy_denied",
        "permission_decision": "deny",
        "reason_code": "reviewer_or_admin_required",
        "actor_id": ACTOR_ID,
        "source_context": json.dumps({"chat_id": CHAT_ID}),
    }


def _enable_memory_message() -> dict:
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {
                "sender_id": {"open_id": ACTOR_ID},
                "sender_type": "user",
            },
            "message": {
                "message_id": "om_enable_attempt",
                "chat_id": CHAT_ID,
                "chat_type": "group",
                "message_type": "text",
                "content": json.dumps({"text": "@_user_1 /enable_memory"}, ensure_ascii=False),
                "mentions": [
                    {
                        "id": {"open_id": "ou_bot"},
                        "key": "@_user_1",
                        "mentioned_type": "bot",
                        "name": "Memory Copilot",
                    }
                ],
                "create_time": "1777647600000",
            },
        },
    }


class FeishuPermissionNegativeGateTest(unittest.TestCase):
    def test_passes_when_denied_enable_memory_result_is_present(self) -> None:
        report = check_permission_negative_events(
            json.dumps(_denied_result(), ensure_ascii=False),
            expected_chat_id=CHAT_ID,
            expected_actor_id=ACTOR_ID,
        )

        self.assertTrue(report["ok"])
        self.assertEqual("non_reviewer_enable_memory_denied", report["reason"])
        self.assertEqual(1, report["summary"]["denied_enable_memory_results"])
        self.assertEqual("reviewer_or_admin_required", report["denied_examples"][0]["reason_code"])

    def test_reads_ndjson_wrapped_result_lines(self) -> None:
        line = json.dumps({"time": "2026-05-01T10:00:00+08:00", "message": _denied_result()}, ensure_ascii=False)

        report = check_permission_negative_events(line)

        self.assertTrue(report["ok"])
        self.assertEqual(1, report["summary"]["denied_enable_memory_results"])

    def test_audit_only_is_not_enough_for_live_result_gate(self) -> None:
        report = check_permission_negative_events(json.dumps(_audit_only(), ensure_ascii=False))

        self.assertFalse(report["ok"])
        self.assertEqual("audit_only_no_denied_live_result", report["reason"])
        self.assertEqual(1, report["summary"]["denied_group_policy_audit_events"])

    def test_allowed_enable_memory_does_not_satisfy_negative_gate(self) -> None:
        report = check_permission_negative_events(json.dumps(_allowed_result(), ensure_ascii=False))

        self.assertFalse(report["ok"])
        self.assertEqual("only_authorized_enable_memory_seen", report["reason"])
        self.assertEqual(1, report["summary"]["allowed_enable_memory_results"])

    def test_attempt_without_result_explains_missing_result_log(self) -> None:
        report = check_permission_negative_events(json.dumps(_enable_memory_message(), ensure_ascii=False))

        self.assertFalse(report["ok"])
        self.assertEqual("enable_memory_attempt_without_denied_result", report["reason"])
        self.assertEqual(1, report["summary"]["enable_memory_attempt_events"])

    def test_expected_chat_filters_other_group(self) -> None:
        report = check_permission_negative_events(
            json.dumps(_denied_result(chat_id="oc_other_group"), ensure_ascii=False),
            expected_chat_id=CHAT_ID,
        )

        self.assertFalse(report["ok"])
        self.assertEqual("expected_chat_not_seen", report["reason"])
        self.assertEqual(1, report["summary"]["chat_mismatch"])

    def test_expected_actor_filters_other_user_when_actor_is_present(self) -> None:
        report = check_permission_negative_events(
            json.dumps(_denied_result(actor_id="ou_other_user"), ensure_ascii=False),
            expected_actor_id=ACTOR_ID,
        )

        self.assertFalse(report["ok"])
        self.assertEqual("expected_actor_not_seen", report["reason"])
        self.assertEqual(1, report["summary"]["actor_mismatch"])


if __name__ == "__main__":
    unittest.main()
