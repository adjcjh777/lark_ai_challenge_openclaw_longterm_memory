from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memory_engine.db import connect, init_db
from memory_engine.feishu_cards import build_decision_card, build_update_card
from memory_engine.feishu_config import FeishuConfig
from memory_engine.feishu_events import message_event_from_payload
from memory_engine.feishu_publisher import DryRunPublisher
from memory_engine.feishu_runtime import handle_message_event


CHAT_ID = "oc_day6"


def payload(message_id: str, text: str) -> dict:
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou_day6"},
                "sender_type": "user",
            },
            "message": {
                "message_id": message_id,
                "chat_id": CHAT_ID,
                "chat_type": "group",
                "message_type": "text",
                "content": f'{{"text":"{text}"}}',
                "create_time": "1777000000000",
            },
        },
    }


class FeishuDay6Test(unittest.TestCase):
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

    def handle(self, text: str, message_id: str) -> dict:
        event = message_event_from_payload(payload(message_id, text))
        self.assertIsNotNone(event)
        return handle_message_event(
            self.conn,
            event,
            DryRunPublisher(),
            self.config,
            db_path=self.db_path,
            dry_run=True,
        )

    def test_recall_reply_has_decision_card_fields_and_redaction(self) -> None:
        self.handle("/remember 生产部署必须加 --canary，API_TOKEN=feishu_abcdefghijklmnopqrstuvwxyz", "om_d6_secret")

        recall = self.handle("/recall 生产部署参数", "om_d6_recall")
        reply = recall["publish"]["text"]

        self.assertIn("卡片：历史决策卡片", reply)
        self.assertIn("结论：", reply)
        self.assertIn("理由：", reply)
        self.assertIn("状态：active", reply)
        self.assertIn("版本：v1", reply)
        self.assertIn("来源：", reply)
        self.assertIn("是否被覆盖：否", reply)
        self.assertIn("API_TOKEN=[REDACTED]", reply)
        self.assertNotIn("feishu_abcdefghijklmnopqrstuvwxyz", reply)

    def test_override_reply_shows_old_to_new_rule(self) -> None:
        self.handle("/remember 生产部署必须加 --canary --region cn-shanghai", "om_d6_initial")
        update = self.handle("/remember 不对，生产部署 region 改成 ap-shanghai", "om_d6_update")
        reply = update["publish"]["text"]

        self.assertIn("卡片：矛盾更新卡片", reply)
        self.assertIn("旧规则 -> 新规则：", reply)
        self.assertIn("生产部署必须加 --canary --region cn-shanghai", reply)
        self.assertIn("不对，生产部署 region 改成 ap-shanghai", reply)
        self.assertIn("旧版本状态：superseded", reply)

    def test_unknown_command_lists_command_whitelist(self) -> None:
        result = self.handle("/deploy now", "om_d6_unknown")
        reply = result["publish"]["text"]

        self.assertIn("状态：unknown_command", reply)
        self.assertIn("命令白名单：", reply)
        self.assertIn("/remember", reply)
        self.assertIn("/recall", reply)

    def test_card_json_builders_keep_required_fields(self) -> None:
        decision_card = build_decision_card(
            title="历史决策卡片",
            conclusion="生产部署必须加 --canary",
            reason="来自项目规则",
            status="active",
            version="v2",
            source="文档《架构决策》/ docx...abcd",
            overwritten="否",
            memory_id="mem_demo",
        )
        update_card = build_update_card(
            title="矛盾更新卡片",
            old_rule="生产部署 region 使用 cn-shanghai",
            new_rule="生产部署 region 改成 ap-shanghai",
            reason="显式覆盖",
            version="v2",
            source="当前飞书消息",
            memory_id="mem_demo",
        )

        decision_text = str(decision_card)
        update_text = str(update_card)
        for required in ("结论", "理由", "状态", "版本", "来源", "是否被覆盖"):
            self.assertIn(required, decision_text)
        self.assertIn("旧规则 -> 新规则", update_text)


if __name__ == "__main__":
    unittest.main()
