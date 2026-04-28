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
    build_reminder_candidate_card,
    build_version_chain_card,
    candidate_review_payload,
    reminder_candidate_payload,
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
        self.assertIn("send_card", publisher.modes)
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
                "type": "workflow",
                "subject": "生产部署",
                "current_value": "不对，生产部署 region 改成 ap-shanghai。",
                "summary": "覆盖旧 region",
            },
        }

        payload = candidate_review_payload(response)
        card = build_candidate_review_card(response)

        self.assertEqual("copilot_candidate_review", payload["surface"])
        self.assertEqual("none", payload["state_mutation"])
        self.assertTrue(payload["conflict"]["has_conflict"])
        self.assertIn("确认保存", [action["label"] for action in payload["buttons"]])
        self.assertEqual("orange", card["header"]["template"])

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
        rendered = json.dumps({"payload": payload, "card": card}, ensure_ascii=False)
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
        self.assertIn("req_card_action_denied", rendered)
        self.assertIn("trace_card_action_denied", rendered)
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
        }

        payload = version_chain_payload(response)
        card = build_version_chain_card(response)

        self.assertEqual("copilot_version_chain", payload["surface"])
        self.assertEqual("none", payload["state_mutation"])
        self.assertEqual("ver_2", payload["active_version"]["version_id"])
        self.assertIn("superseded", card["elements"][1]["text"]["content"])

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
                },
            },
            "bridge": {
                "entrypoint": "openclaw_tool",
                "tool": "memory.explain_versions",
                "request_id": "req_versions_deny",
                "trace_id": "trace_versions_deny",
                "permission_decision": {
                    "decision": "deny",
                    "reason_code": "tenant_mismatch",
                    "requested_action": "memory.explain_versions",
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
        self.assertNotIn("evidence quote", rendered)

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
