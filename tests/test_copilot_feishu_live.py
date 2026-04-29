from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_engine.copilot.feishu_live import handle_copilot_message_event, invocation_from_event
from memory_engine.db import connect, init_db
from memory_engine.feishu_config import FeishuConfig
from memory_engine.feishu_events import message_event_from_payload
from memory_engine.feishu_publisher import DryRunPublisher
from memory_engine.repository import MemoryRepository

CHAT_ID = "oc_copilot_live_test"
SCOPE = "project:feishu_ai_challenge"


def payload(message_id: str, text: str, *, sender_type: str = "user") -> dict:
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou_live_user"},
                "sender_type": sender_type,
            },
            "message": {
                "message_id": message_id,
                "chat_id": CHAT_ID,
                "chat_type": "group",
                "message_type": "text",
                "content": f'{{"text":"{text}"}}',
                "create_time": "1777351200000",
            },
        },
    }


class CopilotFeishuLiveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "memory.sqlite"
        self.conn = connect(self.db_path)
        init_db(self.conn)
        self.config = FeishuConfig(
            bot_mode="reply",
            default_scope=SCOPE,
            lark_cli="lark-cli",
            lark_profile="feishu-ai-challenge",
            lark_as="bot",
            reply_in_thread=False,
            card_mode="text",
        )

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    def handle(self, message_id: str, text: str) -> dict:
        event = message_event_from_payload(payload(message_id, text))
        self.assertIsNotNone(event)
        with patch.dict(os.environ, {"COPILOT_FEISHU_REVIEWER_OPEN_IDS": "*"}, clear=False):
            return handle_copilot_message_event(
                self.conn,
                event,
                DryRunPublisher(),
                self.config,
                dry_run=True,
            )

    def reply_text(self, result: dict) -> str:
        return result["publish"]["text"]

    def test_remember_routes_to_copilot_candidate_not_old_active_memory(self) -> None:
        result = self.handle("om_live_candidate", "/remember 决定：生产部署必须加 --canary --region cn-shanghai")

        self.assertTrue(result["ok"])
        self.assertEqual("memory.create_candidate", result["tool"])
        self.assertEqual("candidate", result["tool_result"]["candidate"]["status"])
        self.assertIn("不会自动成为 active memory", self.reply_text(result))
        self.assertIsNone(MemoryRepository(self.conn).recall(SCOPE, "生产部署参数"))

    def test_confirm_then_search_uses_copilot_tool_bridge(self) -> None:
        created = self.handle("om_live_create", "/remember 决定：生产部署必须加 --canary --region cn-shanghai")
        candidate_id = created["tool_result"]["candidate_id"]

        confirmed = self.handle("om_live_confirm", f"/confirm {candidate_id}")
        self.assertTrue(confirmed["ok"])
        self.assertEqual("memory.confirm", confirmed["tool"])
        self.assertIn("Memory Copilot 已确认候选记忆", self.reply_text(confirmed))

        search = self.handle("om_live_search", "生产部署 region 是什么？")
        self.assertTrue(search["ok"])
        self.assertEqual("memory.search", search["tool"])
        self.assertIn("只返回 active 当前结论", self.reply_text(search))
        self.assertIn("--canary", self.reply_text(search))
        self.assertIn("request_id", search["tool_result"]["bridge"])

    def test_natural_confirm_resolves_recent_candidate_without_internal_id(self) -> None:
        created = self.handle("om_live_create_natural_confirm", "记住：生产部署必须加 --canary，region 用 ap-shanghai。")
        self.assertEqual("memory.create_candidate", created["tool"])
        self.assertIn("你可以直接回复：确认这条", self.reply_text(created))

        confirmed = self.handle("om_live_confirm_natural", "确认这条")

        self.assertTrue(confirmed["ok"])
        self.assertEqual("memory.confirm", confirmed["tool"])
        self.assertEqual("natural_confirm_recent_candidate", confirmed["routing_reason"])
        self.assertEqual(created["tool_result"]["candidate_id"], confirmed["tool_result"]["candidate_id"])
        self.assertIn("下一步：这条记忆已经成为当前有效结论", self.reply_text(confirmed))

    def test_natural_reject_resolves_recent_candidate_without_internal_id(self) -> None:
        created = self.handle("om_live_create_natural_reject", "记住：生产部署 rollback 负责人是程俊豪，截止周五，必须提前录屏。")

        rejected = self.handle("om_live_reject_natural", "不要记这个")

        self.assertTrue(rejected["ok"])
        self.assertEqual("memory.reject", rejected["tool"])
        self.assertEqual("natural_reject_recent_candidate", rejected["routing_reason"])
        self.assertEqual(created["tool_result"]["candidate_id"], rejected["tool_result"]["candidate_id"])
        self.assertIn("不会成为当前有效记忆", self.reply_text(rejected))

    def test_natural_version_question_resolves_recent_memory_without_internal_id(self) -> None:
        self.handle("om_live_seed_old_region", "/remember 决定：生产部署 region 固定 cn-shanghai。")
        self.handle("om_live_confirm_old_region", "确认这条")
        updated = self.handle("om_live_update_region", "不对，生产部署 region 以后统一改成 ap-shanghai。")
        self.assertEqual("memory.create_candidate", updated["tool"])
        self.handle("om_live_confirm_updated_region", "确认这条")

        explained = self.handle("om_live_explain_natural", "为什么旧值不用了？")

        self.assertTrue(explained["ok"])
        self.assertEqual("memory.explain_versions", explained["tool"])
        self.assertEqual("natural_versions_recent_memory", explained["routing_reason"])
        self.assertEqual(updated["tool_result"]["memory_id"], explained["tool_result"]["memory_id"])
        reply = self.reply_text(explained)
        self.assertIn("当前结论", reply)
        self.assertIn("ap-shanghai", reply)
        self.assertIn("旧版本", reply)

    def test_search_reply_puts_audit_metadata_after_user_answer(self) -> None:
        self.handle("om_live_create_audit_order", "/remember 决定：生产部署必须加 --canary --region cn-shanghai")
        self.handle("om_live_confirm_audit_order", "确认这条")

        search = self.handle("om_live_search_audit_order", "生产部署 region 是什么？")
        reply = self.reply_text(search)

        self.assertLess(reply.index("结论："), reply.index("审计详情"))
        self.assertLess(reply.index("下一步："), reply.index("审计详情"))
        self.assertGreater(reply.index("request_id"), reply.index("审计详情"))

    def test_natural_task_request_routes_to_prefetch(self) -> None:
        event = message_event_from_payload(payload("om_live_prefetch", "请准备今天上线前 checklist"))
        self.assertIsNotNone(event)
        invocation = invocation_from_event(event, scope=SCOPE)

        self.assertEqual("memory.prefetch", invocation.tool_name)
        self.assertEqual("natural_prefetch", invocation.reason)
        self.assertEqual(SCOPE, invocation.payload["scope"])

    def test_task_command_places_task_id_in_permission_source_context(self) -> None:
        event = message_event_from_payload(payload("om_live_task_fetch", "/task task_123"))
        self.assertIsNotNone(event)
        invocation = invocation_from_event(event, scope=SCOPE)

        permission = invocation.payload["current_context"]["permission"]
        self.assertEqual("feishu.fetch_task", invocation.tool_name)
        self.assertNotIn("source_context", invocation.payload["current_context"])
        self.assertEqual("memory.create_candidate", permission["requested_action"])
        self.assertEqual("task_123", permission["source_context"]["task_id"])
        self.assertEqual(CHAT_ID, permission["source_context"]["chat_id"])

    def test_meeting_command_places_meeting_id_in_permission_source_context(self) -> None:
        event = message_event_from_payload(payload("om_live_meeting_fetch", "/meeting minute_123"))
        self.assertIsNotNone(event)
        invocation = invocation_from_event(event, scope=SCOPE)

        permission = invocation.payload["current_context"]["permission"]
        self.assertEqual("feishu.fetch_meeting", invocation.tool_name)
        self.assertNotIn("source_context", invocation.payload["current_context"])
        self.assertEqual("memory.create_candidate", permission["requested_action"])
        self.assertEqual("minute_123", permission["source_context"]["meeting_id"])

    def test_bitable_command_places_record_id_in_permission_source_context(self) -> None:
        event = message_event_from_payload(payload("om_live_bitable_fetch", "/bitable app_1 tbl_1 rec_1"))
        self.assertIsNotNone(event)
        invocation = invocation_from_event(event, scope=SCOPE)

        permission = invocation.payload["current_context"]["permission"]
        source_context = permission["source_context"]
        self.assertEqual("feishu.fetch_bitable", invocation.tool_name)
        self.assertNotIn("source_context", invocation.payload["current_context"])
        self.assertEqual("memory.create_candidate", permission["requested_action"])
        self.assertEqual("app_1", source_context["bitable_app_token"])
        self.assertEqual("tbl_1", source_context["bitable_table_id"])
        self.assertEqual("rec_1", source_context["bitable_record_id"])

    def test_permission_context_maps_real_feishu_tenant_org_and_chat(self) -> None:
        event = message_event_from_payload(payload("om_live_real_perm", "生产部署 region 是什么？"))
        self.assertIsNotNone(event)

        with patch.dict(
            os.environ,
            {
                "COPILOT_FEISHU_TENANT_ID": "tenant:feishu-prod",
                "COPILOT_FEISHU_ORGANIZATION_ID": "org:feishu-ai",
                "COPILOT_FEISHU_VISIBILITY": "organization",
            },
            clear=False,
        ):
            invocation = invocation_from_event(event, scope=SCOPE)

        context = invocation.payload["current_context"]
        permission = context["permission"]
        self.assertEqual("tenant:feishu-prod", context["tenant_id"])
        self.assertEqual("org:feishu-ai", context["organization_id"])
        self.assertEqual(CHAT_ID, context["chat_id"])
        self.assertEqual("tenant:feishu-prod", permission["actor"]["tenant_id"])
        self.assertEqual("org:feishu-ai", permission["actor"]["organization_id"])
        self.assertEqual(CHAT_ID, permission["source_context"]["chat_id"])
        self.assertEqual("organization", permission["requested_visibility"])

    def test_chat_allowlist_ignores_non_sandbox_chat_without_reply(self) -> None:
        event = message_event_from_payload(payload("om_live_wrong_chat", "/health"))
        self.assertIsNotNone(event)

        with patch.dict(os.environ, {"COPILOT_FEISHU_ALLOWED_CHAT_IDS": "oc_other_chat"}, clear=False):
            result = handle_copilot_message_event(self.conn, event, DryRunPublisher(), self.config, dry_run=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["ignored"])
        self.assertEqual("chat not in COPILOT_FEISHU_ALLOWED_CHAT_IDS", result["reason"])
        self.assertNotIn("publish", result)

    def test_health_redacts_live_ids(self) -> None:
        with patch.dict(
            os.environ,
            {
                "COPILOT_FEISHU_ALLOWED_CHAT_IDS": CHAT_ID,
                "COPILOT_FEISHU_REVIEWER_OPEN_IDS": "ou_sensitive_reviewer",
            },
            clear=False,
        ):
            result = handle_copilot_message_event(
                self.conn,
                message_event_from_payload(payload("om_live_health", "/health")),
                DryRunPublisher(),
                self.config,
                dry_run=True,
            )

        reply = self.reply_text(result)
        self.assertIn("群聊 allowlist：configured (1)", reply)
        self.assertIn("reviewer 配置：configured (1)", reply)
        self.assertNotIn(CHAT_ID, reply)
        self.assertNotIn("ou_sensitive_reviewer", reply)

    def test_missing_reviewer_role_denies_confirm(self) -> None:
        created = self.handle("om_live_create_member", "/remember 决定：OpenClaw 固定 2026.4.24")
        candidate_id = created["tool_result"]["candidate_id"]
        event = message_event_from_payload(payload("om_live_denied", f"/confirm {candidate_id}"))
        self.assertIsNotNone(event)

        with patch.dict(os.environ, {"COPILOT_FEISHU_REVIEWER_OPEN_IDS": ""}, clear=False):
            denied = handle_copilot_message_event(self.conn, event, DryRunPublisher(), self.config, dry_run=True)

        self.assertFalse(denied["tool_result"]["ok"])
        self.assertEqual("permission_denied", denied["tool_result"]["error"]["code"])
        self.assertIn("安全拒绝", self.reply_text(denied))


if __name__ == "__main__":
    unittest.main()
