from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memory_engine.db import connect, init_db
from memory_engine.feishu_config import FeishuConfig
from memory_engine.feishu_events import message_event_from_payload
from memory_engine.feishu_publisher import DryRunPublisher
from memory_engine.feishu_runtime import handle_message_event

CHAT_ID = "oc_day5"
FIXTURE = "tests/fixtures/day5_doc_ingestion_fixture.md"


def payload(message_id: str, text: str) -> dict:
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou_day5"},
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


class FeishuDay5Test(unittest.TestCase):
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

    def test_ingest_doc_confirm_and_recall_show_document_source(self) -> None:
        ingest = self.handle(f"/ingest_doc {FIXTURE}", "om_d5_ingest")
        reply = ingest["publish"]["text"]
        self.assertIn("类型：文档 ingestion", reply)
        self.assertIn("状态：candidate", reply)
        self.assertIn("候选数量：", reply)

        row = self.conn.execute(
            """
            SELECT id
            FROM memories
            WHERE status = 'candidate'
              AND current_value LIKE '%生产部署必须加%'
            LIMIT 1
            """
        ).fetchone()
        self.assertIsNotNone(row)

        confirm = self.handle(f"/confirm {row['id']}", "om_d5_confirm")
        self.assertIn("状态：active", confirm["publish"]["text"])

        recall = self.handle("/recall 生产部署参数", "om_d5_recall")
        recall_text = recall["publish"]["text"]
        self.assertIn("文档《Day5 架构决策文档》", recall_text)
        self.assertIn("证据：决定：生产部署必须加 --canary --region cn-shanghai。", recall_text)


if __name__ == "__main__":
    unittest.main()
