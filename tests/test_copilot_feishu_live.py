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

    def test_natural_task_request_routes_to_prefetch(self) -> None:
        event = message_event_from_payload(payload("om_live_prefetch", "请准备今天上线前 checklist"))
        self.assertIsNotNone(event)
        invocation = invocation_from_event(event, scope=SCOPE)

        self.assertEqual("memory.prefetch", invocation.tool_name)
        self.assertEqual("natural_prefetch", invocation.reason)
        self.assertEqual(SCOPE, invocation.payload["scope"])

    def test_real_feishu_actor_permission_uses_configured_tenant_org_maps(self) -> None:
        event = message_event_from_payload(payload("om_live_real_permission", "生产部署 region 是什么？"))
        self.assertIsNotNone(event)

        with patch.dict(
            os.environ,
            {
                "COPILOT_FEISHU_ACTOR_TENANT_MAP": "ou_live_user=tenant:feishu-real",
                "COPILOT_FEISHU_ACTOR_ORGANIZATION_MAP": "ou_live_user=org:feishu-real",
                "COPILOT_FEISHU_REVIEWER_OPEN_IDS": "",
            },
            clear=False,
        ):
            invocation = invocation_from_event(event, scope=SCOPE)

        permission = invocation.payload["current_context"]["permission"]
        self.assertEqual("tenant:feishu-real", permission["actor"]["tenant_id"])
        self.assertEqual("org:feishu-real", permission["actor"]["organization_id"])
        self.assertEqual(CHAT_ID, permission["source_context"]["chat_id"])
        self.assertEqual(["member"], permission["actor"]["roles"])

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
