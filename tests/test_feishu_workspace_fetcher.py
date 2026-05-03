from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from memory_engine.db import connect, init_db
from memory_engine.document_ingestion import FeishuIngestionSource, ingest_feishu_source
from memory_engine.feishu_api_client import FeishuApiResult
from memory_engine.feishu_workspace_fetcher import (
    WorkspaceActor,
    WorkspaceResource,
    discover_workspace_resources,
    fetch_workspace_resource_sources,
    workspace_current_context,
)
from memory_engine.repository import MemoryRepository

SCOPE = "project:feishu_ai_challenge"


def _ok(data: dict) -> FeishuApiResult:
    return FeishuApiResult(ok=True, data=data, returncode=0)


class FeishuWorkspaceFetcherTest(unittest.TestCase):
    def test_discovers_workspace_resources_with_drive_search(self) -> None:
        with patch("memory_engine.feishu_workspace_fetcher.run_lark_cli") as run:
            run.return_value = _ok(
                {
                    "results": [
                        {
                            "type": "DOCX",
                            "title": "部署决策",
                            "token": "doc_1",
                            "url": "https://example.feishu.cn/docx/doc_1",
                        },
                        {
                            "type": "Base",
                            "title": "项目知识库",
                            "app_token": "app_1",
                            "url": "https://example.feishu.cn/base/app_1",
                        },
                    ],
                    "has_more": False,
                }
            )

            resources = discover_workspace_resources(
                query="",
                limit=10,
                profile="feishu-ai-challenge",
                edited_since="30d",
            )

        self.assertEqual(["document", "bitable"], [item.route_type for item in resources])
        self.assertEqual("doc_1", resources[0].token)
        self.assertEqual("app_1", resources[1].token)
        self.assertEqual(
            [
                "--profile",
                "feishu-ai-challenge",
                "--as",
                "user",
                "drive",
                "+search",
                "--query",
                "",
                "--doc-types",
                "doc,docx,wiki,sheet,bitable",
                "--page-size",
                "10",
                "--format",
                "json",
                "--edited-since",
                "30d",
            ],
            run.call_args.args[0],
        )

    def test_discovers_paginated_resources_until_limit(self) -> None:
        with patch("memory_engine.feishu_workspace_fetcher.run_lark_cli") as run:
            run.side_effect = [
                _ok({"results": [{"type": "docx", "token": "doc_1"}], "has_more": True, "page_token": "next"}),
                _ok({"results": [{"type": "sheet", "token": "sheet_1"}], "has_more": False}),
            ]

            resources = discover_workspace_resources(limit=2, max_pages=3)

        self.assertEqual(["doc_1", "sheet_1"], [item.token for item in resources])
        self.assertIn("--page-token", run.call_args_list[1].args[0])

    @patch("memory_engine.document_ingestion.subprocess.run")
    def test_fetches_document_resource_as_feishu_source(self, subprocess_run: Mock) -> None:
        completed = Mock()
        completed.stdout = '{"ok":true,"data":{"document":{"content":"# 决策\\n决定：上线窗口固定为周四。"}}}'
        subprocess_run.return_value = completed
        resource = WorkspaceResource(
            resource_type="docx",
            token="doc_1",
            title="部署决策",
            url="https://example.feishu.cn/docx/doc_1",
        )

        sources = fetch_workspace_resource_sources(resource, profile="feishu-ai-challenge")

        self.assertEqual(1, len(sources))
        self.assertEqual("document_feishu", sources[0].source_type)
        self.assertEqual("doc_1", sources[0].source_id)
        self.assertIn("上线窗口固定", sources[0].text)

    def test_fetches_sheet_resource_from_info_and_read(self) -> None:
        with patch("memory_engine.feishu_workspace_fetcher.run_lark_cli") as run:
            run.side_effect = [
                _ok({"data": {"spreadsheet": {"sheets": [{"sheet_id": "sh_1", "title": "规则"}]}}}),
                _ok({"data": {"valueRange": {"values": [["类型", "内容"], ["决定", "生产部署必须加审计"]]}}}),
            ]
            resource = WorkspaceResource(resource_type="sheet", token="sht_1", title="项目规则")

            sources = fetch_workspace_resource_sources(resource, max_sheet_rows=20)

        self.assertEqual(1, len(sources))
        self.assertEqual("lark_sheet", sources[0].source_type)
        self.assertEqual("sht_1", sources[0].metadata["sheet_token"])
        self.assertEqual("sh_1", sources[0].metadata["sheet_id"])
        self.assertIn("生产部署必须加审计", sources[0].text)

    def test_fetches_bitable_resource_by_tables_and_records(self) -> None:
        with patch("memory_engine.feishu_bitable_fetcher.run_lark_cli") as run:
            run.side_effect = [
                _ok({"data": {"items": [{"table_id": "tbl_1", "name": "知识"}]}}),
                _ok({"data": {"items": [{"record_id": "rec_1", "fields": {"规则": "生产部署必须加审计"}}]}}),
                _ok({"data": {"record": {"fields": {"规则": "生产部署必须加审计"}}}}),
            ]
            resource = WorkspaceResource(resource_type="bitable", token="app_1", title="项目知识库")

            sources = fetch_workspace_resource_sources(resource, max_bitable_records=10)

        self.assertEqual(1, len(sources))
        self.assertEqual("lark_bitable", sources[0].source_type)
        self.assertEqual("rec_1", sources[0].source_id)
        self.assertEqual("app_1", sources[0].metadata["app_token"])

    def test_workspace_current_context_allows_sheet_ingestion_candidate_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            conn = connect(Path(temp_dir) / "memory.sqlite")
            init_db(conn)
            repo = MemoryRepository(conn)
            source = FeishuIngestionSource(
                source_type="lark_sheet",
                source_id="sht_1",
                title="项目规则 / 规则",
                text="决定：生产部署必须加审计。",
                actor_id="workspace_sheet_fetch",
                metadata={"sheet_token": "sht_1", "sheet_id": "sh_1"},
            )
            context = workspace_current_context(
                scope=SCOPE,
                actor=WorkspaceActor(open_id="ou_reviewer"),
                source=source,
            )

            result = ingest_feishu_source(repo, source, scope=SCOPE, current_context=context)

            self.assertTrue(result["ok"])
            self.assertEqual(1, result["candidate_count"])
            self.assertEqual("lark_sheet", result["candidates"][0]["evidence"]["source_type"])
            self.assertEqual("sht_1", result["source_metadata"]["sheet_token"])
            self.assertEqual(
                0, conn.execute("SELECT COUNT(*) AS count FROM memories WHERE status = 'active'").fetchone()["count"]
            )
            conn.close()


if __name__ == "__main__":
    unittest.main()
