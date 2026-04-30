from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memory_engine.copilot.service import CopilotService
from memory_engine.copilot.tools import handle_tool_request
from memory_engine.db import connect, init_db
from memory_engine.feishu_cards import (
    build_candidate_review_card,
    build_card_from_text,
    build_prefetch_context_card,
    build_reminder_candidate_card,
    build_review_inbox_card,
    build_search_result_card,
    build_version_chain_card,
    candidate_review_payload,
    prefetch_context_payload,
    reminder_candidate_payload,
    search_result_payload,
    version_chain_payload,
)
from memory_engine.feishu_config import FeishuConfig
from memory_engine.feishu_events import message_event_from_payload
from memory_engine.feishu_publisher import LarkCliPublisher
from memory_engine.feishu_runtime import handle_message_event
from memory_engine.repository import MemoryRepository


class FakePublisher(LarkCliPublisher):
    def __init__(self, config: FeishuConfig, outcomes: list[bool | dict]):
        super().__init__(config)
        self.outcomes = outcomes
        self.modes: list[str] = []
        self.timeouts: list[float | None] = []
        self.commands: list[list[str]] = []

    def _run(self, command, mode, event, text, *, card=None, timeout=None):  # type: ignore[override]
        self.commands.append(command)
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


def copilot_context(
    action: str, *, roles: list[str] | None = None, request_id: str | None = None, trace_id: str | None = None
) -> dict:
    return {
        "scope": "project:feishu_ai_challenge",
        "permission": {
            "request_id": request_id or f"req_{action.replace('.', '_')}",
            "trace_id": trace_id or f"trace_{action.replace('.', '_')}",
            "actor": {
                "user_id": "ou_operator",
                "tenant_id": "tenant:demo",
                "organization_id": "org:demo",
                "roles": roles if roles is not None else ["member", "reviewer"],
            },
            "source_context": {"entrypoint": "feishu_review_surface", "workspace_id": "project:feishu_ai_challenge"},
            "requested_action": action,
            "requested_visibility": "team",
            "timestamp": "2026-05-07T00:00:00+08:00",
        },
    }


