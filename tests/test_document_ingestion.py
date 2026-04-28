from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from memory_engine.benchmark import run_document_ingestion_benchmark
from memory_engine.db import connect, init_db
from memory_engine.document_ingestion import (
    FeishuIngestionSource,
    extract_candidate_quotes,
    fetch_feishu_document_text,
    ingest_document_source,
    ingest_feishu_source,
    mark_feishu_source_revoked,
)
from memory_engine.repository import MemoryRepository

FIXTURE = Path("tests/fixtures/day5_doc_ingestion_fixture.md")
SCOPE = "project:feishu_ai_challenge"


def permission_context(*, document_id: str = "doc_token", **source_context_extra: str) -> dict[str, object]:
    source_context = {
        "entrypoint": "limited_feishu_ingestion",
        "workspace_id": SCOPE,
    }
    if document_id:
        source_context["document_id"] = document_id
    source_context.update(source_context_extra)
    return {
        "scope": SCOPE,
        "permission": {
            "request_id": "req_limited_feishu_ingestion",
            "trace_id": "trace_limited_feishu_ingestion",
            "actor": {
                "user_id": "ou_ingestion_reviewer",
                "tenant_id": "tenant:demo",
                "organization_id": "org:demo",
                "roles": ["member", "reviewer"],
            },
            "source_context": source_context,
            "requested_action": "memory.create_candidate",
            "requested_visibility": "team",
            "timestamp": "2026-05-07T00:00:00+08:00",
        },
    }


class DocumentIngestionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
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

    def test_feishu_ingestion_missing_permission_fails_closed_before_fetch(self) -> None:
        with patch("memory_engine.document_ingestion.fetch_feishu_document_text") as fetch:
            result = ingest_document_source(self.repo, "doc_token", limit=1)

        fetch.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "permission_denied")
        self.assertEqual(result["error"]["details"]["reason_code"], "missing_permission_context")

    def test_feishu_ingestion_malformed_permission_fails_closed_before_fetch(self) -> None:
        with patch("memory_engine.document_ingestion.fetch_feishu_document_text") as fetch:
            result = ingest_document_source(
                self.repo,
                "doc_token",
                current_context={"permission": {"request_id": "req_malformed"}},
                limit=1,
            )

        fetch.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "permission_denied")
        self.assertEqual(result["error"]["details"]["reason_code"], "malformed_permission_context")

    def test_limited_feishu_ingestion_creates_candidate_only_with_source_metadata(self) -> None:
        with patch(
            "memory_engine.document_ingestion.fetch_feishu_document_text",
            return_value="# 飞书来源\n\n- 决定：生产部署必须加 --canary --region cn-shanghai。",
        ) as fetch:
            result = ingest_document_source(
                self.repo,
                "https://example.feishu.cn/docx/doc_token",
                current_context=permission_context(document_id="doc_token"),
                limit=1,
            )

        fetch.assert_called_once()
        self.assertTrue(result["ok"])
        self.assertEqual(1, result["candidate_count"])
        self.assertEqual(
            0, self.conn.execute("SELECT COUNT(*) AS count FROM memories WHERE status = 'active'").fetchone()["count"]
        )
        self.assertEqual(
            1,
            self.conn.execute("SELECT COUNT(*) AS count FROM memories WHERE status = 'candidate'").fetchone()["count"],
        )

        candidate = result["candidates"][0]
        self.assertEqual("created", candidate["action"])
        self.assertEqual("candidate", candidate["status"])
        self.assertIn("--canary", candidate["evidence"]["quote"])
        self.assertEqual("document_feishu", candidate["evidence"]["source_type"])
        self.assertEqual("doc_token", candidate["evidence"]["source_doc_id"])
        self.assertEqual("doc_token", candidate["source_metadata"]["document_token"])
        self.assertEqual("飞书来源", candidate["source_metadata"]["document_title"])
        self.assertEqual("limited_feishu_ingestion", candidate["source_metadata"]["entrypoint"])
        self.assertEqual("req_limited_feishu_ingestion", result["ingestion_trace"]["request_id"])
        self.assertEqual("trace_limited_feishu_ingestion", result["ingestion_trace"]["trace_id"])
        self.assertEqual("allow", result["ingestion_trace"]["permission_decision"]["decision"])
        self.assertIsNone(self.repo.recall(SCOPE, "生产部署参数"))

    def test_feishu_ingestion_source_context_mismatch_fails_closed_before_fetch(self) -> None:
        with patch("memory_engine.document_ingestion.fetch_feishu_document_text") as fetch:
            result = ingest_document_source(
                self.repo,
                "doc_token",
                current_context=permission_context(document_id="other_doc"),
                limit=1,
            )

        fetch.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertEqual("permission_denied", result["error"]["code"])
        self.assertEqual("source_context_mismatch", result["error"]["details"]["reason_code"])
        self.assertEqual("req_limited_feishu_ingestion", result["error"]["details"]["request_id"])
        self.assertEqual("trace_limited_feishu_ingestion", result["error"]["details"]["trace_id"])
        rendered = str(result)
        self.assertNotIn("--canary", rendered)
        self.assertNotIn("candidates", result)
        self.assertNotIn("document", result)

    def test_feishu_ingestion_missing_document_id_fails_closed_before_fetch(self) -> None:
        with patch("memory_engine.document_ingestion.fetch_feishu_document_text") as fetch:
            result = ingest_document_source(
                self.repo,
                "doc_token",
                current_context=permission_context(document_id=""),
                limit=1,
            )

        fetch.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertEqual("permission_denied", result["error"]["code"])
        self.assertEqual("source_context_mismatch", result["error"]["details"]["reason_code"])
        self.assertEqual("missing_document_id", result["error"]["details"]["source_context_error"])
        self.assertEqual("req_limited_feishu_ingestion", result["error"]["details"]["request_id"])
        self.assertEqual("trace_limited_feishu_ingestion", result["error"]["details"]["trace_id"])
        self.assertNotIn("candidates", result)
        self.assertNotIn("document", result)

    def test_limited_feishu_ingestion_supports_task_meeting_and_bitable_candidate_only(self) -> None:
        sources = [
            FeishuIngestionSource(
                source_type="feishu_task",
                source_id="task_1",
                title="上线任务",
                text="决定：上线任务负责人是程俊豪，截止 2026-04-30。",
                actor_id="ou_task_owner",
            ),
            FeishuIngestionSource(
                source_type="feishu_meeting",
                source_id="meeting_1",
                title="发布复盘会",
                text="风险：发布复盘会确认灰度期间不能关闭审计日志。",
                actor_id="ou_meeting_owner",
            ),
            FeishuIngestionSource(
                source_type="lark_bitable",
                source_id="record_1",
                title="上线参数表",
                text="规则：Bitable 记录要求生产部署 region 使用 ap-shanghai。",
                actor_id="ou_bitable_owner",
                metadata={"app_token": "app_token", "table_id": "tbl_1", "record_id": "record_1"},
            ),
        ]

        results = [
            ingest_feishu_source(
                self.repo,
                source,
                current_context=permission_context(
                    document_id="",
                    task_id="task_1" if source.source_type == "feishu_task" else "",
                    meeting_id="meeting_1" if source.source_type == "feishu_meeting" else "",
                    bitable_record_id="record_1" if source.source_type == "lark_bitable" else "",
                ),
                limit=1,
            )
            for source in sources
        ]

        self.assertTrue(all(result["ok"] for result in results))
        self.assertEqual([1, 1, 1], [result["candidate_count"] for result in results])
        self.assertEqual(
            3,
            self.conn.execute("SELECT COUNT(*) AS count FROM memory_versions WHERE status = 'candidate'").fetchone()[
                "count"
            ],
        )
        self.assertEqual(
            0, self.conn.execute("SELECT COUNT(*) AS count FROM memories WHERE status = 'active'").fetchone()["count"]
        )
        self.assertEqual(
            ["feishu_task", "feishu_meeting", "lark_bitable"],
            [result["candidates"][0]["evidence"]["source_type"] for result in results],
        )
        self.assertEqual("record_1", results[2]["source_metadata"]["bitable_record_id"])
        self.assertIsNone(self.repo.recall(SCOPE, "生产部署 region"))

    def test_limited_feishu_ingestion_source_id_mismatch_fails_closed_before_candidate(self) -> None:
        result = ingest_feishu_source(
            self.repo,
            FeishuIngestionSource(
                source_type="feishu_task",
                source_id="task_1",
                title="上线任务",
                text="决定：上线任务负责人是程俊豪。",
                actor_id="ou_task_owner",
            ),
            current_context=permission_context(document_id="", task_id="other_task"),
            limit=1,
        )

        self.assertFalse(result["ok"])
        self.assertEqual("permission_denied", result["error"]["code"])
        self.assertEqual("source_context_mismatch", result["error"]["details"]["reason_code"])
        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) AS count FROM memories").fetchone()["count"])

    def test_source_revocation_marks_confirmed_memory_stale_and_hides_recall(self) -> None:
        created = ingest_feishu_source(
            self.repo,
            FeishuIngestionSource(
                source_type="feishu_task",
                source_id="task_1",
                title="上线任务",
                text="决定：上线任务负责人是程俊豪。",
                actor_id="ou_task_owner",
            ),
            current_context=permission_context(document_id="", task_id="task_1"),
            limit=1,
        )
        candidate_id = created["candidates"][0]["candidate_id"]
        confirm = self.repo.confirm_candidate(candidate_id)
        self.assertEqual("confirmed", confirm["action"])
        self.assertIsNotNone(self.repo.recall(SCOPE, "上线任务负责人"))

        revoked = mark_feishu_source_revoked(
            self.repo,
            source_type="feishu_task",
            source_id="task_1",
            current_context=permission_context(document_id="", task_id="task_1"),
        )

        self.assertTrue(revoked["ok"])
        self.assertEqual(1, revoked["stale_memory_count"])
        self.assertIsNone(self.repo.recall(SCOPE, "上线任务负责人"))
        status = self.conn.execute("SELECT status FROM memories WHERE id = ?", (candidate_id,)).fetchone()["status"]
        self.assertEqual("stale", status)

    def test_day5_ingestion_benchmark(self) -> None:
        result = run_document_ingestion_benchmark("benchmarks/day5_ingestion_cases.json")

        self.assertEqual(result["summary"]["case_count"], 2)
        self.assertEqual(result["summary"]["case_pass_rate"], 1.0)
        self.assertEqual(result["summary"]["avg_quote_coverage"], 1.0)
        self.assertEqual(result["summary"]["avg_noise_rejection_rate"], 1.0)
        self.assertEqual(result["summary"]["document_evidence_coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
