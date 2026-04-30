from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_engine.db import connect, init_db
from scripts.openclaw_feishu_remember_router import build_remember_payload, route_gateway_message, route_remember_message

SCOPE = "project:feishu_ai_challenge"
CHAT_ID = "oc_openclaw_remember_router_test"
SENDER_OPEN_ID = "ou_openclaw_remember_sender"


class OpenClawFeishuRememberRouterTest(unittest.TestCase):
    def test_build_remember_payload_uses_repo_contract(self) -> None:
        payload = build_remember_payload(
            text="决定：OpenClaw /remember 必须进入 repo candidate pipeline。",
            message_id="om_router_001",
            chat_id=CHAT_ID,
            sender_open_id=SENDER_OPEN_ID,
        )

        self.assertEqual(SCOPE, payload["scope"])
        self.assertEqual("feishu_message", payload["source"]["source_type"])
        self.assertEqual("om_router_001", payload["source"]["source_id"])
        self.assertEqual(CHAT_ID, payload["source"]["source_chat_id"])
        permission = payload["current_context"]["permission"]
        self.assertEqual("tenant:demo", permission["actor"]["tenant_id"])
        self.assertEqual("org:demo", permission["actor"]["organization_id"])
        self.assertEqual(["member"], permission["actor"]["roles"])
        self.assertEqual("fmc_memory_create_candidate", permission["requested_action"])
        self.assertEqual("team", permission["requested_visibility"])
        self.assertEqual("feishu_chat", permission["source_context"]["entrypoint"])
        self.assertEqual(SCOPE, permission["source_context"]["workspace_id"])
        self.assertEqual(CHAT_ID, permission["source_context"]["chat_id"])

    def test_route_remember_message_returns_candidate_review_card(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            result = route_remember_message(
                text="/remember 决定：OpenClaw /remember 应直接返回 interactive candidate card。",
                message_id="om_router_002",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                db_path=str(db_path),
            )

        self.assertTrue(result["ok"])
        self.assertEqual("fmc_memory_create_candidate", result["tool_result"]["bridge"]["tool"])
        self.assertEqual("candidate", result["tool_result"]["candidate"]["status"])
        card = result["card"]
        action_blocks = [element for element in card["elements"] if element.get("tag") == "action"]
        self.assertEqual(1, len(action_blocks))
        labels = [action["text"]["content"] for action in action_blocks[0]["actions"]]
        self.assertIn("确认保存", labels)
        self.assertIn("拒绝候选", labels)

    def test_gateway_explicit_remember_keeps_interactive_card_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            result = route_gateway_message(
                text="/remember 决定：OpenClaw gateway 显式记忆仍返回审核卡片。",
                message_id="om_router_explicit",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=False,
                allowlist_chat_ids=[],
                db_path=str(db_path),
            )

        self.assertTrue(result["ok"])
        self.assertEqual("fmc_memory_create_candidate", result["tool_result"]["bridge"]["tool"])
        self.assertIsNotNone(result["card"])
        action_blocks = [element for element in result["card"]["elements"] if element.get("tag") == "action"]
        self.assertEqual(1, len(action_blocks))

    def test_gateway_unmentioned_allowlist_group_message_creates_silent_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "memory.sqlite"
            conn = connect(db_path)
            init_db(conn)
            conn.close()

            result = route_gateway_message(
                text="决定：OpenClaw gateway live 静默候选入口必须走 CopilotService，负责人是程俊豪，截止周五。",
                message_id="om_router_silent_candidate",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=False,
                allowlist_chat_ids=[CHAT_ID],
                db_path=str(db_path),
            )

        self.assertTrue(result["ok"])
        self.assertEqual("memory.create_candidate", result["tool"])
        self.assertEqual("passive_candidate_probe", result["routing_reason"])
        self.assertIsNone(result["card"])
        self.assertEqual("silent_no_reply", result["disposition"])
        self.assertEqual("silent_no_reply", result["publish"]["mode"])
        self.assertTrue(result["publish"]["suppressed"])
        self.assertEqual("silent_candidate_probe", result["message_disposition"]["memory_path"])
        self.assertEqual("passive_group_detection", result["message_disposition"]["reason_code"])
        self.assertEqual("candidate", result["tool_result"]["candidate"]["status"])
        bridge = result["tool_result"]["bridge"]
        self.assertEqual("fmc_memory_create_candidate", bridge["tool"])
        self.assertEqual("allow", bridge["permission_decision"]["decision"])
        self.assertEqual("scope_access_granted", bridge["permission_decision"]["reason_code"])
        self.assertEqual("openclaw_gateway_live", bridge["permission_decision"]["source_entrypoint"])

    def test_gateway_unmentioned_plain_question_is_ignored_without_tool_call(self) -> None:
        with patch("scripts.openclaw_feishu_remember_router.handle_tool_request") as handle:
            result = route_gateway_message(
                text="生产部署 region 是什么？",
                message_id="om_router_plain_question",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=False,
                allowlist_chat_ids=[CHAT_ID],
            )

        handle.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertTrue(result["ignored"])
        self.assertIsNone(result["card"])
        self.assertEqual("silent_no_reply", result["disposition"])
        self.assertEqual("silent_no_reply", result["publish"]["mode"])
        self.assertEqual("low_memory_signal", result["message_disposition"]["reason_code"])

    def test_gateway_unmentioned_low_signal_message_is_ignored_without_tool_call(self) -> None:
        with patch("scripts.openclaw_feishu_remember_router.handle_tool_request") as handle:
            result = route_gateway_message(
                text="大家下午三点喝咖啡。",
                message_id="om_router_low_signal",
                chat_id=CHAT_ID,
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=False,
                allowlist_chat_ids=[CHAT_ID],
            )

        handle.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertTrue(result["ignored"])
        self.assertIsNone(result["card"])
        self.assertEqual("silent_no_reply", result["publish"]["mode"])
        self.assertEqual("low_memory_signal", result["message_disposition"]["reason_code"])

    def test_gateway_non_allowlist_group_message_is_ignored_without_tool_call(self) -> None:
        with patch("scripts.openclaw_feishu_remember_router.handle_tool_request") as handle:
            result = route_gateway_message(
                text="决定：这个群不在 allowlist，不应该进入候选。",
                message_id="om_router_not_allowlisted",
                chat_id="oc_not_allowlisted",
                sender_open_id=SENDER_OPEN_ID,
                chat_type="group",
                bot_mentioned=False,
                allowlist_chat_ids=[CHAT_ID],
            )

        handle.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertTrue(result["ignored"])
        self.assertIsNone(result["card"])
        self.assertEqual("chat_not_allowlisted", result["message_disposition"]["reason_code"])


if __name__ == "__main__":
    unittest.main()
