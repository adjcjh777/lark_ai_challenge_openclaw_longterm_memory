from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.collect_cognee_embedding_long_run_evidence import (
    collect_cognee_embedding_long_run_evidence,
    _parse_json_object,
    _read_embedding_samples,
)


class CogneeEmbeddingLongRunEvidenceTest(unittest.TestCase):
    def test_collects_completion_audit_evidence_for_full_window(self) -> None:
        result = collect_cognee_embedding_long_run_evidence(
            curated_sync_report={
                "dataset_name": "copilot_project_feishu_ai_challenge",
                "memory_id": "mem_cognee",
                "data_root": "/var/lib/cognee/data",
                "system_root": "/var/lib/cognee/system",
                "cognee_sync": {"status": "pass", "fallback": None},
            },
            embedding_samples=[
                _embedding_sample("2026-05-01T00:00:00+00:00"),
                _embedding_sample("2026-05-01T12:30:00+00:00"),
                _embedding_sample("2026-05-02T00:30:00+00:00"),
            ],
            store_reopened=False,
            reopened_search_ok=False,
            persistent_readback_report={
                "ok": True,
                "matched_memory": True,
                "search_result_count": 2,
                "checks": {
                    "store_reopened": {"status": "pass"},
                    "reopened_search_ok": {"status": "pass"},
                },
            },
            service_unit="cognee-embedding.service",
            oncall_owner="memory-copilot-oncall",
            evidence_refs=["ops/cognee-embedding-long-run-20260502"],
        )

        self.assertTrue(result["ok"], result)
        self.assertEqual([], result["failed_checks"])
        evidence = result["completion_audit_evidence"]
        self.assertEqual("pass", evidence["cognee_sync"]["status"])
        self.assertTrue(evidence["persistence"]["store_reopened"])
        self.assertTrue(evidence["persistence"]["reopened_search_ok"])
        self.assertTrue(evidence["persistence"]["readback_report_ok"])
        self.assertEqual(2, evidence["persistence"]["readback_result_count"])
        self.assertEqual(3, evidence["embedding_service"]["healthcheck_sample_count"])
        self.assertGreaterEqual(evidence["embedding_service"]["window_hours"], 24)

    def test_fails_without_reopen_and_long_window(self) -> None:
        result = collect_cognee_embedding_long_run_evidence(
            curated_sync_report={"cognee_sync": {"status": "pass", "fallback": None}},
            embedding_samples=[_embedding_sample("2026-05-01T00:00:00+00:00")],
            store_reopened=False,
            reopened_search_ok=False,
            service_unit="",
            oncall_owner="",
            evidence_refs=[],
        )

        self.assertFalse(result["ok"])
        self.assertIn("persistent_store_reopened", result["failed_checks"])
        self.assertIn("reopened_search_ok", result["failed_checks"])
        self.assertIn("embedding_successful_samples", result["failed_checks"])
        self.assertIn("embedding_window", result["failed_checks"])
        self.assertIn("ops_metadata_present", result["failed_checks"])

    def test_curated_sync_fallback_does_not_pass(self) -> None:
        result = collect_cognee_embedding_long_run_evidence(
            curated_sync_report={"cognee_sync": {"status": "fallback", "fallback": {"reason": "sdk_missing"}}},
            embedding_samples=[
                _embedding_sample("2026-05-01T00:00:00+00:00"),
                _embedding_sample("2026-05-01T12:00:00+00:00"),
                _embedding_sample("2026-05-02T01:00:00+00:00"),
            ],
            store_reopened=True,
            reopened_search_ok=True,
            service_unit="cognee-embedding.service",
            oncall_owner="memory-copilot-oncall",
            evidence_refs=["ops/cognee-long-run"],
        )

        self.assertFalse(result["ok"])
        self.assertIn("curated_sync_pass", result["failed_checks"])

    def test_reads_embedding_samples_from_ndjson(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cognee_embedding_long_run_") as temp_dir:
            path = Path(temp_dir) / "samples.ndjson"
            path.write_text(
                "\n".join(
                    [
                        json.dumps(_embedding_sample("2026-05-01T00:00:00+00:00")),
                        json.dumps(_embedding_sample("2026-05-01T01:00:00+00:00")),
                    ]
                ),
                encoding="utf-8",
            )

            samples = list(_read_embedding_samples(path))

        self.assertEqual(2, len(samples))
        self.assertEqual("2026-05-01T00:00:00+00:00", samples[0]["sampled_at"])

    def test_reads_noisy_curated_sync_stdout_before_json(self) -> None:
        parsed = _parse_json_object(
            "User abc has registered.\n"
            "Provider List: https://docs.litellm.ai/docs/providers\n"
            "{\"ok\": true, \"cognee_sync\": {\"status\": \"pass\", \"fallback\": null}}\n"
        )

        self.assertEqual({"ok": True, "cognee_sync": {"status": "pass", "fallback": None}}, parsed)


def _embedding_sample(sampled_at: str) -> dict[str, object]:
    return {
        "ok": True,
        "status": "ready",
        "check_mode": "live_embedding",
        "sampled_at": sampled_at,
        "model": "ollama/qwen3-embedding:0.6b-fp16",
        "expected_dimensions": 1024,
        "actual_dimensions": 1024,
    }


if __name__ == "__main__":
    unittest.main()
