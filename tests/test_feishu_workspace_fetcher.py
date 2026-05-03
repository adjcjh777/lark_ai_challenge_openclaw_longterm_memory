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
    discover_drive_folder_resources,
    discover_wiki_space_resources,
    discover_workspace_resource_batch,
    discover_workspace_resources,
    fetch_workspace_resource_sources,
    inspect_sheet_resource,
    workspace_resource_from_spec,
    workspace_current_context,
)
from memory_engine.repository import MemoryRepository

SCOPE = "project:feishu_ai_challenge"


def _ok(data: dict) -> FeishuApiResult:
    return FeishuApiResult(ok=True, data=data, returncode=0)


class FeishuWorkspaceFetcherTest(unittest.TestCase):
    def test_parses_explicit_workspace_resource_spec(self) -> None:
        resource = workspace_resource_from_spec("bitable:app_1:项目看板")

        self.assertEqual("bitable", resource.resource_type)
        self.assertEqual("app_1", resource.token)
        self.assertEqual("项目看板", resource.title)
        self.assertEqual("bitable", resource.route_type)

    def test_explicit_workspace_resource_spec_requires_type_and_token(self) -> None:
        with self.assertRaises(ValueError):
            workspace_resource_from_spec("bitable")

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

    def test_discovers_resumable_batch_with_next_page_token(self) -> None:
        with patch("memory_engine.feishu_workspace_fetcher.run_lark_cli") as run:
            run.return_value = _ok(
                {
                    "results": [{"type": "docx", "token": "doc_2"}],
                    "has_more": True,
                    "page_token": "next_2",
                }
            )

            batch = discover_workspace_resource_batch(
                limit=1,
                max_pages=1,
                start_page_token="next_1",
            )

        self.assertEqual(["doc_2"], [item.token for item in batch.resources])
        self.assertEqual(1, batch.pages_seen)
        self.assertEqual("next_2", batch.next_page_token)
        self.assertFalse(batch.exhausted)
        self.assertIn("--page-token", run.call_args.args[0])
        self.assertIn("next_1", run.call_args.args[0])

    def test_discovers_workspace_resources_with_scan_filters(self) -> None:
        with patch("memory_engine.feishu_workspace_fetcher.run_lark_cli") as run:
            run.return_value = _ok({"results": [], "has_more": False})

            discover_workspace_resources(
                query="",
                limit=5,
                mine=True,
                opened_since="30d",
                opened_until="2026-05-04",
                creator_ids="ou_creator",
                sharer_ids="ou_sharer",
                chat_ids="oc_chat",
                sort="edit_time",
            )

        argv = run.call_args.args[0]
        self.assertIn("--mine", argv)
        self.assertIn("--opened-since", argv)
        self.assertIn("30d", argv)
        self.assertIn("--opened-until", argv)
        self.assertIn("2026-05-04", argv)
        self.assertIn("--creator-ids", argv)
        self.assertIn("ou_creator", argv)
        self.assertIn("--sharer-ids", argv)
        self.assertIn("ou_sharer", argv)
        self.assertIn("--chat-ids", argv)
        self.assertIn("oc_chat", argv)
        self.assertIn("--sort", argv)
        self.assertIn("edit_time", argv)

    def test_discovers_workspace_resources_from_current_drive_search_shape(self) -> None:
        with patch("memory_engine.feishu_workspace_fetcher.run_lark_cli") as run:
            run.return_value = _ok(
                {
                    "data": {
                        "results": [
                            {
                                "entity_type": "WIKI",
                                "result_meta": {
                                    "doc_types": "SHEET",
                                    "icon_info": '{"token":"sht_underlying","obj_type":3}',
                                    "token": "wiki_node_token",
                                    "url": "https://example.feishu.cn/wiki/wiki_node_token",
                                },
                                "title_highlighted": "<h>飞书挑战赛</h>任务跟进看板",
                            },
                            {
                                "entity_type": "DOC",
                                "result_meta": {
                                    "doc_types": "SHEET",
                                    "token": "sht_doc_token",
                                    "url": "https://example.feishu.cn/sheets/sht_doc_token",
                                },
                                "title_highlighted": "项目指标表",
                            },
                        ],
                        "has_more": False,
                    }
                }
            )

            resources = discover_workspace_resources(doc_types=["sheet"], limit=10)

        self.assertEqual(["sht_underlying", "sht_doc_token"], [item.token for item in resources])
        self.assertEqual(["sheet", "sheet"], [item.resource_type for item in resources])
        self.assertEqual(["sheet", "sheet"], [item.route_type for item in resources])
        self.assertEqual("<h>飞书挑战赛</h>任务跟进看板", resources[0].title)
        self.assertEqual("项目指标表", resources[1].title)

    def test_discovers_drive_folder_resources_and_recurses_folders(self) -> None:
        with patch("memory_engine.feishu_workspace_fetcher.run_lark_cli") as run:
            run.side_effect = [
                _ok(
                    {
                        "data": {
                            "files": [
                                {"type": "docx", "token": "doc_1", "name": "方案"},
                                {"type": "folder", "token": "fld_child", "name": "子目录"},
                            ],
                            "has_more": False,
                        },
                    }
                ),
                _ok(
                    {
                        "data": {
                            "files": [
                                {"type": "bitable", "token": "app_1", "name": "任务表"},
                            ],
                            "has_more": False,
                        },
                    }
                ),
            ]

            resources = discover_drive_folder_resources(
                folder_tokens=["fld_root"],
                max_depth=1,
                limit=10,
                profile="feishu-ai-challenge",
            )

        self.assertEqual(["doc_1", "app_1"], [item.token for item in resources])
        self.assertEqual(["document", "bitable"], [item.route_type for item in resources])
        first_argv = run.call_args_list[0].args[0]
        second_argv = run.call_args_list[1].args[0]
        self.assertIn("drive", first_argv)
        self.assertIn("files", first_argv)
        self.assertTrue(any("fld_root" in item for item in first_argv))
        self.assertTrue(any("fld_child" in item for item in second_argv))

    def test_drive_folder_discovery_respects_doc_type_filter(self) -> None:
        with patch("memory_engine.feishu_workspace_fetcher.run_lark_cli") as run:
            run.return_value = _ok(
                {
                    "data": {
                        "files": [
                            {"type": "docx", "token": "doc_1", "name": "方案"},
                            {"type": "sheet", "token": "sht_1", "name": "指标"},
                            {"type": "bitable", "token": "app_1", "name": "任务表"},
                        ],
                        "has_more": False,
                    },
                }
            )

            resources = discover_drive_folder_resources(folder_tokens=["fld_root"], doc_types=["sheet"], limit=10)

        self.assertEqual(["sht_1"], [item.token for item in resources])
        self.assertEqual(["sheet"], [item.resource_type for item in resources])

    def test_discovers_wiki_space_resources_from_nodes(self) -> None:
        with patch("memory_engine.feishu_workspace_fetcher.run_lark_cli") as run:
            run.side_effect = [
                _ok(
                    {
                        "data": {
                            "items": [
                                {
                                    "obj_type": "docx",
                                    "obj_token": "doc_1",
                                    "title": "知识库方案",
                                    "node_token": "wik_1",
                                    "has_child": True,
                                },
                            ],
                            "has_more": False,
                        },
                    }
                ),
                _ok(
                    {
                        "data": {
                            "items": [
                                {
                                    "obj_type": "sheet",
                                    "obj_token": "sht_1",
                                    "title": "指标表",
                                    "node_token": "wik_2",
                                },
                            ],
                            "has_more": False,
                        },
                    }
                ),
            ]

            resources = discover_wiki_space_resources(space_ids=["space_1"], max_depth=1, limit=10)

        self.assertEqual(["doc_1", "sht_1"], [item.token for item in resources])
        self.assertEqual(["document", "sheet"], [item.route_type for item in resources])
        self.assertTrue(any("space_1" in item for item in run.call_args_list[0].args[0]))
        self.assertTrue(any("wik_1" in item for item in run.call_args_list[1].args[0]))

    def test_wiki_space_discovery_respects_doc_type_filter(self) -> None:
        with patch("memory_engine.feishu_workspace_fetcher.run_lark_cli") as run:
            run.return_value = _ok(
                {
                    "data": {
                        "items": [
                            {"obj_type": "docx", "obj_token": "doc_1", "title": "方案"},
                            {"obj_type": "sheet", "obj_token": "sht_1", "title": "指标"},
                        ],
                        "has_more": False,
                    },
                }
            )

            resources = discover_wiki_space_resources(space_ids=["space_1"], doc_types=["sheet"], limit=10)

        self.assertEqual(["sht_1"], [item.token for item in resources])
        self.assertEqual(["sheet"], [item.resource_type for item in resources])

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

    def test_fetches_sheet_resource_from_current_lark_cli_info_shape(self) -> None:
        with patch("memory_engine.feishu_workspace_fetcher.run_lark_cli") as run:
            run.side_effect = [
                _ok({"data": {"sheets": {"sheets": [{"sheet_id": "sh_1", "title": "规则"}]}}}),
                _ok({"data": {"valueRange": {"values": [["类型", "内容"], ["决定", "生产部署必须加审计"]]}}}),
            ]
            resource = WorkspaceResource(resource_type="sheet", token="sht_1", title="项目规则")

            sources = fetch_workspace_resource_sources(resource, max_sheet_rows=20)

        self.assertEqual(1, len(sources))
        self.assertEqual("lark_sheet", sources[0].source_type)
        self.assertEqual("sh_1", sources[0].metadata["sheet_id"])

    def test_skips_bitable_backed_sheet_tabs_without_silent_failure(self) -> None:
        with patch("memory_engine.feishu_workspace_fetcher.run_lark_cli") as run:
            run.return_value = _ok(
                {
                    "data": {
                        "sheets": {
                            "sheets": [
                                {
                                    "sheet_id": "sh_bitable",
                                    "title": "任务跟进看板",
                                    "resource_type": "bitable",
                                }
                            ]
                        }
                    }
                }
            )
            resource = WorkspaceResource(resource_type="sheet", token="sht_1", title="项目规则")

            sources = fetch_workspace_resource_sources(resource, max_sheet_rows=20)

        self.assertEqual([], sources)
        self.assertEqual(1, run.call_count)

    def test_inspects_sheet_resource_without_reading_cells(self) -> None:
        with patch("memory_engine.feishu_workspace_fetcher.run_lark_cli") as run:
            run.return_value = _ok(
                {
                    "data": {
                        "sheets": {
                            "sheets": [
                                {"sheet_id": "sh_1", "title": "规则", "resource_type": "sheet"},
                                {"sheet_id": "sh_2", "title": "看板", "resource_type": "bitable"},
                            ]
                        }
                    }
                }
            )
            resource = WorkspaceResource(resource_type="sheet", token="sht_1", title="项目规则")

            inspection = inspect_sheet_resource(resource, profile="feishu-ai-challenge")

        self.assertTrue(inspection["is_normal_sheet"])
        self.assertFalse(inspection["is_sheet_backed_bitable_only"])
        self.assertEqual(2, inspection["sheet_count"])
        self.assertEqual(1, inspection["normal_sheet_count"])
        self.assertEqual(["规则"], inspection["normal_sheet_titles"])
        self.assertEqual(["bitable"], inspection["embedded_resource_types"])
        self.assertEqual(1, run.call_count)
        self.assertNotIn("+read", run.call_args.args[0])

    def test_inspects_sheet_backed_bitable_only_resource(self) -> None:
        with patch("memory_engine.feishu_workspace_fetcher.run_lark_cli") as run:
            run.return_value = _ok(
                {
                    "data": {
                        "sheets": {
                            "sheets": [
                                {"sheet_id": "sh_bitable", "title": "任务看板", "resource_type": "bitable"},
                            ]
                        }
                    }
                }
            )
            resource = WorkspaceResource(resource_type="sheet", token="sht_1", title="任务看板")

            inspection = inspect_sheet_resource(resource)

        self.assertFalse(inspection["is_normal_sheet"])
        self.assertTrue(inspection["is_sheet_backed_bitable_only"])
        self.assertEqual(0, inspection["normal_sheet_count"])

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
