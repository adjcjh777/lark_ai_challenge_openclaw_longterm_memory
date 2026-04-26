from __future__ import annotations

import json
import unittest
from pathlib import Path

from memory_engine.db import connect, init_db
from memory_engine.feishu_cards import build_card_from_text
from memory_engine.feishu_config import FeishuConfig
from memory_engine.feishu_events import message_event_from_payload
from memory_engine.feishu_publisher import LarkCliPublisher
from memory_engine.feishu_runtime import handle_message_event
from temp_utils import WorkspaceTempDir


class FakePublisher(LarkCliPublisher):
    def __init__(self, config: FeishuConfig, outcomes: list[bool | dict]):
        super().__init__(config)
        self.outcomes = outcomes
        self.modes: list[str] = []
        self.timeouts: list[float | None] = []

    def _run(self, command, mode, event, text, *, card=None, timeout=None):  # type: ignore[override]
        self.modes.append(mode)
        self.timeouts.append(timeout)
        outcome = self.outcomes.pop(0) if self.outcomes else True
        if isinstance(outcome, dict):
            ok = bool(outcome.get("ok"))
            timed_out = bool(outcome.get("timed_out"))
            stderr = outcome.get("stderr") or ("simulated timeout" if timed_out else "simulated failure")
            returncode = outcome.get("returncode", None if timed_out else (0 if ok else 1))
        else:
            ok = outcome
            timed_out = False
            stderr = "" if ok else "simulated failure"
            returncode = 0 if ok else 1
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


def text_payload(message_id: str, text: str) -> dict:
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_test"}, "sender_type": "user"},
            "message": {
                "message_id": message_id,
                "chat_id": "oc_test",
                "chat_type": "group",
                "message_type": "text",
                "content": f'{{"text":"{text}"}}',
                "create_time": "1777000000000",
            },
        },
    }


def card_action_payload(action: str, memory_id: str, *, candidate_index: int | None = None) -> dict:
    value = {
        "memory_engine_action": action,
        "memory_id": memory_id,
        "candidate_id": memory_id,
    }
    if candidate_index is not None:
        value["candidate_index"] = str(candidate_index)
        value["candidate_label"] = f"候选 {candidate_index}"
    return {
        "schema": "2.0",
        "header": {"event_type": "card.action.trigger"},
        "event": {
            "token": "card_token_1",
            "operator": {"open_id": "ou_operator"},
            "context": {"open_chat_id": "oc_test"},
            "action": {"value": value},
        },
    }


class FeishuInteractiveCardsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = WorkspaceTempDir("feishu_interactive_cards")
        self.db_path = Path(self.temp_dir.name) / "memory.sqlite"
        self.conn = connect(self.db_path)
        init_db(self.conn)
        self.config = FeishuConfig(
            bot_mode="reply",
            default_scope="project:feishu_ai_challenge",
            lark_cli="lark-cli",
            lark_profile="feishu-ai-challenge",
            lark_as="bot",
            reply_in_thread=False,
        )

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    def test_interactive_card_success_does_not_send_text_fallback(self) -> None:
        event = message_event_from_payload(text_payload("om_card_success", "/remember 生产部署必须加 --canary"))
        self.assertIsNotNone(event)
        publisher = FakePublisher(self.config, [True])

        result = handle_message_event(self.conn, event, publisher, self.config, db_path=self.db_path)

        self.assertTrue(result["ok"])
        self.assertEqual(["reply_card"], publisher.modes)
        self.assertEqual([2.0], publisher.timeouts)
        self.assertFalse(result["publish"]["fallback_used"])
        self.assertIsNotNone(result["publish"]["card"])
        json.dumps(result, ensure_ascii=False)

    def test_text_fallback_runs_only_after_three_card_failures(self) -> None:
        event = message_event_from_payload(text_payload("om_card_fallback", "/remember 生产部署必须加 --canary"))
        self.assertIsNotNone(event)
        publisher = FakePublisher(self.config, [False, False, False, True])

        result = handle_message_event(self.conn, event, publisher, self.config, db_path=self.db_path)

        self.assertTrue(result["ok"])
        self.assertEqual(["reply_card", "reply_card", "reply_card", "reply_text"], publisher.modes)
        self.assertTrue(result["publish"]["fallback_used"])
        self.assertEqual(3, len(result["publish"]["card_attempts"]))
        self.assertEqual([2.0, 2.0, 2.0, None], publisher.timeouts)
        json.dumps(result, ensure_ascii=False)

    def test_timeout_suppresses_text_fallback_to_avoid_double_send(self) -> None:
        event = message_event_from_payload(text_payload("om_card_timeout", "/remember 生产部署必须加 --canary"))
        self.assertIsNotNone(event)
        publisher = FakePublisher(
            self.config,
            [
                {"ok": False, "timed_out": True},
                {"ok": False, "timed_out": True},
                {"ok": False, "timed_out": True},
            ],
        )

        result = handle_message_event(self.conn, event, publisher, self.config, db_path=self.db_path)

        self.assertFalse(result["ok"])
        self.assertEqual(["reply_card", "reply_card", "reply_card"], publisher.modes)
        self.assertFalse(result["publish"]["fallback_used"])
        self.assertTrue(result["publish"]["fallback_suppressed"])
        self.assertEqual("interactive_card_timeout_ambiguous", result["publish"]["fallback_reason"])
        json.dumps(result, ensure_ascii=False)

    def test_long_card_action_idempotency_key_is_shortened(self) -> None:
        event = message_event_from_payload(card_action_payload("versions", "mem_demo"))
        self.assertIsNotNone(event)
        long_event = event.as_text_event()
        long_event = type(long_event)(
            message_id="card_action_" + "x" * 80,
            chat_id=long_event.chat_id,
            chat_type=long_event.chat_type,
            sender_id=long_event.sender_id,
            sender_type=long_event.sender_type,
            message_type=long_event.message_type,
            text=long_event.text,
            create_time=long_event.create_time,
            raw=long_event.raw,
        )
        publisher = LarkCliPublisher(self.config)

        key = publisher._idempotency_key(long_event)

        self.assertLessEqual(len(key), 64)
        self.assertTrue(key.startswith("feishu-memory-"))

    def test_ingest_card_buttons_only_target_candidate_rows(self) -> None:
        text = "\n".join(
            [
                "已从文档抽取候选记忆，等待人工确认。",
                "卡片：人工确认队列",
                "结论：已抽取候选记忆，等待人工确认",
                "理由：文档 ingestion 先进入 candidate 状态，确认后才成为 active 企业记忆",
                "状态：candidate",
                "版本：Day 5",
                "来源：Memory Engine",
                "是否被覆盖：否",
                "已生效：mem_active [active] 生产部署：已确认内容（confidence=0.75）",
                "候选 1：mem_candidate1 [candidate] 飞书接入：候选一（confidence=0.75；建议动作：/confirm mem_candidate1 或 /reject mem_candidate1）",
                "候选 2：mem_candidate2 [candidate] Benchmark：候选二（confidence=0.75；建议动作：/confirm mem_candidate2 或 /reject mem_candidate2）",
            ]
        )

        card = build_card_from_text(text)
        action_blocks = [element for element in card["elements"] if element.get("tag") == "action"]
        self.assertEqual(1, len(action_blocks))
        labels = [button["text"]["content"] for button in action_blocks[0]["actions"]]
        values = [button["value"].get("candidate_id") for button in action_blocks[0]["actions"]]

        self.assertEqual(["确认候选 1", "拒绝候选 1", "确认候选 2", "拒绝候选 2"], labels)
        self.assertNotIn("mem_active", values)
        self.assertEqual("候选 1", action_blocks[0]["actions"][0]["value"]["candidate_label"])

    def test_card_action_event_routes_to_existing_command(self) -> None:
        ingest = message_event_from_payload(text_payload("om_ingest_for_card", "/ingest_doc tests/fixtures/day5_doc_ingestion_fixture.md"))
        self.assertIsNotNone(ingest)
        handle_message_event(self.conn, ingest, FakePublisher(self.config, [True]), self.config, db_path=self.db_path)
        row = self.conn.execute("SELECT id FROM memories WHERE status = 'candidate' LIMIT 1").fetchone()
        self.assertIsNotNone(row)

        event = message_event_from_payload(card_action_payload("confirm", row["id"]))
        self.assertIsNotNone(event)
        publisher = FakePublisher(self.config, [True])
        result = handle_message_event(self.conn, event, publisher, self.config, db_path=self.db_path)

        self.assertEqual("confirm", result["command"])
        self.assertIn("send_card", publisher.modes)
        status = self.conn.execute("SELECT status FROM memories WHERE id = ?", (row["id"],)).fetchone()["status"]
        self.assertEqual("active", status)

    def test_card_action_result_preserves_candidate_label(self) -> None:
        ingest = message_event_from_payload(text_payload("om_ingest_for_card_label", "/ingest_doc tests/fixtures/day5_doc_ingestion_fixture.md"))
        self.assertIsNotNone(ingest)
        handle_message_event(self.conn, ingest, FakePublisher(self.config, [True]), self.config, db_path=self.db_path)
        row = self.conn.execute("SELECT id FROM memories WHERE status = 'candidate' LIMIT 1").fetchone()
        self.assertIsNotNone(row)

        event = message_event_from_payload(card_action_payload("reject", row["id"], candidate_index=2))
        self.assertIsNotNone(event)
        result = handle_message_event(self.conn, event, FakePublisher(self.config, [True]), self.config, db_path=self.db_path)

        self.assertEqual("reject", result["command"])
        field_texts = [field["text"]["content"] for field in result["publish"]["card"]["elements"][0]["fields"]]
        self.assertTrue(any("候选序号" in text and "候选 2" in text for text in field_texts))


if __name__ == "__main__":
    unittest.main()
