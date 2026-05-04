from __future__ import annotations

import unittest
from unittest.mock import patch

from memory_engine.feishu_workspace_fetcher import WorkspaceResource
from scripts.check_workspace_project_sheet_evidence_gate import (
    build_project_sheet_evidence_report,
    collect_project_sheet_resources,
)


class WorkspaceProjectSheetEvidenceGateTest(unittest.TestCase):
    def test_report_passes_when_project_normal_sheet_exists(self) -> None:
        report = build_project_sheet_evidence_report(
            candidates=[
                {
                    "title": "飞书挑战赛知识表",
                    "is_normal_sheet": True,
                    "is_sheet_backed_bitable_only": False,
                    "is_cross_tenant": False,
                    "eligible_project_normal_sheet": True,
                }
            ],
            inspection_failures=[],
            min_eligible=1,
            queries=["飞书挑战赛"],
            project_keywords=["飞书挑战赛"],
            allow_cross_tenant=False,
        )

        self.assertTrue(report["ok"], report["failures"])
        self.assertEqual("pass", report["status"])
        self.assertEqual(1, report["summary"]["eligible_project_normal_sheet_count"])

    def test_report_fails_for_sheet_backed_bitable_only(self) -> None:
        report = build_project_sheet_evidence_report(
            candidates=[
                {
                    "title": "飞书挑战赛任务跟进看板",
                    "is_normal_sheet": False,
                    "is_sheet_backed_bitable_only": True,
                    "is_cross_tenant": False,
                    "eligible_project_normal_sheet": False,
                }
            ],
            inspection_failures=[],
            min_eligible=1,
            queries=["飞书挑战赛"],
            project_keywords=["飞书挑战赛"],
            allow_cross_tenant=False,
        )

        self.assertFalse(report["ok"])
        self.assertIn("has_eligible_project_normal_sheet", report["failures"])
        self.assertEqual(1, report["summary"]["sheet_backed_bitable_only_count"])

    def test_report_fails_for_cross_tenant_candidate_without_override(self) -> None:
        report = build_project_sheet_evidence_report(
            candidates=[
                {
                    "title": "外部项目表",
                    "is_normal_sheet": True,
                    "is_sheet_backed_bitable_only": False,
                    "is_cross_tenant": True,
                    "eligible_project_normal_sheet": False,
                }
            ],
            inspection_failures=[],
            min_eligible=1,
            queries=[""],
            project_keywords=["项目"],
            allow_cross_tenant=False,
        )

        self.assertFalse(report["ok"])
        self.assertEqual(1, report["summary"]["cross_tenant_candidate_count"])

    def test_collect_resources_supports_search_folder_and_wiki_walks(self) -> None:
        with (
            patch(
                "scripts.check_workspace_project_sheet_evidence_gate.discover_workspace_resources",
                return_value=[WorkspaceResource(resource_type="sheet", token="sht_search", title="Search Sheet")],
            ) as search,
            patch(
                "scripts.check_workspace_project_sheet_evidence_gate.discover_drive_folder_resources",
                return_value=[WorkspaceResource(resource_type="sheet", token="sht_folder", title="Folder Sheet")],
            ) as folder,
            patch(
                "scripts.check_workspace_project_sheet_evidence_gate.discover_wiki_space_resources",
                return_value=[WorkspaceResource(resource_type="sheet", token="sht_wiki", title="Wiki Sheet")],
            ) as wiki,
        ):
            resources = collect_project_sheet_resources(
                queries=["OpenClaw"],
                explicit_resources=["sheet:sht_explicit:Explicit Sheet"],
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

        self.assertEqual(
            ["sht_search", "sht_explicit", "sht_folder", "sht_wiki"],
            [resource.token for resource in resources],
        )
        search.assert_called_once_with(
            query="OpenClaw",
            doc_types=["sheet"],
            limit=20,
            max_pages=2,
            opened_since="365d",
            edited_since=None,
            created_since=None,
            mine=False,
            sort="edit_time",
            profile=None,
            as_identity="user",
        )
        folder.assert_called_once()
        wiki.assert_called_once()


if __name__ == "__main__":
    unittest.main()
