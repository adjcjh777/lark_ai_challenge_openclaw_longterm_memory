from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_engine.db import connect, init_db
from memory_engine.document_ingestion import FeishuIngestionSource
from memory_engine.feishu_workspace_fetcher import WorkspaceActor, WorkspaceResource
from scripts.check_workspace_real_chat_resource_gate import ChatInput
from scripts.check_workspace_real_same_conclusion_sample_finder import collect_reviewed_resources, run_sample_finder


class WorkspaceRealSameConclusionSampleFinderTest(unittest.TestCase):
    def test_finder_runs_strict_gate_when_exact_fact_match_exists(self) -> None:
        report = self._run(
            chats=[
                ChatInput(
                    message_id="msg_real_001",
                    chat_id="chat_real",
                    sender_id="ou_sender",
                    text="决定：生产部署必须加 --canary --region cn-shanghai。",
                    created_at="2026-05-04T00:00:00+08:00",
                    source="event_log",
                )
            ],
            sources=[
                FeishuIngestionSource(
                    source_type="document_feishu",
                    source_id="doc_real_001",
                    title="Project doc",
                    text="上线说明\n决定：生产部署必须加 --canary --region cn-shanghai。",
                    actor_id="ou_reviewer",
                    created_at="2026-05-04T00:00:00+08:00",
                )
            ],
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("pass", report["status"])
        self.assertEqual(1, report["summary"]["same_fact_match_count"])
        self.assertEqual("pass", report["strict_gate"]["status"])
        self.assertEqual(["document_feishu", "feishu_message"], report["strict_gate"]["active_evidence_source_types"])
        self.assertNotIn("生产部署必须", str(report))
        self.assertNotIn("msg_real_001", str(report))
        self.assertNotIn("doc_real_001", str(report))

    def test_finder_fails_when_no_workspace_source_repeats_chat_fact(self) -> None:
        report = self._run(
            chats=[
                ChatInput(
                    message_id="msg_real_002",
                    chat_id="chat_real",
                    sender_id="ou_sender",
                    text="决定：非 @ 群消息 live gate 测试，今天只验证事件投递。",
                    created_at="2026-05-04T00:00:00+08:00",
                    source="event_log",
                )
            ],
            sources=[
                FeishuIngestionSource(
                    source_type="document_feishu",
                    source_id="doc_real_002",
                    title="Project doc",
                    text="当前状态：MVP / Demo / Pre-production 本地闭环已完成。",
                    actor_id="ou_reviewer",
                    created_at="2026-05-04T00:00:00+08:00",
                )
            ],
        )

        self.assertFalse(report["ok"])
        self.assertIn("same_fact_match_count", report["failures"])
        self.assertIsNone(report["strict_gate"])
        self.assertEqual(0, report["summary"]["same_fact_match_count"])

    def test_collect_reviewed_resources_expands_read_only_discovery_inputs(self) -> None:
        with (
            patch(
                "scripts.check_workspace_real_same_conclusion_sample_finder.discover_workspace_resources",
                return_value=[
                    WorkspaceResource(resource_type="docx", token="doc_1", title="Project doc"),
                    WorkspaceResource(resource_type="docx", token="doc_1", title="Project doc duplicate"),
                ],
            ) as search,
            patch(
                "scripts.check_workspace_real_same_conclusion_sample_finder.discover_drive_folder_resources",
                return_value=[WorkspaceResource(resource_type="sheet", token="sht_1", title="Project sheet")],
            ) as folder,
            patch(
                "scripts.check_workspace_real_same_conclusion_sample_finder.discover_wiki_space_resources",
                return_value=[WorkspaceResource(resource_type="bitable", token="base_1", title="Project base")],
            ) as wiki,
        ):
            resources = collect_reviewed_resources(
                specs=["docx:doc_1:Reviewed doc"],
                queries=["OpenClaw"],
                doc_types=["docx", "sheet", "bitable"],
                opened_since="365d",
                limit=20,
                max_pages=2,
                folder_walk_root=True,
                folder_walk_tokens="fld_1",
                wiki_space_walk_ids="my_library",
                walk_max_depth=2,
                walk_page_size=50,
                profile=None,
                as_identity="user",
            )

        self.assertEqual(["doc_1", "sht_1", "base_1"], [resource.token for resource in resources])
        search.assert_called_once()
        folder.assert_called_once()
        wiki.assert_called_once()

    def _run(self, *, chats: list[ChatInput], sources: list[FeishuIngestionSource]) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temp_dir:
            conn = connect(Path(temp_dir) / "sample-finder.sqlite")
            try:
                init_db(conn)
                return run_sample_finder(
                    conn,
                    chats=chats,
                    resource_sources=sources,
                    fetch_failure_count=0,
                    actor=WorkspaceActor(
                        user_id="ou_reviewer",
                        open_id=None,
                        tenant_id="tenant:demo",
                        organization_id="org:demo",
                        roles=("member", "reviewer"),
                    ),
                    scope="project:feishu_ai_challenge",
                )
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
