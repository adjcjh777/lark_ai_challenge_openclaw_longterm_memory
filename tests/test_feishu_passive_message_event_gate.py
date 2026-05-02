from __future__ import annotations

import json
import unittest

from scripts.check_feishu_passive_message_event_gate import check_passive_message_events


def _message_payload(*, mentions: list[dict] | None = None, chat_id: str = "oc_passive_gate") -> dict:
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou_passive_sender"},
                "sender_type": "user",
            },
            "message": {
                "message_id": "om_passive_message",
                "chat_id": chat_id,
                "chat_type": "group",
                "message_type": "text",
                "content": json.dumps({"text": "决定：非 @ 群消息需要进入 passive screening。"}, ensure_ascii=False),
                "mentions": mentions or [],
                "create_time": "1777647600000",
            },
        },
    }


class FeishuPassiveMessageEventGateTest(unittest.TestCase):
    def test_passes_when_non_mentioned_group_text_message_is_present(self) -> None:
        report = check_passive_message_events(json.dumps(_message_payload(), ensure_ascii=False))

        self.assertTrue(report["ok"])
        self.assertEqual("passive_group_message_seen", report["reason"])
        self.assertEqual(1, report["summary"]["passive_group_text_messages"])
        self.assertEqual("om_p...sage", report["passive_examples"][0]["message_id"])

    def test_fails_with_reaction_only_symptom(self) -> None:
        payload = {
            "schema": "2.0",
            "header": {"event_type": "im.message.reaction.created_v1"},
            "event": {"message_id": "om_reaction_only", "reaction_type": "thumbsup"},
        }

        report = check_passive_message_events(json.dumps(payload))

        self.assertFalse(report["ok"])
        self.assertEqual("reaction_only_no_passive_message_event", report["reason"])
        self.assertEqual(1, report["summary"]["reaction_events"])
        self.assertIn("event subscription", report["next_step"])

    def test_fails_when_only_at_mention_group_message_is_seen(self) -> None:
        payload = _message_payload(
            mentions=[
                {
                    "key": "@_user_1",
                    "id": {"open_id": "ou_bot"},
                    "mentioned_type": "bot",
                    "name": "Memory Copilot",
                    "tenant_key": "tenant_demo",
                }
            ]
        )

        report = check_passive_message_events(json.dumps(payload, ensure_ascii=False))

        self.assertFalse(report["ok"])
        self.assertEqual("only_at_mention_group_messages_seen", report["reason"])
        self.assertEqual(1, report["summary"]["mentioned_group_text_messages"])

    def test_expected_chat_id_filters_other_group_events(self) -> None:
        report = check_passive_message_events(
            json.dumps(_message_payload(chat_id="oc_other_group"), ensure_ascii=False),
            expected_chat_id="oc_expected_group",
        )

        self.assertFalse(report["ok"])
        self.assertEqual("expected_chat_not_seen", report["reason"])
        self.assertEqual(1, report["summary"]["chat_mismatch"])

    def test_reads_ndjson_log_wrappers(self) -> None:
        wrapped = {
            "time": "2026-05-01T10:00:00+08:00",
            "payload": _message_payload(),
        }
        report = check_passive_message_events(json.dumps(wrapped, ensure_ascii=False) + "\n")

        self.assertTrue(report["ok"])
        self.assertEqual(1, report["summary"]["passive_group_text_messages"])

    def test_reads_copilot_listener_raw_line_wrappers(self) -> None:
        wrapped = {
            "ts": "2026-05-01T19:18:35+08:00",
            "event": "copilot_live_event_received",
            "raw_line": json.dumps(_message_payload(), ensure_ascii=False),
        }
        report = check_passive_message_events(json.dumps(wrapped, ensure_ascii=False) + "\n")

        self.assertTrue(report["ok"])
        self.assertEqual(1, report["summary"]["passive_group_text_messages"])

    def test_reads_openclaw_channel_group_message_logs(self) -> None:
        wrapped = {
            "file": "/tmp/openclaw/openclaw-2026-05-02.log",
            "channel": "feishu",
            "lines": [
                {
                    "time": "2026-05-02T12:08:57.320+08:00",
                    "message": (
                        '{"subsystem":"gateway/channels/feishu"} '
                        "feishu[default]: Feishu[default] message in group oc_passive_gate: "
                        "决定：非 @ 群消息 live gate 复测，权限更新后验证事件投递。"
                    ),
                }
            ],
        }

        report = check_passive_message_events(
            json.dumps(wrapped, ensure_ascii=False),
            expected_chat_id="oc_passive_gate",
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual("passive_group_message_seen", report["reason"])
        self.assertEqual(1, report["summary"]["passive_group_text_messages"])

    def test_reads_plaintext_openclaw_channel_group_message_logs(self) -> None:
        raw_log = (
            "2026-05-02T16:55:20.344+08:00 [feishu] "
            "feishu[default]: Feishu[default] message in group oc_passive_gate: "
            "决定：非 @ 群消息 live gate 测试，今天只验证事件投递。"
        )

        report = check_passive_message_events(raw_log, expected_chat_id="oc_passive_gate")

        self.assertTrue(report["ok"], report)
        self.assertEqual("passive_group_message_seen", report["reason"])
        self.assertEqual(1, report["summary"]["passive_group_text_messages"])

    def test_reads_openclaw_file_log_numbered_fields(self) -> None:
        wrapped = {
            "0": (
                '2026-05-02T12:08:57.320+08:00 info {"subsystem":"gateway/channels/feishu"} '
                "feishu[default]: Feishu[default] message in group oc_passive_gate: "
                "决定：非 @ 群消息 live gate 复测，权限更新后验证事件投递。"
            ),
            "_meta": {"date": "2026-05-02T04:36:37.519Z"},
            "time": "2026-05-02T12:36:37.519+08:00",
        }

        report = check_passive_message_events(
            json.dumps(wrapped, ensure_ascii=False),
            expected_chat_id="oc_passive_gate",
        )

        self.assertTrue(report["ok"], report)
        self.assertEqual("passive_group_message_seen", report["reason"])
        self.assertEqual(1, report["summary"]["passive_group_text_messages"])


if __name__ == "__main__":
    unittest.main()
