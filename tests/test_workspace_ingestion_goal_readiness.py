from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memory_engine.feishu_workspace_fetcher import WorkspaceResource
from scripts.check_workspace_ingestion_goal_readiness import (
    build_readiness_report,
    collect_project_sheet_resources,
    sheet_resources_from_specs,
)


class WorkspaceIngestionGoalReadinessTest(unittest.TestCase):
    def test_goal_complete_when_static_and_real_evidence_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._project_root(Path(temp_dir))
            report = build_readiness_report(
                project_root=root,
                sheet_report={"ok": True, "summary": {"eligible_project_normal_sheet_count": 1}},
                same_conclusion_report={"ok": True, "summary": {"same_fact_match_count": 1}},
            )

        self.assertTrue(report["ok"], report["failures"])
        self.assertTrue(report["goal_complete"])
        self.assertEqual([], report["blockers"])

    def test_goal_blocked_when_real_evidence_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = self._project_root(Path(temp_dir))
            report = build_readiness_report(
                project_root=root,
                sheet_report={"ok": False, "summary": {"eligible_project_normal_sheet_count": 0}},
                same_conclusion_report={"ok": False, "summary": {"same_fact_match_count": 0}},
            )

        self.assertFalse(report["ok"])
        self.assertFalse(report["goal_complete"])
        self.assertIn("project_enterprise_normal_sheet_evidence", report["failures"])
        self.assertIn("real_same_conclusion_corroboration_evidence", report["failures"])
        self.assertEqual(2, len(report["blockers"]))

    def test_static_artifact_gaps_are_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docs/productization").mkdir(parents=True)
            report = build_readiness_report(
                project_root=root,
                sheet_report={"ok": True, "summary": {"eligible_project_normal_sheet_count": 1}},
                same_conclusion_report={"ok": True, "summary": {"same_fact_match_count": 1}},
            )

        self.assertFalse(report["ok"])
        self.assertIn("lark_cli_first_architecture_decision", report["failures"])

    def test_sheet_specs_are_reused_from_resource_inputs(self) -> None:
        specs = sheet_resources_from_specs(
            resources=[
                "docx:doc_1:Project doc",
                "sheet:sht_1:Project Sheet",
                "bitable:base_1:Project Base",
            ],
            sheet_resources=["sheet:sht_2:Metrics Sheet", "sheet:sht_1:Project Sheet"],
        )

        self.assertEqual(["sheet:sht_2:Metrics Sheet", "sheet:sht_1:Project Sheet"], specs)

    def test_project_sheet_resources_include_folder_and_wiki_walks(self) -> None:
        with (
            patch(
                "scripts.check_workspace_ingestion_goal_readiness.discover_workspace_resources",
                return_value=[WorkspaceResource(resource_type="sheet", token="sht_search", title="Search Sheet")],
            ) as search,
            patch(
                "scripts.check_workspace_ingestion_goal_readiness.discover_drive_folder_resources",
                return_value=[WorkspaceResource(resource_type="sheet", token="sht_folder", title="Folder Sheet")],
            ) as folder,
            patch(
                "scripts.check_workspace_ingestion_goal_readiness.discover_wiki_space_resources",
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
        search.assert_called_once()
        folder.assert_called_once()
        wiki.assert_called_once()

    def _project_root(self, root: Path) -> Path:
        productization = root / "docs/productization"
        productization.mkdir(parents=True)
        (productization / "workspace-ingestion-architecture-adr.md").write_text(
            "\n".join(
                [
                    "lark-cli first",
                    "native Feishu OpenAPI",
                    "Remember candidates when the source contains",
                    "Do not remember",
                    "FeishuIngestionSource",
                    "CopilotService",
                    "candidate pipeline",
                    "one governed ledger",
                    "Evidence rows",
                    "latency gate",
                    "bounded",
                ]
            ),
            encoding="utf-8",
        )
        (productization / "document-writing-style-guide-opus-4-6.md").write_text(
            "Opus 4.6 language boundary; do not use 4.7.",
            encoding="utf-8",
        )
        return root


if __name__ == "__main__":
    unittest.main()
