from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from memory_engine.benchmark import run_document_ingestion_benchmark
from memory_engine.db import connect, init_db
from memory_engine.document_ingestion import extract_candidate_quotes, fetch_feishu_document_text, ingest_document_source
from memory_engine.repository import MemoryRepository
from temp_utils import WorkspaceTempDir


FIXTURE = Path("tests/fixtures/day5_doc_ingestion_fixture.md")


class DocumentIngestionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = WorkspaceTempDir("document_ingestion")
        self.db_path = Path(self.temp_dir.name) / "memory.sqlite"
        self.conn = connect(self.db_path)
        init_db(self.conn)
        self.repo = MemoryRepository(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    def test_extracts_candidate_quotes_from_markdown(self) -> None:
        quotes = extract_candidate_quotes(FIXTURE.read_text(encoding="utf-8"))

        self.assertGreaterEqual(len(quotes), 5)
        self.assertTrue(any("生产部署必须加" in quote for quote in quotes))
        self.assertFalse(any("咖啡" in quote for quote in quotes))

    def test_ingests_candidates_and_preserves_document_evidence(self) -> None:
        result = ingest_document_source(self.repo, str(FIXTURE), limit=7)

        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["candidate_count"], 5)
        candidate_ids = [item["memory_id"] for item in result["candidates"] if item["action"] == "created"]
        self.assertGreaterEqual(len(candidate_ids), 5)

        inactive_recall = self.repo.recall("project:feishu_ai_challenge", "生产部署参数")
        self.assertIsNone(inactive_recall)

        confirm = self.repo.confirm_candidate(candidate_ids[0])
        self.assertEqual(confirm["action"], "confirmed")

        recall = self.repo.recall("project:feishu_ai_challenge", "生产部署参数")
        self.assertIsNotNone(recall)
        assert recall is not None
        self.assertEqual(recall["status"], "active")
        self.assertEqual(recall["source"]["source_type"], "document_markdown")
        self.assertEqual(recall["source"]["document_title"], "Day5 架构决策文档")
        self.assertIn("生产部署必须加", recall["source"]["quote"])

    def test_reject_candidate_keeps_it_out_of_recall(self) -> None:
        result = ingest_document_source(self.repo, str(FIXTURE), limit=1)
        candidate_id = result["candidates"][0]["memory_id"]

        reject = self.repo.reject_candidate(candidate_id)
        self.assertEqual(reject["action"], "rejected")
        self.assertIsNone(self.repo.recall("project:feishu_ai_challenge", "生产部署参数"))

    def test_feishu_fetch_uses_v2_doc_format_and_extracts_content(self) -> None:
        completed = Mock()
        completed.stdout = '{"ok":true,"data":{"document":{"content":"# 标题\\n\\n- 决定：生产部署必须加 --canary。"}}}'
        with patch("memory_engine.document_ingestion.subprocess.run", return_value=completed) as run:
            text = fetch_feishu_document_text(
                "doc_token",
                lark_cli="lark-cli",
                profile="feishu-ai-challenge",
                as_identity="user",
            )

        run.assert_called_once()
        command = run.call_args.args[0]
        self.assertEqual(
            command,
            [
                "lark-cli",
                "--profile",
                "feishu-ai-challenge",
                "--as",
                "user",
                "docs",
                "+fetch",
                "--api-version",
                "v2",
                "--doc",
                "doc_token",
                "--doc-format",
                "markdown",
            ],
        )
        self.assertIn("生产部署必须加", text)

    def test_day5_ingestion_benchmark(self) -> None:
        result = run_document_ingestion_benchmark("benchmarks/day5_ingestion_cases.json")

        self.assertEqual(result["summary"]["case_count"], 2)
        self.assertEqual(result["summary"]["case_pass_rate"], 1.0)
        self.assertEqual(result["summary"]["avg_quote_coverage"], 1.0)
        self.assertEqual(result["summary"]["avg_noise_rejection_rate"], 1.0)
        self.assertEqual(result["summary"]["document_evidence_coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
