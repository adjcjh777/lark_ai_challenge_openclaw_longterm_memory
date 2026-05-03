from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memory_engine.db import connect, init_db
from memory_engine.document_ingestion import FeishuIngestionSource
from memory_engine.feishu_workspace_fetcher import WorkspaceActor
from scripts.check_workspace_real_chat_resource_gate import ChatInput
from scripts.check_workspace_real_same_conclusion_gate import run_same_conclusion_gate


class WorkspaceRealSameConclusionGateTest(unittest.TestCase):
    def test_passes_when_real_chat_fact_exists_in_workspace_source(self) -> None:
        report = self._run(
            chat_text="决定：生产部署必须加 --canary --region cn-shanghai。",
            resource_sources=[
                FeishuIngestionSource(
                    source_type="document_feishu",
                    source_id="doc_real_gate",
                    title="Project doc",
                    text="上线说明\n决定：生产部署必须加 --canary --region cn-shanghai。",
                    actor_id="ou_reviewer",
                    created_at="2026-05-04T00:00:00+08:00",
                )
            ],
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("pass", report["status"])
        self.assertEqual(["document_feishu", "feishu_message"], report["active_evidence_source_types"])
        self.assertEqual({"document_feishu": 1}, report["matching_source_type_counts"])
        self.assertEqual("duplicate", report["actions"]["workspace_duplicates"][0]["action"])
        self.assertNotIn("决定：生产部署", str(report))

    def test_fails_when_workspace_sources_do_not_contain_same_fact(self) -> None:
        report = self._run(
            chat_text="决定：非 @ 群消息 live gate 测试，今天只验证事件投递。",
            resource_sources=[
                FeishuIngestionSource(
                    source_type="document_feishu",
                    source_id="doc_real_gate",
                    title="Project doc",
                    text="当前状态：MVP / Demo / Pre-production 本地闭环已完成。",
                    actor_id="ou_reviewer",
                    created_at="2026-05-04T00:00:00+08:00",
                )
            ],
        )

        self.assertFalse(report["ok"])
        self.assertIn("same_fact_found_in_workspace_source", report["failures"])
        self.assertEqual(0, report["summary"]["matching_resource_source_count"])
        self.assertEqual([], report["active_evidence_source_types"])

    def _run(self, *, chat_text: str, resource_sources: list[FeishuIngestionSource]) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as temp_dir:
            conn = connect(Path(temp_dir) / "same-conclusion.sqlite")
            try:
                init_db(conn)
                return run_same_conclusion_gate(
                    conn,
                    chat_input=ChatInput(
                        message_id="msg_real_gate",
                        chat_id="chat_real_gate",
                        sender_id="ou_sender",
                        text=chat_text,
                        created_at="2026-05-04T00:00:00+08:00",
                        source="event_log",
                    ),
                    resource_sources=resource_sources,
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
