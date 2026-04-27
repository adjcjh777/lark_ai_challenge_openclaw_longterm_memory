from __future__ import annotations

import tempfile
import unittest

from memory_engine.copilot.service import CopilotService
from memory_engine.copilot.schemas import SearchRequest
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository


class CopilotRetrievalTest(unittest.TestCase):
    def test_search_trace_shows_l0_l1_and_l2_when_warm_fallback_is_needed(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_retrieval_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(
                "project:feishu_ai_challenge",
                "评测报告周日 20:00 前完成，负责人是程俊豪。",
                source_type="unit_test",
            )

            response = CopilotService(repository=repo).search(
                SearchRequest.from_payload(
                    {
                        "query": "谁负责评测报告",
                        "scope": "project:feishu_ai_challenge",
                        "current_context": {
                            "session_id": "sess_1",
                            "chat_id": "chat_1",
                            "task_id": "task_1",
                            "scope": "project:feishu_ai_challenge",
                        },
                    }
                )
            )
            conn.close()

        self.assertTrue(response["ok"])
        self.assertEqual(1, len(response["results"]))
        self.assertEqual("active", response["results"][0]["status"])
        self.assertEqual("L2", response["results"][0]["layer"])
        self.assertIn("程俊豪", response["results"][0]["current_value"])
        step_layers = [step["layer"] for step in response["trace"]["steps"]]
        self.assertEqual(["L0", "L1", "L2", "L3"], step_layers)
        self.assertEqual("no_hot_match_above_threshold", response["trace"]["steps"][1]["note"])

    def test_search_layer_filter_can_select_hot_path(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_retrieval_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(
                "project:feishu_ai_challenge",
                "生产部署必须加 --canary --region cn-shanghai。",
                source_type="unit_test",
            )

            response = CopilotService(repository=repo).search(
                SearchRequest.from_payload(
                    {
                        "query": "生产部署参数",
                        "scope": "project:feishu_ai_challenge",
                        "filters": {"layer": "L1"},
                    }
                )
            )
            conn.close()

        self.assertTrue(response["ok"])
        self.assertEqual(1, len(response["results"]))
        self.assertEqual("L1", response["results"][0]["layer"])
        self.assertEqual(["L1"], response["trace"]["layers"])

    def test_default_search_does_not_return_candidates_or_raw_l3_events(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_retrieval_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.add_candidate(
                "project:feishu_ai_challenge",
                "客户项目验收标准需要候选复核。",
                source_type="unit_test",
                source_id="doc_1",
                document_token="doc_token_1",
                document_title="验收标准",
                quote="客户项目验收标准需要候选复核。",
            )
            repo.add_noise_event("project:feishu_ai_challenge", "raw events 里有一条不该默认返回的历史证据")

            response = CopilotService(repository=repo).search(
                SearchRequest.from_payload(
                    {
                        "query": "验收标准",
                        "scope": "project:feishu_ai_challenge",
                        "top_k": 3,
                    }
                )
            )
            conn.close()

        self.assertTrue(response["ok"])
        self.assertEqual([], response["results"])
        self.assertEqual("no_active_memory_with_evidence", response["trace"]["final_reason"])
        self.assertIn("L3", response["trace"]["layers"])
        self.assertEqual("l3_raw_events_blocked_for_default_search", response["trace"]["steps"][-1]["note"])


if __name__ == "__main__":
    unittest.main()
