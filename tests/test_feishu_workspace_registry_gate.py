from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memory_engine.db import connect, init_db
from memory_engine.document_ingestion import FeishuIngestionSource
from memory_engine.feishu_workspace_fetcher import WorkspaceResource
from memory_engine.feishu_workspace_registry import (
    discovery_filter_key,
    finish_workspace_ingestion_run,
    mark_missing_sources_stale,
    record_discovered_resource,
    record_fetch_error,
    record_source_ingested,
    record_workspace_discovery_cursor,
    start_workspace_ingestion_run,
)
from scripts.check_feishu_workspace_registry_gate import build_report


SCOPE = "project:feishu_ai_challenge"
TENANT = "tenant:demo"
ORG = "org:demo"


class FeishuWorkspaceRegistryGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.conn = connect(Path(self.temp_dir.name) / "memory.sqlite")
        self.addCleanup(self.conn.close)
        init_db(self.conn)

    def test_registry_gate_passes_with_ingested_skip_stale_failed_and_cursor_evidence(self) -> None:
        filter_key = discovery_filter_key(query="", doc_types=["docx"], folder_walk_root=True, walk_max_depth=2)
        old_resource = WorkspaceResource(resource_type="docx", token="old_doc", title="旧文档", raw={"revision": "r0"})
        doc_resource = WorkspaceResource(resource_type="docx", token="doc_1", title="方案", raw={"revision": "r1"})
        failed_resource = WorkspaceResource(resource_type="docx", token="doc_denied", title="无权限文档")
        source = FeishuIngestionSource(
            source_type="document_feishu",
            source_id="doc_1",
            title="方案",
            text="决定：上线窗口固定在周四。",
            actor_id="workspace_document_fetch",
        )

        first_run = self._start_run(filter_key)
        record_discovered_resource(
            self.conn,
            resource=old_resource,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            run_id=first_run,
        )
        record_discovered_resource(
            self.conn,
            resource=doc_resource,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            run_id=first_run,
        )
        record_source_ingested(
            self.conn,
            source=source,
            resource=doc_resource,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            run_id=first_run,
            candidate_count=1,
            duplicate_count=0,
        )
        record_workspace_discovery_cursor(
            self.conn,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            run_id=first_run,
            page_token="next_1",
            pages_seen=1,
            resource_count=2,
            filters={"folder_walk_root": True},
        )
        finish_workspace_ingestion_run(
            self.conn,
            run_id=first_run,
            status="completed",
            resource_count=2,
            fetched_count=1,
            ingested_count=1,
            skipped_unchanged_count=0,
            failed_count=0,
            stale_marked_count=0,
        )

        second_run = self._start_run(filter_key)
        record_discovered_resource(
            self.conn,
            resource=doc_resource,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            run_id=second_run,
        )
        record_discovered_resource(
            self.conn,
            resource=failed_resource,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            run_id=second_run,
        )
        record_fetch_error(
            self.conn,
            resource=failed_resource,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            run_id=second_run,
            error_code="permission_denied",
            error_message="permission denied",
        )
        stale_count = mark_missing_sources_stale(
            self.conn,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            run_id=second_run,
        )
        finish_workspace_ingestion_run(
            self.conn,
            run_id=second_run,
            status="completed_with_errors",
            resource_count=2,
            fetched_count=0,
            ingested_count=0,
            skipped_unchanged_count=1,
            failed_count=1,
            stale_marked_count=stale_count,
        )

        report = build_report(
            self.conn,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            min_runs=2,
            require_ingested=True,
            require_skipped=True,
            require_stale=True,
            require_failed=True,
            require_cursor=True,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual(2, report["run_count"])
        self.assertEqual(1, report["totals"]["skipped_unchanged"])
        self.assertEqual(1, report["totals"]["failed"])
        self.assertGreaterEqual(report["totals"]["stale_marked"], 1)
        self.assertTrue(report["evidence"]["has_cursor"])
        self.assertEqual("read_only_workspace_registry_gate_no_fetch_no_write", report["boundary"])

    def test_registry_gate_fails_when_required_evidence_is_missing(self) -> None:
        report = build_report(
            self.conn,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            min_runs=1,
            require_ingested=True,
        )

        self.assertFalse(report["ok"])
        self.assertIn("run_count_below_min:0<1", report["failures"])
        self.assertIn("missing_ingested_evidence", report["failures"])

    def _start_run(self, filter_key: str) -> str:
        return start_workspace_ingestion_run(
            self.conn,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            query="",
            doc_types=["docx"],
            filters={"folder_walk_root": True},
            mode="controlled_workspace_ingestion_pilot",
            boundary="candidate_pipeline_only_with_registry_no_production_daemon_no_raw_event_embedding",
        )


if __name__ == "__main__":
    unittest.main()
