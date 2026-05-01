from __future__ import annotations

import tempfile
import unittest

from memory_engine.copilot.knowledge_pages import compile_project_memory_cards
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository

SCOPE = "project:feishu_ai_challenge"


class CopilotKnowledgePagesTest(unittest.TestCase):
    def test_compiles_active_memories_with_evidence_and_version_context(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_knowledge_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(SCOPE, "生产部署必须加 --canary --region cn-shanghai。", source_type="unit_test")
            updated = repo.remember(SCOPE, "不对，生产部署 region 改成 ap-shanghai。", source_type="unit_test")
            repo.remember(SCOPE, "Benchmark 报告必须展示 Recall@3。", source_type="unit_test")

            result = compile_project_memory_cards(repo, scope=SCOPE)
            conn.close()

        self.assertTrue(result["ok"])
        self.assertEqual(2, result["card_count"])
        self.assertFalse(result["generation_policy"]["raw_events_included"])
        self.assertFalse(result["generation_policy"]["writes_feishu"])
        markdown = result["markdown"]
        self.assertIn("# 项目记忆卡册：project:feishu_ai_challenge", markdown)
        self.assertIn("ap-shanghai", markdown)
        self.assertIn("Recall@3", markdown)
        self.assertIn("历史覆盖：1 个旧版本已 superseded", markdown)
        self.assertIn(updated["memory_id"], [card["memory_id"] for card in result["cards"]])


if __name__ == "__main__":
    unittest.main()