def card_action_payload(
    action: str,
    memory_id: str,
    *,
    candidate_index: int | None = None,
    extra_value: dict | None = None,
) -> dict:
    value = {
        "memory_engine_action": action,
        "memory_id": memory_id,
        "candidate_id": memory_id,
    }
    if extra_value:
        value.update(extra_value)
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
        self.temp_dir = tempfile.TemporaryDirectory()
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

    def test_targeted_review_card_failure_suppresses_public_text_fallback(self) -> None:
        event = message_event_from_payload(text_payload("om_targeted_card_fallback", "/review"))
        self.assertIsNotNone(event)
        publisher = FakePublisher(self.config, [False, False, False])
        card = build_review_inbox_card(
            {
                "delivery_channel": "routed_private_review",
                "open_ids": ["ou_owner"],
                "counts": {"all": 1, "mine": 1},
                "items": [],
            }
        )

        result = publisher.publish(event, "这里包含不应回退到群聊的审核文本", card)

        self.assertFalse(result["ok"])
        self.assertFalse(result["fallback_used"])
        self.assertTrue(result["fallback_suppressed"])
        self.assertEqual("targeted_review_card_text_fallback_suppressed", result["fallback_reason"])
        self.assertEqual(["reply_card", "reply_card", "reply_card"], publisher.modes)

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

    def test_card_action_event_routes_to_existing_command_and_fails_closed_without_permission(self) -> None:
        ingest = message_event_from_payload(
            text_payload("om_ingest_for_card", "/ingest_doc tests/fixtures/day5_doc_ingestion_fixture.md")
        )
        self.assertIsNotNone(ingest)
        handle_message_event(self.conn, ingest, FakePublisher(self.config, [True]), self.config, db_path=self.db_path)
        row = self.conn.execute("SELECT id FROM memories WHERE status = 'candidate' LIMIT 1").fetchone()
        self.assertIsNotNone(row)

        event = message_event_from_payload(card_action_payload("confirm", row["id"]))
        self.assertIsNotNone(event)
        publisher = FakePublisher(self.config, [True])
        result = handle_message_event(self.conn, event, publisher, self.config, db_path=self.db_path)

        self.assertEqual("confirm", result["command"])
        self.assertIn("update_card", publisher.modes)
        self.assertFalse(result["tool_result"]["ok"])
        self.assertEqual("permission_denied", result["tool_result"]["error"]["code"])
        self.assertEqual("missing_permission_context", result["tool_result"]["error"]["details"]["reason_code"])
        status = self.conn.execute("SELECT status FROM memories WHERE id = ?", (row["id"],)).fetchone()["status"]
        self.assertEqual("candidate", status)

    def test_card_action_result_preserves_candidate_label(self) -> None:
        ingest = message_event_from_payload(
            text_payload("om_ingest_for_card_label", "/ingest_doc tests/fixtures/day5_doc_ingestion_fixture.md")
        )
        self.assertIsNotNone(ingest)
        handle_message_event(self.conn, ingest, FakePublisher(self.config, [True]), self.config, db_path=self.db_path)
        row = self.conn.execute("SELECT id FROM memories WHERE status = 'candidate' LIMIT 1").fetchone()
        self.assertIsNotNone(row)

        event = message_event_from_payload(card_action_payload("reject", row["id"], candidate_index=2))
        self.assertIsNotNone(event)
        result = handle_message_event(
            self.conn, event, FakePublisher(self.config, [True]), self.config, db_path=self.db_path
        )

        self.assertEqual("reject", result["command"])
        field_texts = [field["text"]["content"] for field in result["publish"]["card"]["elements"][0]["fields"]]
        self.assertTrue(any("候选序号" in text and "候选 2" in text for text in field_texts))

    def test_card_action_updates_original_interactive_card(self) -> None:
        ingest = message_event_from_payload(
            text_payload("om_ingest_for_card_update", "/ingest_doc tests/fixtures/day5_doc_ingestion_fixture.md")
        )
        self.assertIsNotNone(ingest)
        handle_message_event(self.conn, ingest, FakePublisher(self.config, [True]), self.config, db_path=self.db_path)
        row = self.conn.execute("SELECT id FROM memories WHERE status = 'candidate' LIMIT 1").fetchone()
        self.assertIsNotNone(row)

        event = message_event_from_payload(card_action_payload("reject", row["id"]))
        self.assertIsNotNone(event)
        publisher = FakePublisher(self.config, [True])
        result = handle_message_event(self.conn, event, publisher, self.config, db_path=self.db_path)

        self.assertEqual("reject", result["command"])
        self.assertEqual(["update_card"], publisher.modes)
        self.assertEqual("card_token_1", result["publish"]["card_update_token"])
        data = json.loads(publisher.commands[0][publisher.commands[0].index("--data") + 1])
        self.assertEqual(["ou_operator"], data["card"]["open_ids"])

    def test_copilot_candidate_review_payload_marks_conflict_without_mutation(self) -> None:
        response = {
            "candidate_id": "ver_new",
            "memory_id": "mem_1",
            "version_id": "ver_new",
            "status": "candidate",
            "recommended_action": "review_conflict",
            "risk_flags": ["conflict_candidate"],
            "evidence": {
                "source_type": "unit_test",
                "source_id": "msg_1",
                "quote": "不对，生产部署 region 改成 ap-shanghai。",
            },
            "conflict": {
                "has_conflict": True,
                "old_memory_id": "mem_1",
                "old_value": "生产部署 region 固定 cn-shanghai。",
                "old_status": "active",
            },
            "candidate": {
                "candidate_id": "ver_new",
                "memory_id": "mem_1",
                "version_id": "ver_new",
                "status": "candidate",
                "visibility_policy": "project",
                "type": "workflow",
                "subject": "生产部署",
                "current_value": "不对，生产部署 region 改成 ap-shanghai。",
                "summary": "覆盖旧 region",
            },
        }

        payload = candidate_review_payload(response)
        card = build_candidate_review_card(response)
        rendered = json.dumps(card, ensure_ascii=False)

        self.assertEqual("copilot_candidate_review", payload["surface"])
        self.assertEqual("none", payload["state_mutation"])
        self.assertTrue(payload["conflict"]["has_conflict"])
        self.assertEqual("当前项目", payload["scope_hint"])
        self.assertEqual("pending", payload["review_status"])
        self.assertEqual("medium", payload["risk_level"])
        self.assertEqual("overrides_active", payload["conflict_status"])
        self.assertIn("待我审核", payload["queue_views"])
        self.assertIn("冲突需判断", payload["queue_views"])
        self.assertIn("确认保存", [action["label"] for action in payload["buttons"]])
        self.assertIn("确认合并", [action["label"] for action in payload["buttons"]])
        self.assertIn("要求补证据", [action["label"] for action in payload["buttons"]])
        self.assertIn("标记过期", [action["label"] for action in payload["buttons"]])
        self.assertEqual("orange", card["header"]["template"])
        self.assertIn("旧结论", rendered)
        self.assertIn("生产部署 region 固定 cn-shanghai。", rendered)
        self.assertIn("新结论", rendered)
        self.assertIn("生产部署 region 改成 ap-shanghai。", rendered)
        self.assertIn("适用范围", rendered)
        self.assertIn("当前项目", rendered)
        self.assertNotIn("**candidate_id**", rendered)
        self.assertNotIn("**memory_id**", rendered)
        self.assertNotIn("**trace_id**", rendered)
        self.assertNotIn("**request_id**", rendered)

    def test_copilot_candidate_review_payload_marks_high_risk_review_view(self) -> None:
        response = {
            "candidate_id": "mem_secret",
            "memory_id": "mem_secret",
            "version_id": "ver_secret",
            "status": "candidate",
            "recommended_action": "manual_review_sensitive",
            "risk_flags": ["sensitive_content"],
            "evidence": {
                "source_type": "feishu_message",
                "source_id": "msg_secret",
                "quote": "规则：临时 app_secret=abc123456789 只能本地调试。",
            },
            "conflict": {"has_conflict": False},
            "candidate": {
                "candidate_id": "mem_secret",
                "memory_id": "mem_secret",
                "version_id": "ver_secret",
                "status": "candidate",
                "type": "risk",
                "subject": "临时密钥",
                "current_value": "规则：临时 app_secret=abc123456789 只能本地调试。",
                "summary": "敏感内容需要人工判断",
            },
            "bridge": {
                "request_id": "req_secret_review",
                "trace_id": "trace_secret_review",
                "permission_decision": {
                    "decision": "allow",
                    "reason_code": "scope_access_granted",
                    "actor": {"user_id": "ou_reviewer", "roles": ["member", "reviewer"]},
                },
            },
        }

        payload = candidate_review_payload(response)
        card = build_candidate_review_card(response)
        rendered = json.dumps(card, ensure_ascii=False)

        self.assertEqual("high", payload["risk_level"])
        self.assertEqual("no_conflict", payload["conflict_status"])
        self.assertIn("高风险暂不建议确认", payload["queue_views"])
        self.assertEqual("ou_reviewer", payload["reviewer"])
        self.assertIn("要求补证据", rendered)
        self.assertIn("标记过期", rendered)

    def test_candidate_review_card_hides_internal_queue_and_risk_details(self) -> None:
        response = {
            "candidate_id": "ver_simple",
            "memory_id": "mem_simple",
            "status": "candidate",
            "recommended_action": "manual_review_conflict",
            "risk_flags": ["conflict_candidate", "override_intent"],
            "candidate": {
                "candidate_id": "ver_simple",
                "memory_id": "mem_simple",
                "status": "candidate",
                "type": "decision",
                "subject": "部署窗口",
                "current_value": "决定：周五 18:00 前完成灰度发布。",
                "summary": "灰度发布窗口",
                "conflict": {
                    "has_conflict": True,
                    "old_value": "决定：周四 18:00 前完成灰度发布。",
                },
            },
            "evidence": {"quote": "决定：周五 18:00 前完成灰度发布。", "source_type": "feishu_message"},
            "bridge": {
                "request_id": "req_simple_card",
                "trace_id": "trace_simple_card",
                "permission_decision": {
                    "decision": "allow",
                    "reason_code": "scope_access_granted",
                    "actor": {"user_id": "ou_reviewer", "roles": ["member", "reviewer"]},
                },
            },
        }

        card = build_candidate_review_card(response)
        rendered = json.dumps(card, ensure_ascii=False)

        self.assertIn("待确认", rendered)
        self.assertIn("决定：周五 18:00 前完成灰度发布。", rendered)
        self.assertIn("旧结论", rendered)
        self.assertIn("新结论", rendered)
        self.assertIn("适用范围", rendered)
        self.assertIn("当前团队范围", rendered)
        self.assertIn("确认保存", rendered)
        self.assertIn("确认合并", rendered)
        self.assertNotIn("队列视图", rendered)
        self.assertNotIn("操作建议", rendered)
        self.assertNotIn("conflict_candidate", rendered)
        self.assertNotIn("**candidate_id**", rendered)
        self.assertNotIn("**memory_id**", rendered)
        self.assertNotIn("**trace_id**", rendered)
        self.assertNotIn("**request_id**", rendered)

    def test_candidate_review_card_limits_visibility_for_routed_private_review_targets(self) -> None:
        response = {
            "candidate_id": "ver_private_review",
            "memory_id": "mem_private_review",
            "status": "candidate",
            "delivery_channel": "routed_private_review",
            "review_targets": ["ou_owner", "ou_reviewer"],
            "candidate": {
                "type": "decision",
                "subject": "发布审批",
                "current_value": "决定：发布审批由 owner 和 reviewer 双人确认。",
                "summary": "私聊审核目标",
            },
            "evidence": {"quote": "决定：发布审批由 owner 和 reviewer 双人确认。", "source_type": "feishu_message"},
            "review_policy": {
                "delivery_channel": "routed_private_review",
                "review_targets": ["ou_owner", "ou_reviewer"],
            },
            "bridge": {
                "permission_decision": {
                    "decision": "allow",
                    "reason_code": "scope_access_granted",
                    "actor": {"user_id": "ou_owner", "roles": ["member", "owner"]},
                },
            },
        }

        card = build_candidate_review_card(response)

        self.assertEqual(["ou_owner", "ou_reviewer"], card["open_ids"])

    def test_candidate_review_card_does_not_add_open_ids_without_targets(self) -> None:
        response = {
            "candidate_id": "ver_no_targets",
            "memory_id": "mem_no_targets",
            "status": "candidate",
            "review_policy": {"delivery_channel": "routed_private_review"},
            "candidate": {
                "type": "decision",
                "subject": "无目标审核",
                "current_value": "决定：没有目标时不要限制可见人。",
            },
            "evidence": {"quote": "决定：没有目标时不要限制可见人。"},
        }

        card = build_candidate_review_card(response)

        self.assertNotIn("open_ids", card)

    def test_terminal_candidate_review_card_shows_only_undo_action(self) -> None:
        response = {
            "candidate_id": "mem_terminal_undo",
            "memory_id": "mem_terminal_undo",
            "status": "active",
            "review_status": "confirmed",
            "action": "confirmed",
            "memory": {
                "type": "decision",
                "subject": "撤销入口",
                "current_value": "决定：确认后的卡片只保留撤销入口。",
                "status": "active",
                "owner_id": "ou_owner",
            },
            "bridge": {
                "permission_decision": {
                    "decision": "allow",
                    "reason_code": "scope_access_granted",
                    "actor": {"user_id": "ou_owner", "roles": ["owner"]},
                }
            },
        }

        card = build_candidate_review_card(response)
        actions = [element for element in card["elements"] if element.get("tag") == "action"]

        self.assertEqual(1, len(actions))
        labels = [action["text"]["content"] for action in actions[0]["actions"]]
        self.assertEqual(["撤销这次处理"], labels)
        self.assertNotIn("确认保存", json.dumps(card, ensure_ascii=False))

    def test_review_inbox_card_summarizes_items_and_hides_internal_ids(self) -> None:
        inbox_response = {
            "counts": {"pending": 2, "conflict": 1, "high_risk": 1},
            "review_targets": ["ou_owner", "ou_reviewer"],
            "items": [
                {
                    "candidate_id": "cand_internal_1",
                    "memory_id": "mem_internal_1",
                    "request_id": "req_internal_1",
                    "trace_id": "trace_internal_1",
                    "subject": "生产部署",
                    "new_value": "生产部署 region 改成 ap-shanghai。",
                    "old_value": "生产部署 region 固定 cn-shanghai。",
                    "evidence": {"quote": "不对，生产部署 region 以后统一改成 ap-shanghai。"},
                    "scope_hint": "当前项目",
                    "recommended_action": "确认是否覆盖旧规则",
                },
                {
                    "candidate_id": "cand_internal_2",
                    "memory_id": "mem_internal_2",
                    "subject": "临时密钥",
                    "current_value": "临时 app_secret 只能本地调试。",
                    "evidence": "安全同学提醒：临时 app_secret 只能本地调试。",
                    "scope": "本组织",
                    "recommended_action": "要求补证据",
                },
            ],
        }

        card = build_review_inbox_card(inbox_response)
        rendered = json.dumps(card, ensure_ascii=False)
        visible_rendered = json.dumps(
            [element for element in card["elements"] if element.get("tag") != "action"],
            ensure_ascii=False,
        )

        self.assertEqual("待审核记忆", card["header"]["title"]["content"])
        self.assertEqual(["ou_owner", "ou_reviewer"], card["open_ids"])
        self.assertIn("待处理: 2", rendered)
        self.assertIn("冲突需判断: 1", rendered)
        self.assertIn("主题", rendered)
        self.assertIn("生产部署", rendered)
        self.assertIn("新结论", rendered)
        self.assertIn("生产部署 region 改成 ap-shanghai。", rendered)
        self.assertIn("旧结论", rendered)
        self.assertIn("生产部署 region 固定 cn-shanghai。", rendered)
        self.assertIn("证据", rendered)
        self.assertIn("适用范围", rendered)
        self.assertIn("建议动作", rendered)
        self.assertIn("确认第1条", rendered)
        self.assertIn("拒绝第1条", rendered)
        self.assertIn("补证据第1条", rendered)
        action_blocks = [element for element in card["elements"] if element.get("tag") == "action"]
        self.assertGreaterEqual(len(action_blocks), 1)
        self.assertEqual("cand_internal_1", action_blocks[0]["actions"][0]["value"]["candidate_id"])
        for hidden in (
            "candidate_id",
            "memory_id",
            "request_id",
            "trace_id",
            "cand_internal_1",
            "mem_internal_1",
            "req_internal_1",
            "trace_internal_1",
            "cand_internal_2",
            "mem_internal_2",
        ):
            self.assertNotIn(hidden, visible_rendered)

    def test_review_inbox_card_does_not_add_open_ids_without_targets(self) -> None:
        card = build_review_inbox_card({"counts": {"pending": 0}, "items": []})

        self.assertNotIn("open_ids", card)

    def test_candidate_review_card_maps_visibility_policy_to_user_scope_hint(self) -> None:
        cases = [
            ("private", "仅自己"),
            ("team", "本群或团队"),
            ("organization", "本组织"),
            ("project", "当前项目"),
        ]
        for visibility_policy, expected in cases:
            with self.subTest(visibility_policy=visibility_policy):
                response = {
                    "candidate_id": f"ver_{visibility_policy}",
                    "memory_id": f"mem_{visibility_policy}",
                    "status": "candidate",
                    "visibility_policy": visibility_policy,
                    "candidate": {
                        "type": "decision",
                        "subject": "适用范围测试",
                        "current_value": "决定：按范围展示。",
                    },
                    "evidence": {"quote": "决定：按范围展示。", "source_type": "unit_test"},
                }

                payload = candidate_review_payload(response)
                rendered = json.dumps(build_candidate_review_card(response), ensure_ascii=False)

                self.assertEqual(expected, payload["scope_hint"])
                self.assertIn("适用范围", rendered)
                self.assertIn(expected, rendered)

    def test_copilot_candidate_review_payload_hides_reviewer_buttons_for_member(self) -> None:
        response = {
            "candidate_id": "ver_member",
            "memory_id": "mem_member",
            "status": "candidate",
            "candidate": {
                "candidate_id": "ver_member",
                "memory_id": "mem_member",
                "type": "workflow",
                "subject": "生产部署",
                "current_value": "生产部署必须加 --canary。",
                "summary": "待确认部署规则",
            },
            "evidence": {"quote": "生产部署必须加 --canary。"},
            "bridge": {
                "request_id": "req_member_candidate",
                "trace_id": "trace_member_candidate",
                "permission_decision": {
                    "decision": "allow",
                    "reason_code": "scope_access_granted",
                    "actor": {"user_id": "ou_member", "roles": ["member"]},
                },
            },
        }

        payload = candidate_review_payload(response)
        card = build_candidate_review_card(response)
        rendered = json.dumps(card, ensure_ascii=False)

        self.assertEqual([], payload["buttons"])
        self.assertEqual("candidate", payload["status"])
        self.assertNotIn("确认保存", rendered)
        self.assertNotIn("拒绝候选", rendered)

    def test_copilot_candidate_review_payload_hides_buttons_after_confirm(self) -> None:
        response = {
            "ok": True,
            "action": "confirmed",
            "candidate_id": "ver_confirmed",
            "memory_id": "mem_confirmed",
            "status": "active",
            "review_status": "confirmed",
            "owner_id": "ou_owner",
            "candidate": {
                "candidate_id": "ver_confirmed",
                "memory_id": "mem_confirmed",
                "status": "candidate",
                "type": "workflow",
                "subject": "生产部署",
                "current_value": "生产部署必须加 --canary。",
                "summary": "已确认部署规则",
            },
            "memory": {
                "memory_id": "mem_confirmed",
                "owner_id": "ou_owner",
                "status": "active",
                "type": "workflow",
                "subject": "生产部署",
                "current_value": "生产部署必须加 --canary。",
                "summary": "已确认部署规则",
            },
            "evidence": {"quote": "生产部署必须加 --canary。", "source_type": "feishu_message"},
            "bridge": {
                "request_id": "req_confirmed_card",
                "trace_id": "trace_confirmed_card",
                "permission_decision": {
                    "decision": "allow",
                    "reason_code": "scope_access_granted",
                    "actor": {"user_id": "ou_owner", "roles": ["member", "owner"]},
                },
            },
        }

        payload = candidate_review_payload(response)
        card = build_candidate_review_card(response)
        actions = [element for element in card["elements"] if element.get("tag") == "action"]

        self.assertEqual("confirmed", payload["review_status"])
        self.assertEqual("confirmed", payload["state_mutation"])
        self.assertEqual(["undo"], [button["action"] for button in payload["buttons"]])
        self.assertEqual(["撤销这次处理"], [action["text"]["content"] for action in actions[0]["actions"]])
        self.assertNotIn("确认保存", json.dumps(card, ensure_ascii=False))

    def test_copilot_search_result_payload_separates_user_content_and_audit(self) -> None:
        response = {
            "ok": True,
            "query": "生产部署 region",
            "results": [
                {
                    "memory_id": "mem_region",
                    "subject": "生产部署",
                    "current_value": "生产部署 region 用 ap-shanghai。",
                    "status": "active",
                    "version": 2,
                    "rank": 1,
                    "evidence": [
                        {
                            "source_type": "feishu_message",
                            "source_id": "msg_region",
                            "quote": "不对，生产部署 region 以后统一改成 ap-shanghai。",
                        }
                    ],
                    "matched_via": ["active", "evidence", "superseded_filtered"],
                    "why_ranked": {"score": 0.98, "reason": "subject_match"},
                }
            ],
            "trace": {"returned_count": 1, "final_reason": "l1_hot_hit"},
            "bridge": {
                "request_id": "req_search_card",
                "trace_id": "trace_search_card",
                "permission_decision": {"decision": "allow", "reason_code": "scope_access_granted"},
            },
        }

        payload = search_result_payload(response)
        card = build_search_result_card(response)
        rendered = json.dumps(card, ensure_ascii=False)

        self.assertEqual("copilot_search_results", payload["surface"])
        self.assertEqual("none", payload["state_mutation"])
        self.assertEqual("生产部署 region 用 ap-shanghai。", payload["user_content"]["results"][0]["current_conclusion"])
        self.assertTrue(payload["user_content"]["results"][0]["superseded_filtered"])
        self.assertIn("命中当前 active 记忆", payload["user_content"]["results"][0]["rank_reason"])
        self.assertIn("证据内容与问题相关", payload["user_content"]["results"][0]["rank_reason"])
        self.assertIn("旧版本已过滤", payload["user_content"]["results"][0]["rank_reason"])
        self.assertIn("默认结果已过滤 superseded 旧值", payload["user_content"]["results"][0]["explanation"])
        self.assertEqual("req_search_card", payload["audit_details"]["request_id"])
        self.assertIn("解释版本", [button["label"] for button in payload["buttons"]])
        self.assertIn("当前结论", rendered)
        self.assertIn("为什么采用", rendered)
        self.assertIn("已过滤旧值", rendered)

    def test_copilot_prefetch_payload_uses_compact_context_pack(self) -> None:
        response = {
            "ok": True,
            "tool": "memory.prefetch",
            "task": "准备上线 checklist",
            "context_pack": {
                "summary": "准备上线 checklist: 找到 2 条 active 记忆。",
                "relevant_memories": [
                    {
                        "memory_id": "mem_rule",
                        "subject": "部署规则",
                        "current_value": "生产部署必须加 --canary。",
                        "status": "active",
                        "version": 1,
                        "evidence": [{"quote": "生产部署必须加 --canary。"}],
                    }
                ],
                "risks": [{"subject": "回滚风险", "current_value": "上线前必须提前录屏。"}],
                "deadlines": [{"subject": "截止时间", "current_value": "周五前提交。"}],
                "stale_superseded_filtered": True,
                "raw_events_included": False,
            },
            "bridge": {
                "request_id": "req_prefetch_card",
                "trace_id": "trace_prefetch_card",
                "permission_decision": {"decision": "allow", "reason_code": "scope_access_granted"},
            },
        }

        payload = prefetch_context_payload(response)
        card = build_prefetch_context_card(response)
        rendered = json.dumps({"payload": payload, "card": card}, ensure_ascii=False)

        self.assertEqual("copilot_prefetch_context", payload["surface"])
        self.assertEqual("none", payload["state_mutation"])
        self.assertEqual("准备上线 checklist", payload["user_content"]["task"])
        self.assertFalse(payload["user_content"]["raw_events_included"])
        self.assertTrue(payload["user_content"]["superseded_filtered"])
        self.assertEqual([], payload["buttons"])
        self.assertIn("生产部署必须加 --canary", rendered)
        self.assertNotIn("raw events", rendered)

    def test_reminder_candidate_payload_exposes_review_actions_and_redaction(self) -> None:
        reminder = {
            "reminder_id": "rem_mem_1_deadline",
            "memory_id": "mem_1",
            "scope": "project:feishu_ai_challenge",
            "subject": "提交材料",
            "current_value": "提交材料截止时间是 2026-05-07。",
            "reason": "任务前提醒",
            "trigger": "deadline",
            "status": "candidate",
            "due_at": "2026-05-07",
            "evidence": {"quote": "提交材料截止时间是 2026-05-07。"},
            "target_actor": {"user_id": "ou_reviewer", "roles": ["member", "reviewer"]},
            "cooldown": {"cooldown_ms": 86400000, "passed": True, "next_allowed_at": 1778000000000},
            "actions": [
                {"action": "confirm_useful", "label": "确认提醒有用"},
                {"action": "ignore", "label": "忽略本次"},
                {"action": "snooze", "label": "延后"},
                {"action": "mute_same_type", "label": "关闭同类提醒"},
            ],
            "permission_trace": {
                "request_id": "req_reminder_card",
                "trace_id": "trace_reminder_card",
                "decision": "allow",
                "reason_code": "scope_access_granted",
            },
        }

        payload = reminder_candidate_payload(reminder)
        card = build_reminder_candidate_card(reminder)
        rendered = json.dumps({"payload": payload, "card": card}, ensure_ascii=False)

        self.assertEqual(
            ["confirm_useful", "ignore", "snooze", "mute_same_type"],
            [button["action"] for button in payload["buttons"]],
        )
        self.assertIn("确认提醒有用", rendered)
        self.assertIn("忽略本次", rendered)
        self.assertIn("延后", rendered)
        self.assertIn("关闭同类提醒", rendered)
        self.assertIn("req_reminder_card", rendered)

    def test_copilot_candidate_review_payload_redacts_permission_denied_output(self) -> None:
        service = CopilotService(repository=MemoryRepository(self.conn))
        created = handle_tool_request(
            "memory.create_candidate",
            {
                "text": "决定：生产部署 region 以后统一改成 ap-shanghai。",
                "scope": "project:feishu_ai_challenge",
                "source": {
                    "source_type": "unit_test",
                    "source_id": "msg_denied_card",
                    "actor_id": "ou_operator",
                    "created_at": "2026-05-07T10:00:00+08:00",
                    "quote": "决定：生产部署 region 以后统一改成 ap-shanghai。",
                },
                "current_context": copilot_context("memory.create_candidate"),
            },
            service=service,
        )
        self.assertTrue(created["ok"])

        denied = handle_tool_request(
            "memory.confirm",
            {
                "candidate_id": created["candidate_id"],
                "scope": "project:feishu_ai_challenge",
                "reason": "non-reviewer click",
                "current_context": copilot_context(
                    "memory.confirm",
                    roles=["member"],
                    request_id="req_denied_review_card",
                    trace_id="trace_denied_review_card",
                ),
            },
            service=service,
        )

        payload = candidate_review_payload(denied)
        card = build_candidate_review_card(denied)
        rendered = json.dumps(card, ensure_ascii=False)
        status = self.conn.execute("SELECT status FROM memories WHERE id = ?", (created["candidate_id"],)).fetchone()[
            "status"
        ]

        self.assertFalse(denied["ok"])
        self.assertEqual("candidate", status)
        self.assertEqual("permission_denied", payload["status"])
        self.assertEqual("req_denied_review_card", payload["request_id"])
        self.assertEqual("trace_denied_review_card", payload["trace_id"])
        self.assertEqual("deny", payload["permission_decision"]["decision"])
        self.assertEqual("review_role_required", payload["permission_decision"]["reason_code"])
        self.assertEqual([], payload["buttons"])
        self.assertNotIn("ap-shanghai", rendered)
        self.assertNotIn("决定：生产部署 region", rendered)
        self.assertNotIn("request_id", rendered)
        self.assertNotIn("trace_id", rendered)
        self.assertNotIn("req_denied_review_card", rendered)
        self.assertNotIn("trace_denied_review_card", rendered)

    def test_card_action_review_surface_uses_copilot_bridge_and_fails_closed(self) -> None:
        service = CopilotService(repository=MemoryRepository(self.conn))
        created = handle_tool_request(
            "memory.create_candidate",
            {
                "text": "决定：Phase 3 review surface 必须走 CopilotService。",
                "scope": "project:feishu_ai_challenge",
                "source": {
                    "source_type": "unit_test",
                    "source_id": "msg_review_action",
                    "actor_id": "ou_operator",
                    "created_at": "2026-05-07T10:00:00+08:00",
                    "quote": "决定：Phase 3 review surface 必须走 CopilotService。",
                },
                "current_context": copilot_context("memory.create_candidate"),
            },
            service=service,
        )
        self.assertTrue(created["ok"])

        event = message_event_from_payload(
            card_action_payload(
                "confirm",
                created["candidate_id"],
                extra_value={
                    "review_surface": "copilot_service",
                    "tool": "memory.confirm",
                    "scope": "project:feishu_ai_challenge",
                    "current_context": copilot_context(
                        "memory.confirm",
                        roles=["member"],
                        request_id="req_card_action_denied",
                        trace_id="trace_card_action_denied",
                    ),
                    "reason": "non-reviewer click",
                },
            )
        )
        self.assertIsNotNone(event)

        result = handle_message_event(
            self.conn, event, FakePublisher(self.config, [True]), self.config, db_path=self.db_path
        )
        status = self.conn.execute("SELECT status FROM memories WHERE id = ?", (created["candidate_id"],)).fetchone()[
            "status"
        ]
        rendered = json.dumps(result["publish"]["card"], ensure_ascii=False)

        self.assertEqual("confirm", result["command"])
        self.assertFalse(result["tool_result"]["ok"])
        self.assertEqual("permission_denied", result["tool_result"]["error"]["code"])
        self.assertEqual("review_role_required", result["tool_result"]["bridge"]["permission_decision"]["reason_code"])
        self.assertEqual("candidate", status)
        self.assertEqual("req_card_action_denied", result["tool_result"]["bridge"]["request_id"])
        self.assertEqual("trace_card_action_denied", result["tool_result"]["bridge"]["trace_id"])
        self.assertNotIn("req_card_action_denied", rendered)
        self.assertNotIn("trace_card_action_denied", rendered)
        self.assertNotIn("Phase 3 review surface 必须走 CopilotService", rendered)

    def test_card_action_without_permission_context_fails_closed(self) -> None:
        service = CopilotService(repository=MemoryRepository(self.conn))
        created = handle_tool_request(
            "memory.create_candidate",
            {
                "text": "决定：缺少权限上下文的卡片点击不能确认候选。",
                "scope": "project:feishu_ai_challenge",
                "source": {
                    "source_type": "unit_test",
                    "source_id": "msg_missing_context_action",
                    "actor_id": "ou_operator",
                    "created_at": "2026-05-07T10:00:00+08:00",
                    "quote": "决定：缺少权限上下文的卡片点击不能确认候选。",
                },
                "current_context": copilot_context("memory.create_candidate"),
            },
            service=service,
        )
        self.assertTrue(created["ok"])

        event = message_event_from_payload(
            card_action_payload(
                "confirm",
                created["candidate_id"],
                extra_value={
                    "review_surface": "copilot_service",
                    "tool": "memory.confirm",
                    "scope": "project:feishu_ai_challenge",
                    "reason": "missing permission context",
                },
            )
        )
        self.assertIsNotNone(event)

        result = handle_message_event(
            self.conn, event, FakePublisher(self.config, [True]), self.config, db_path=self.db_path
        )
        status = self.conn.execute("SELECT status FROM memories WHERE id = ?", (created["candidate_id"],)).fetchone()[
            "status"
        ]
        rendered = json.dumps(result["publish"]["card"], ensure_ascii=False)

        self.assertEqual("confirm", result["command"])
        self.assertFalse(result["tool_result"]["ok"])
        self.assertEqual("permission_denied", result["tool_result"]["error"]["code"])
        self.assertEqual(
            "missing_permission_context", result["tool_result"]["bridge"]["permission_decision"]["reason_code"]
        )
        self.assertEqual("candidate", status)
        self.assertNotIn("权限上下文的卡片点击不能确认候选", rendered)

    def test_copilot_version_chain_payload_explains_old_value(self) -> None:
        response = {
            "ok": True,
            "memory_id": "mem_1",
            "scope": "project:feishu_ai_challenge",
            "subject": "生产部署",
            "type": "workflow",
            "status": "active",
            "active_version": {"version_id": "ver_2", "version": 2, "value": "ap-shanghai", "status": "active"},
            "versions": [
                {
                    "version_id": "ver_1",
                    "version": 1,
                    "value": "cn-shanghai",
                    "status": "superseded",
                    "is_active": False,
                    "inactive_reason": "已被后续确认的新版本覆盖，默认 search 不再把它当当前答案。",
                    "evidence": {"quote": "旧值"},
                },
                {
                    "version_id": "ver_2",
                    "version": 2,
                    "value": "ap-shanghai",
                    "status": "active",
                    "is_active": True,
                    "evidence": {"quote": "新值"},
                },
            ],
            "supersedes": [{"version_id": "ver_2", "supersedes_version_id": "ver_1"}],
            "explanation": "当前有效值是 v2：ap-shanghai。",
            "user_explanation": {
                "kind": "memory_version_chain",
                "current_version": {
                    "version_id": "ver_2",
                    "version": 2,
                    "status": "active",
                    "value": "ap-shanghai",
                    "evidence": {"quote": "新值"},
                    "explanation": "当前采用 v2，因为它是已经确认的 active 版本。",
                },
                "old_versions": [
                    {
                        "version_id": "ver_1",
                        "version": 1,
                        "status": "superseded",
                        "value": "cn-shanghai",
                        "evidence": {"quote": "旧值"},
                        "covered_by": "v2",
                        "inactive_reason": "旧版本只保留在版本链里，不会进入默认搜索结果。",
                    }
                ],
                "override_reason": "当前采用 v2：ap-shanghai，因为新证据已经覆盖旧结论：cn-shanghai。",
                "evidence_summary": "当前版本证据：新值；旧版本证据：旧值。",
                "search_boundary": "默认搜索只返回当前 active 版本；旧版本不会作为当前答案返回。",
            },
        }

        payload = version_chain_payload(response)
        card = build_version_chain_card(response)
        rendered = json.dumps({"payload": payload, "card": card}, ensure_ascii=False)

        self.assertEqual("copilot_version_chain", payload["surface"])
        self.assertEqual("none", payload["state_mutation"])
        self.assertEqual("ver_2", payload["active_version"]["version_id"])
        self.assertEqual("memory_version_chain", payload["user_explanation"]["kind"])
        self.assertEqual("ap-shanghai", payload["user_content"]["current_version"]["value"])
        self.assertIn("覆盖旧结论", payload["user_content"]["override_reason"])
        self.assertIn("默认搜索只返回当前 active 版本", payload["user_content"]["search_boundary"])
        self.assertIn("为什么采用", rendered)
        self.assertIn("当前采用 v2：ap-shanghai", rendered)
        self.assertIn("superseded", rendered)

    def test_copilot_version_chain_payload_redacts_permission_denied_output(self) -> None:
        denied = {
            "ok": False,
            "error": {
                "code": "permission_denied",
                "message": "actor tenant cannot access requested memory scope",
                "retryable": False,
                "details": {
                    "reason_code": "tenant_mismatch",
                    "request_id": "req_versions_deny",
                    "trace_id": "trace_versions_deny",
                    "redacted_fields": ["current_value", "summary", "evidence"],
                    "current_value": "生产部署 region 用 cn-secret。",
                    "summary": "不应出现在卡片里",
                    "evidence": {"quote": "secret evidence quote"},
                },
            },
            "bridge": {
                "entrypoint": "openclaw_tool",
                "tool": "fmc_memory_explain_versions",
                "request_id": "req_versions_deny",
                "trace_id": "trace_versions_deny",
                "permission_decision": {
                    "decision": "deny",
                    "reason_code": "tenant_mismatch",
                    "requested_action": "fmc_memory_explain_versions",
                },
            },
        }

        payload = version_chain_payload(denied)
        card = build_version_chain_card(denied)
        rendered = json.dumps({"payload": payload, "card": card}, ensure_ascii=False)

        self.assertEqual("permission_denied", payload["status"])
        self.assertEqual("req_versions_deny", payload["request_id"])
        self.assertEqual("trace_versions_deny", payload["trace_id"])
        self.assertEqual("deny", payload["permission_decision"]["decision"])
        self.assertNotIn("current_value", rendered)
        self.assertNotIn("生产部署 region 用 cn-secret", rendered)
        self.assertNotIn("不应出现在卡片里", rendered)
        self.assertNotIn("secret evidence quote", rendered)

    def test_copilot_reminder_candidate_payload_is_dry_run(self) -> None:
        reminder = {
            "reminder_id": "rem_mem_1_deadline",
            "memory_id": "mem_1",
            "scope": "project:feishu_ai_challenge",
            "subject": "提交材料",
            "current_value": "提交材料截止时间是 2026-05-07。",
            "reason": "这条记忆像是截止时间或发布风险，任务前先提醒。",
            "trigger": "deadline",
            "status": "candidate",
            "due_at": "2026-05-07",
            "evidence": {"quote": "提交材料截止时间是 2026-05-07。"},
            "recommended_action": "review_reminder_candidate",
            "risk_flags": [],
            "target_actor": {"user_id": "ou_test", "roles": ["member", "reviewer"]},
            "cooldown": {"cooldown_ms": 86400000, "passed": True},
            "permission_trace": {
                "request_id": "req_heartbeat_review_due",
                "trace_id": "trace_heartbeat_review_due",
                "decision": "allow",
                "reason_code": "scope_access_granted",
            },
        }

        payload = reminder_candidate_payload(reminder)
        card = build_reminder_candidate_card(reminder)

        self.assertEqual("copilot_reminder_candidate", payload["surface"])
        self.assertEqual("none", payload["state_mutation"])
        self.assertEqual("deadline", payload["trigger"])
        self.assertEqual("ou_test", payload["target_actor"]["user_id"])
        self.assertEqual("req_heartbeat_review_due", payload["request_id"])
        self.assertEqual("trace_heartbeat_review_due", payload["trace_id"])
        self.assertIn("dry-run", card["elements"][1]["text"]["content"])

    def test_copilot_reminder_card_redacts_withheld_sensitive_payload(self) -> None:
        reminder = {
            "reminder_id": "rem_mem_secret_important_not_recalled",
            "memory_id": "mem_secret",
            "scope": "project:feishu_ai_challenge",
            "subject": "OpenAPI 调试风险",
            "current_value": "OpenAPI 调试风险：api_key=abcdefghi123456789 只能放本地环境。",
            "reason": "敏感提醒已隐藏，需 reviewer 复核。",
            "trigger": "important_not_recalled",
            "status": "withheld",
            "evidence": {"quote": "OpenAPI 调试风险：api_key=abcdefghi123456789 只能放本地环境。"},
            "recommended_action": "permission_denied",
            "risk_flags": ["sensitive_content"],
            "target_actor": {"user_id": "ou_member", "roles": ["member"]},
            "cooldown": {"cooldown_ms": 86400000, "passed": True},
            "permission_trace": {
                "request_id": "req_sensitive_reminder",
                "trace_id": "trace_sensitive_reminder",
                "decision": "redact",
                "reason_code": "sensitive_content_redacted",
            },
        }

        payload = reminder_candidate_payload(reminder)
        card = build_reminder_candidate_card(reminder)
        rendered = json.dumps(card, ensure_ascii=False)

        self.assertEqual("withheld", payload["status"])
        self.assertEqual("", payload["current_value"])
        self.assertEqual({}, payload["evidence"])
        self.assertEqual("redact", payload["permission_decision"]["decision"])
        self.assertEqual("req_sensitive_reminder", payload["request_id"])
        self.assertNotIn("api_key", rendered)
        self.assertNotIn("abcdefghi123456789", rendered)


if __name__ == "__main__":
    unittest.main()
