from __future__ import annotations

import unittest

from scripts.check_workspace_project_sheet_evidence_gate import build_project_sheet_evidence_report


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


if __name__ == "__main__":
    unittest.main()
