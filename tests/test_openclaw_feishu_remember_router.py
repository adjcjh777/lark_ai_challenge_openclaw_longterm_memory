from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memory_engine.db import connect, init_db
from scripts.openclaw_feishu_remember_router import build_remember_payload, route_remember_message

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


if __name__ == "__main__":
    unittest.main()
