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
    get_workspace_discovery_cursor,
    mark_missing_sources_stale,
    record_workspace_discovery_cursor,
    record_discovered_resource,
    record_fetch_error,
    record_source_ingested,
    reset_workspace_discovery_cursor,
    resource_revision,
    start_workspace_ingestion_run,
)


SCOPE = "project:feishu_ai_challenge"
TENANT = "tenant:demo"
ORG = "org:demo"


class FeishuWorkspaceRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.conn = connect(Path(self.temp_dir.name) / "memory.sqlite")
        self.addCleanup(self.conn.close)
        init_db(self.conn)

    def test_filter_key_separates_explicit_resources_from_discovery_scan(self) -> None:
        discovery_only_key = discovery_filter_key(query="", doc_types=["bitable"])
        explicit_key = discovery_filter_key(
            query="",
            doc_types=["bitable"],
            explicit_resources=["bitable:app_1:任务看板"],
            skip_discovery=True,
        )

        self.assertNotEqual(discovery_only_key, explicit_key)

    def test_filter_key_separates_direct_folder_and_wiki_walks(self) -> None:
        search_key = discovery_filter_key(query="", doc_types=["docx"])
        folder_key = discovery_filter_key(
            query="",
            doc_types=["docx"],
            folder_walk_tokens=["fld_1"],
            walk_max_depth=2,
        )
        wiki_key = discovery_filter_key(
            query="",
            doc_types=["docx"],
            wiki_space_walk_ids=["my_library"],
            walk_max_depth=2,
        )

        self.assertNotEqual(search_key, folder_key)
        self.assertNotEqual(folder_key, wiki_key)

    def test_registry_skips_unchanged_resources_after_ingestion(self) -> None:
        filter_key = discovery_filter_key(query="", doc_types=["docx"], edited_since="30d")
        first_run = self._start_run(filter_key)
        resource = WorkspaceResource(
            resource_type="docx",
            token="doc_1",
            title="部署决策",
            raw={"revision": "r1"},
        )

        first_decision = record_discovered_resource(
            self.conn,
            resource=resource,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            run_id=first_run,
        )
        record_source_ingested(
            self.conn,
            source=FeishuIngestionSource(
                source_type="document_feishu",
                source_id="doc_1",
                title="部署决策",
                text="决定：上线窗口是周四。",
                actor_id="workspace_document_fetch",
            ),
            resource=resource,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            run_id=first_run,
            candidate_count=1,
            duplicate_count=0,
        )

        second_run = self._start_run(filter_key)
        second_decision = record_discovered_resource(
            self.conn,
            resource=resource,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            run_id=second_run,
        )

        self.assertTrue(first_decision.should_fetch)
        self.assertFalse(second_decision.should_fetch)
        self.assertEqual("unchanged_revision", second_decision.reason)

    def test_registry_uses_drive_result_meta_icon_info_version_as_revision(self) -> None:
        resource = WorkspaceResource(
            resource_type="docx",
            token="doc_1",
            title="部署决策",
            raw={
                "entity_type": "WIKI",
                "result_meta": {
                    "doc_types": "DOCX",
                    "icon_info": '{"type":0,"obj_type":22,"token":"doc_1","version":13}',
                },
            },
        )

        self.assertEqual("13", resource_revision(resource))

    def test_registry_uses_dict_icon_info_version_as_revision(self) -> None:
        resource = WorkspaceResource(
            resource_type="sheet",
            token="sht_1",
            title="项目规则",
            raw={"result_meta": {"icon_info": {"obj_type": 3, "token": "sht_1", "version": 538}}},
        )

        self.assertEqual("538", resource_revision(resource))

    def test_registry_fetches_unversioned_resources_every_time(self) -> None:
        filter_key = discovery_filter_key(query="", doc_types=["docx"])
        resource = WorkspaceResource(resource_type="docx", token="doc_1", title="部署决策")
        first_run = self._start_run(filter_key)
        second_run = self._start_run(filter_key)

        record_discovered_resource(
            self.conn,
            resource=resource,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            run_id=first_run,
        )
        decision = record_discovered_resource(
            self.conn,
            resource=resource,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            run_id=second_run,
        )

        self.assertTrue(decision.should_fetch)
        self.assertEqual("changed_or_unversioned", decision.reason)

    def test_registry_records_sheet_source_with_fingerprint(self) -> None:
        filter_key = discovery_filter_key(query="", doc_types=["sheet"])
        run_id = self._start_run(filter_key)
        resource = WorkspaceResource(resource_type="sheet", token="sht_1", title="项目规则")
        source = FeishuIngestionSource(
            source_type="lark_sheet",
            source_id="sht_1",
            title="项目规则 / 规则",
            text="决定：生产部署必须加审计。",
            actor_id="workspace_sheet_fetch",
            metadata={"sheet_token": "sht_1", "sheet_id": "sh_1"},
        )

        record_source_ingested(
            self.conn,
            source=source,
            resource=resource,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            run_id=run_id,
            candidate_count=1,
            duplicate_count=0,
        )
        row = self.conn.execute(
            """
            SELECT source_key, source_type, sheet_id, status, content_fingerprint
            FROM feishu_workspace_source_registry
            WHERE source_type = 'lark_sheet'
            """
        ).fetchone()

        self.assertEqual("source:lark_sheet:sht_1:sh_1", row["source_key"])
        self.assertEqual("sh_1", row["sheet_id"])
        self.assertEqual("ingested", row["status"])
        self.assertEqual(64, len(row["content_fingerprint"]))

    def test_missing_sources_can_be_marked_stale_for_same_filter_only(self) -> None:
        filter_key = discovery_filter_key(query="project", doc_types=["docx"])
        other_filter_key = discovery_filter_key(query="other", doc_types=["docx"])
        first_run = self._start_run(filter_key)
        other_run = self._start_run(other_filter_key)
        stale_run = self._start_run(filter_key)
        old_resource = WorkspaceResource(resource_type="docx", token="old_doc", title="旧文档")
        other_resource = WorkspaceResource(resource_type="docx", token="other_doc", title="其他文档")

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
            resource=other_resource,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=other_filter_key,
            run_id=other_run,
        )

        count = mark_missing_sources_stale(
            self.conn,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            run_id=stale_run,
        )
        statuses = {
            row["token"]: row["status"]
            for row in self.conn.execute("SELECT token, status FROM feishu_workspace_source_registry").fetchall()
        }

        self.assertEqual(1, count)
        self.assertEqual("stale", statuses["old_doc"])
        self.assertEqual("discovered", statuses["other_doc"])

    def test_fetch_permission_error_marks_registry_revoked(self) -> None:
        filter_key = discovery_filter_key(query="", doc_types=["docx"])
        run_id = self._start_run(filter_key)
        resource = WorkspaceResource(resource_type="docx", token="doc_1", title="部署决策")
        record_discovered_resource(
            self.conn,
            resource=resource,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            run_id=run_id,
        )

        record_fetch_error(
            self.conn,
            resource=resource,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            run_id=run_id,
            error_code="permission_denied",
            error_message="permission denied",
        )
        row = self.conn.execute(
            "SELECT status, revoked_at, error_code FROM feishu_workspace_source_registry WHERE token = 'doc_1'"
        ).fetchone()

        self.assertEqual("revoked", row["status"])
        self.assertGreater(row["revoked_at"], 0)
        self.assertEqual("permission_denied", row["error_code"])

    def test_finish_run_writes_summary_counts(self) -> None:
        filter_key = discovery_filter_key(query="", doc_types=["docx"])
        run_id = self._start_run(filter_key)

        finish_workspace_ingestion_run(
            self.conn,
            run_id=run_id,
            status="completed_with_errors",
            resource_count=3,
            fetched_count=2,
            ingested_count=1,
            skipped_unchanged_count=1,
            failed_count=1,
            stale_marked_count=0,
        )
        row = self.conn.execute(
            "SELECT status, resource_count, skipped_unchanged_count, failed_count FROM feishu_workspace_ingestion_runs"
        ).fetchone()

        self.assertEqual("completed_with_errors", row["status"])
        self.assertEqual(3, row["resource_count"])
        self.assertEqual(1, row["skipped_unchanged_count"])
        self.assertEqual(1, row["failed_count"])

    def test_discovery_cursor_records_active_and_completed_resume_state(self) -> None:
        filter_key = discovery_filter_key(query="", doc_types=["docx"])
        first_run = self._start_run(filter_key)

        active = record_workspace_discovery_cursor(
            self.conn,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            run_id=first_run,
            page_token="next_1",
            pages_seen=2,
            resource_count=40,
            filters={"opened_since": "30d"},
        )
        cursor = get_workspace_discovery_cursor(
            self.conn,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
        )

        self.assertEqual("active", active["status"])
        self.assertEqual("next_1", cursor["page_token"])
        self.assertEqual(2, cursor["page_count"])
        self.assertEqual(40, cursor["resource_count"])

        second_run = self._start_run(filter_key)
        completed = record_workspace_discovery_cursor(
            self.conn,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            run_id=second_run,
            page_token=None,
            pages_seen=1,
            resource_count=3,
            filters={"opened_since": "30d"},
        )
        cursor = get_workspace_discovery_cursor(
            self.conn,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
        )

        self.assertEqual("completed", completed["status"])
        self.assertIsNone(cursor["page_token"])
        self.assertEqual("completed", cursor["status"])
        self.assertEqual(3, cursor["page_count"])
        self.assertEqual(43, cursor["resource_count"])

    def test_discovery_cursor_can_be_reset_for_filter(self) -> None:
        filter_key = discovery_filter_key(query="", doc_types=["docx"])
        run_id = self._start_run(filter_key)
        record_workspace_discovery_cursor(
            self.conn,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            run_id=run_id,
            page_token="next_1",
            pages_seen=1,
            resource_count=1,
            filters={},
        )

        reset_workspace_discovery_cursor(
            self.conn,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
        )

        self.assertIsNone(
            get_workspace_discovery_cursor(
                self.conn,
                workspace_id=SCOPE,
                tenant_id=TENANT,
                organization_id=ORG,
                filter_key=filter_key,
            )
        )

    def _start_run(self, filter_key: str) -> str:
        return start_workspace_ingestion_run(
            self.conn,
            workspace_id=SCOPE,
            tenant_id=TENANT,
            organization_id=ORG,
            filter_key=filter_key,
            query="",
            doc_types=["docx"],
            filters={},
            mode="controlled_workspace_ingestion_pilot",
            boundary="test_boundary",
        )


if __name__ == "__main__":
    unittest.main()
