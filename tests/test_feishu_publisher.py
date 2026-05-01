from __future__ import annotations

import json
import unittest

from memory_engine.feishu_config import FeishuConfig
from memory_engine.feishu_events import FeishuTextEvent
from memory_engine.feishu_publisher import DryRunPublisher, LarkCliPublisher


class RecordingPublisher(LarkCliPublisher):
    def __init__(self, config: FeishuConfig, outcomes: list[bool | dict] | None = None):
        super().__init__(config)
        self.outcomes = list(outcomes or [])
        self.commands: list[list[str]] = []
        self.modes: list[str] = []

    def _run(self, command, mode, event, text, *, card=None, timeout=None):  # type: ignore[override]
        self.commands.append(command)
        self.modes.append(mode)
        outcome = self.outcomes.pop(0) if self.outcomes else True
        if isinstance(outcome, dict):
            ok = bool(outcome.get("ok"))
            timed_out = bool(outcome.get("timed_out"))
            returncode = outcome.get("returncode", None if timed_out else (0 if ok else 1))
            stderr = outcome.get("stderr", "timeout" if timed_out else "failed")
        else:
            ok = bool(outcome)
            timed_out = False
            returncode = 0 if ok else 1
            stderr = "" if ok else "failed"
        return {
            "ok": ok,
            "dry_run": False,
            "mode": mode,
            "reply_to": event.message_id if mode.startswith("reply") else None,
            "chat_id": event.chat_id,
            "text": text,
            "card": card,
            "returncode": returncode,
            "stdout": "",
            "stderr": stderr,
            "timed_out": timed_out,
            "latency_ms": 1.0,
        }


def event() -> FeishuTextEvent:
    return FeishuTextEvent(
        message_id="om_review",
        chat_id="oc_group",
        chat_type="group",
        sender_id="ou_sender",
        sender_type="user",
        message_type="text",
        text="/review",
        create_time=1777000000000,
        raw={},
    )


def card_action_event(*, token: str | None = "card_token_review") -> FeishuTextEvent:
    raw_event = {
        "event": {
            "operator": {"open_id": "ou_sender"},
            "context": {"open_chat_id": "oc_group"},
            "action": {"value": {"memory_engine_action": "confirm", "candidate_id": "mem_1"}},
        }
    }
    if token is not None:
        raw_event["event"]["token"] = token
    return FeishuTextEvent(
        message_id=f"card_action_{token or 'missing'}",
        chat_id="oc_group",
        chat_type="group",
        sender_id="ou_sender",
        sender_type="user",
        message_type="card_action",
        text="/confirm mem_1",
        create_time=1777000000000,
        raw=raw_event,
    )


def config() -> FeishuConfig:
    return FeishuConfig(
        bot_mode="reply",
        default_scope="project:feishu_ai_challenge",
        lark_cli="lark-cli",
        lark_profile="feishu-ai-challenge",
        lark_as="bot",
        reply_in_thread=False,
        card_mode="interactive",
        card_retry_count=1,
        card_timeout_seconds=0.5,
    )


def targeted_card() -> dict:
    return {
        "config": {"wide_screen_mode": True},
        "open_ids": ["ou_reviewer_1", "ou_reviewer_2"],
        "elements": [{"tag": "div", "text": {"tag": "plain_text", "content": "待审核"}}],
    }


class FeishuPublisherTest(unittest.TestCase):
    def test_targeted_interactive_card_sends_dm_to_each_open_id_not_group(self) -> None:
        publisher = RecordingPublisher(config())

        result = publisher.publish(event(), "不应发到群聊", targeted_card())

        self.assertTrue(result["ok"])
        self.assertEqual("dm", result["delivery_mode"])
        self.assertEqual(["ou_reviewer_1", "ou_reviewer_2"], result["targets"])
        self.assertEqual(["send_direct_card", "send_direct_card"], publisher.modes)
        self.assertEqual(len(result["targets"]), len(publisher.commands))
        for command, target in zip(publisher.commands, result["targets"]):
            self.assertIn("--user-id", command)
            self.assertEqual(target, command[command.index("--user-id") + 1])
            self.assertNotIn("--chat-id", command)
            self.assertEqual("interactive", command[command.index("--msg-type") + 1])
            json.loads(command[command.index("--content") + 1])

    def test_targeted_card_failure_falls_back_only_to_dm_text(self) -> None:
        publisher = RecordingPublisher(config(), [False, True])

        result = publisher.publish(event(), "只能私聊 fallback", {"open_ids": ["ou_reviewer_1"]})

        self.assertTrue(result["ok"])
        self.assertEqual("dm", result["delivery_mode"])
        self.assertTrue(result["target_results"][0]["fallback_used"])
        self.assertEqual(["send_direct_card", "send_direct_text"], publisher.modes)
        for command in publisher.commands:
            self.assertIn("--user-id", command)
            self.assertEqual("ou_reviewer_1", command[command.index("--user-id") + 1])
            self.assertNotIn("--chat-id", command)
        self.assertIn("--text", publisher.commands[1])

    def test_targeted_card_timeout_suppresses_fallback_without_group_send(self) -> None:
        publisher = RecordingPublisher(config(), [{"ok": False, "timed_out": True}])

        result = publisher.publish(event(), "不能因为超时回群", {"open_ids": ["ou_reviewer_1"]})

        self.assertFalse(result["ok"])
        self.assertEqual("dm", result["delivery_mode"])
        self.assertEqual("direct_interactive_card_timeout_ambiguous", result["target_results"][0]["fallback_reason"])
        self.assertEqual(["send_direct_card"], publisher.modes)
        self.assertIn("--user-id", publisher.commands[0])
        self.assertNotIn("--chat-id", publisher.commands[0])

    def test_dry_run_reports_dm_mode_and_targets_for_targeted_card(self) -> None:
        result = DryRunPublisher().publish(event(), "dry run", targeted_card())

        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertEqual("dm", result["delivery_mode"])
        self.assertEqual(["ou_reviewer_1", "ou_reviewer_2"], result["targets"])
        self.assertEqual("interactive", result["mode"])
        self.assertEqual("direct_interactive", result["direct_mode"])
        self.assertIsNone(result["chat_id"])

    def test_card_action_with_token_updates_clicked_card_only(self) -> None:
        publisher = RecordingPublisher(config())

        result = publisher.publish(card_action_event(token="card_token_review"), "更新卡片", {"elements": []})

        self.assertTrue(result["ok"])
        self.assertEqual("update_card", result["mode"])
        self.assertEqual("card_token_review", result["card_update_token"])
        self.assertEqual(["update_card"], publisher.modes)
        command = publisher.commands[0]
        self.assertEqual("/open-apis/interactive/v1/card/update", command[command.index("POST") + 1])
        self.assertNotIn("--chat-id", command)

    def test_card_action_without_token_suppresses_duplicate_group_card(self) -> None:
        publisher = RecordingPublisher(config())

        result = publisher.publish(card_action_event(token=None), "不能新发群卡片", {"elements": []})

        self.assertFalse(result["ok"])
        self.assertEqual("card_action_update_token_missing", result["mode"])
        self.assertTrue(result["fallback_suppressed"])
        self.assertEqual("card_action_update_token_missing", result["fallback_reason"])
        self.assertEqual([], publisher.modes)

    def test_dry_run_card_action_without_token_reports_suppressed_update(self) -> None:
        result = DryRunPublisher().publish(card_action_event(token=None), "dry run", {"elements": []})

        self.assertFalse(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertEqual("card_action_update_token_missing", result["mode"])
        self.assertTrue(result["fallback_suppressed"])


if __name__ == "__main__":
    unittest.main()
