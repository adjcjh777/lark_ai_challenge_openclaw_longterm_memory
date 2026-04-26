from __future__ import annotations

import unittest
from pathlib import Path

from memory_engine.db import connect, init_db
from memory_engine.feishu_config import FeishuConfig
from memory_engine.feishu_events import message_event_from_payload
from memory_engine.feishu_publisher import DryRunPublisher
from memory_engine.feishu_runtime import handle_message_event
from temp_utils import WorkspaceTempDir


CHAT_ID = "oc_test"


def payload(
    message_id: str,
    text: str,
    *,
    message_type: str = "text",
    sender_type: str = "user",
) -> dict:
    content = f'{{"text":"{text}"}}' if message_type == "text" else "{}"
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou_test"},
                "sender_type": sender_type,
            },
            "message": {
                "message_id": message_id,
                "chat_id": CHAT_ID,
                "chat_type": "group",
                "message_type": message_type,
                "content": content,
                "create_time": "1777000000000",
            },
        },
    }


class FeishuDay3Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = WorkspaceTempDir("feishu_day3")
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

    def handle(self, raw: dict) -> dict:
        event = message_event_from_payload(raw)
        self.assertIsNotNone(event)
        return handle_message_event(
            self.conn,
            event,
            DryRunPublisher(),
            self.config,
            db_path=self.db_path,
            dry_run=True,
        )

    def reply_text(self, result: dict) -> str:
        return result["publish"]["text"]

    def test_demo_commands_use_stable_reply_fields(self) -> None:
        remember = self.handle(payload("om_d3_remember", "/remember 生产部署必须加 --canary --region cn-shanghai"))
        self.assertIn("类型：已记住", self.reply_text(remember))
        self.assertIn("主题：生产部署", self.reply_text(remember))
        self.assertIn("状态：active", self.reply_text(remember))
        self.assertIn("版本：v1", self.reply_text(remember))
        self.assertIn("来源：当前飞书消息", self.reply_text(remember))

        recall = self.handle(payload("om_d3_recall", "/recall 生产部署参数"))
        self.assertIn("类型：记忆召回", self.reply_text(recall))
        self.assertIn("当前有效规则：生产部署必须加 --canary --region cn-shanghai", self.reply_text(recall))

        update = self.handle(payload("om_d3_update", "/remember 不对，生产部署 region 改成 ap-shanghai"))
        self.assertIn("类型：记忆更新", self.reply_text(update))
        self.assertIn("版本：v2", self.reply_text(update))

        memory_id = self.conn.execute("SELECT id FROM memories WHERE subject = ?", ("生产部署",)).fetchone()["id"]
        versions = self.handle(payload("om_d3_versions", f"/versions {memory_id}"))
        self.assertIn("类型：版本链", self.reply_text(versions))
        self.assertIn("版本数量：2", self.reply_text(versions))
        self.assertIn("v1 [superseded]", self.reply_text(versions))
        self.assertIn("v2 [active]", self.reply_text(versions))

    def test_help_and_health(self) -> None:
        help_result = self.handle(payload("om_d3_help", "/help"))
        self.assertIn("类型：命令帮助", self.reply_text(help_result))
        self.assertIn("/remember <内容>", self.reply_text(help_result))
        self.assertIn("Demo 推荐输入", self.reply_text(help_result))

        health = self.handle(payload("om_d3_health", "/health"))
        self.assertIn("类型：健康检查", self.reply_text(health))
        self.assertIn(f"数据库：{self.db_path}", self.reply_text(health))
        self.assertIn("默认 scope：project:feishu_ai_challenge", self.reply_text(health))
        self.assertIn("dry-run：true", self.reply_text(health))

    def test_edge_cases_are_explicit(self) -> None:
        unknown = self.handle(payload("om_d3_unknown", "/wat 生产部署"))
        self.assertIn("状态：unknown_command", self.reply_text(unknown))

        empty = self.handle(payload("om_d3_empty", "   "))
        self.assertIn("状态：ignored", self.reply_text(empty))
        self.assertIn("收到空消息", self.reply_text(empty))

        non_text = self.handle(payload("om_d3_image", "", message_type="image"))
        self.assertIn("状态：ignored", self.reply_text(non_text))
        self.assertIn("只支持文本消息", self.reply_text(non_text))

        bot_event = message_event_from_payload(payload("om_d3_bot", "/help", sender_type="bot"))
        self.assertIsNotNone(bot_event)
        bot_result = handle_message_event(self.conn, bot_event, DryRunPublisher(), self.config)
        self.assertTrue(bot_result["ignored"])
        self.assertEqual("bot self message", bot_result["reason"])
        self.assertNotIn("publish", bot_result)

        first = self.handle(payload("om_d3_duplicate", "/help"))
        self.assertTrue(first["ok"])
        duplicate = self.handle(payload("om_d3_duplicate", "/help"))
        self.assertTrue(duplicate["duplicate"])
        self.assertIn("状态：duplicate", self.reply_text(duplicate))


if __name__ == "__main__":
    unittest.main()
