from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from scripts.collect_workspace_source_coverage_evidence import (
    collect_workspace_source_coverage_evidence,
)


class WorkspaceSourceCoverageEvidenceTest(unittest.TestCase):
    def test_collects_complete_source_coverage_patch(self) -> None:
        result = collect_workspace_source_coverage_evidence(
            reports=[
                _ingest_report(
                    [
                        ("docx", "document_feishu"),
                        ("doc", "lark_doc"),
                        ("sheet", "lark_sheet"),
                        ("bitable", "lark_bitable"),
                        ("wiki", "document_feishu"),
                    ]
                ),
                _same_conclusion_report(),
                _mixed_source_conflict_report(),
            ],
            evidence_refs=["logs/workspace-productized/source-coverage-redacted"],
        )

        self.assertTrue(result["ok"], result["failed_checks"])
        patch = result["production_manifest_patch"]["source_coverage"]
        self.assertEqual(2, patch["source_types"]["document_feishu"]["organic_sample_count"])
        self.assertEqual(1, patch["source_types"]["lark_doc"]["organic_sample_count"])
        self.assertEqual(1, patch["source_types"]["lark_sheet"]["organic_sample_count"])
        self.assertEqual(1, patch["source_types"]["lark_bitable"]["organic_sample_count"])
        self.assertEqual(1, patch["source_types"]["wiki"]["organic_sample_count"])
        self.assertTrue(patch["same_conclusion_across_chat_and_workspace"])
        self.assertTrue(patch["conflict_negative_proven"])
        self.assertFalse(result["production_ready_claim"])

    def test_blocks_without_same_conclusion_conflict_or_refs(self) -> None:
        result = collect_workspace_source_coverage_evidence(
            reports=[_ingest_report([("docx", "document_feishu")])],
            evidence_refs=[],
        )

        self.assertFalse(result["ok"])
        self.assertIn("same_conclusion_across_chat_and_workspace", result["failed_checks"])
        self.assertIn("conflict_negative_proven", result["failed_checks"])
        self.assertIn("evidence_refs_present", result["failed_checks"])
        self.assertIn("lark_sheet_organic_sample_count", result["failed_checks"])

    def test_cli_writes_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="workspace_source_coverage_") as temp_dir:
            root = Path(temp_dir)
            report = root / "coverage.json"
            output = root / "source-coverage-evidence.json"
            report.write_text(
                json.dumps(
                    {
                        "ok": True,
                        "status": "pass",
                        "source_type_counts": {
                            "document_feishu": 1,
                            "lark_doc": 1,
                            "lark_sheet": 1,
                            "lark_bitable": 1,
                            "wiki": 1,
                        },
                        "summary": {
                            "same_fact_match_count": 1,
                        },
                        "checks": {
                            "bitable_conflict_candidate_created": True,
                        },
                    }
                ),
                encoding="utf-8",
            )

            from scripts.collect_workspace_source_coverage_evidence import main
            import sys
            from unittest.mock import patch

            with patch.object(
                sys,
                "argv",
                [
                    "collect_workspace_source_coverage_evidence.py",
                    "--evidence-report",
                    str(report),
                    "--evidence-ref",
                    "logs/workspace-productized/source-coverage-redacted",
                    "--output",
                    str(output),
                    "--json",
                ],
            ), redirect_stdout(StringIO()):
                exit_code = main()

            self.assertEqual(0, exit_code)
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertTrue(written["ok"])

    def test_rejects_placeholder_or_secret_like_evidence_refs(self) -> None:
        result = collect_workspace_source_coverage_evidence(
            reports=[
                {
                    "ok": True,
                    "status": "pass",
                    "source_type_counts": {
                        "document_feishu": 1,
                        "lark_doc": 1,
                        "lark_sheet": 1,
                        "lark_bitable": 1,
                        "wiki": 1,
                    },
                    "summary": {"same_fact_match_count": 1},
                    "checks": {"bitable_conflict_candidate_created": True},
                }
            ],
            evidence_refs=["Bearer leaked-token"],
        )

        self.assertFalse(result["ok"])
        self.assertIn("evidence_refs_present", result["failed_checks"])


def _ingest_report(items: list[tuple[str, str]]) -> dict[str, object]:
    return {
        "ok": True,
        "status": "pass",
        "mode": "controlled_workspace_ingestion_pilot",
        "results": [
            {
                "ok": True,
                "resource": {"resource_type": resource_type},
                "source": {"source_type": source_type},
            }
            for resource_type, source_type in items
        ],
    }


def _same_conclusion_report() -> dict[str, object]:
    return {
        "ok": True,
        "status": "pass",
        "mode": "real_same_conclusion_temp_db",
        "summary": {"matching_resource_source_count": 1},
        "active_evidence_source_types": ["feishu_message", "lark_sheet"],
    }


def _mixed_source_conflict_report() -> dict[str, object]:
    return {
        "ok": True,
        "boundary": "local_temp_sqlite_mixed_source_gate",
        "checks": {"bitable_conflict_candidate_created": True},
        "evidence": {"conflict_evidence_source_types": ["lark_bitable"]},
    }


if __name__ == "__main__":
    unittest.main()
