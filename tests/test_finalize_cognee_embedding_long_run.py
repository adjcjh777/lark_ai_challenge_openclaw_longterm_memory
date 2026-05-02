from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.finalize_cognee_embedding_long_run import finalize_cognee_embedding_long_run


class FinalizeCogneeEmbeddingLongRunTest(unittest.TestCase):
    def test_reports_not_ready_without_writing_evidence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cognee_finalize_") as temp_dir:
            root = Path(temp_dir)
            curated = _write_json(root / "curated.json", _curated_sync_report())
            readback = _write_json(root / "readback.json", _readback_report())
            samples = _write_samples(
                root / "samples.ndjson",
                [
                    _embedding_sample("2026-05-01T00:00:00+00:00"),
                    _embedding_sample("2026-05-01T12:00:00+00:00"),
                ],
            )
            output = root / "evidence.json"

            result = finalize_cognee_embedding_long_run(
                curated_sync_report_path=curated,
                persistent_readback_report_path=readback,
                embedding_sample_log=samples,
                pid_file=None,
                service_unit="openclaw-local-cognee-sampler",
                oncall_owner="memory-owner",
                evidence_refs=[],
                output_path=output,
            )

            self.assertFalse(result["ok"])
            self.assertEqual("cognee_sampler_not_ready", result["reason"])
            self.assertFalse(output.exists())
            self.assertEqual(12.0, result["sampler_status"]["embedding_window_hours"])

    def test_writes_completion_audit_evidence_when_sampler_ready(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cognee_finalize_") as temp_dir:
            root = Path(temp_dir)
            curated = _write_json(root / "curated.json", _curated_sync_report())
            readback = _write_json(root / "readback.json", _readback_report())
            samples = _write_samples(
                root / "samples.ndjson",
                [
                    _embedding_sample("2026-05-01T00:00:00+00:00"),
                    _embedding_sample("2026-05-01T12:30:00+00:00"),
                    _embedding_sample("2026-05-02T00:30:00+00:00"),
                ],
            )
            output = root / "evidence.json"

            result = finalize_cognee_embedding_long_run(
                curated_sync_report_path=curated,
                persistent_readback_report_path=readback,
                embedding_sample_log=samples,
                pid_file=None,
                service_unit="openclaw-local-cognee-sampler",
                oncall_owner="memory-owner",
                evidence_refs=["ops/cognee-long-run"],
                output_path=output,
            )

            self.assertTrue(result["ok"], result)
            self.assertEqual("cognee_long_run_evidence_ready", result["reason"])
            evidence = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("pass", evidence["cognee_sync"]["status"])
            self.assertTrue(evidence["persistence"]["store_reopened"])
            self.assertGreaterEqual(evidence["embedding_service"]["window_hours"], 24)


def _curated_sync_report() -> dict[str, object]:
    return {
        "ok": True,
        "dataset_name": "copilot_project_feishu_ai_challenge",
        "memory_id": "mem_cognee",
        "data_root": "/tmp/cognee/data",
        "system_root": "/tmp/cognee/system",
        "cognee_sync": {"status": "pass", "fallback": None},
    }


def _readback_report() -> dict[str, object]:
    return {
        "ok": True,
        "matched_memory": True,
        "search_result_count": 1,
        "checks": {
            "store_reopened": {"status": "pass"},
            "reopened_search_ok": {"status": "pass"},
        },
    }


def _embedding_sample(sampled_at: str) -> dict[str, object]:
    return {
        "ok": True,
        "status": "ready",
        "sampled_at": sampled_at,
        "model": "ollama/qwen3-embedding:0.6b-fp16",
        "expected_dimensions": 1024,
        "actual_dimensions": 1024,
    }


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_samples(path: Path, samples: list[dict[str, object]]) -> Path:
    path.write_text("\n".join(json.dumps(sample) for sample in samples), encoding="utf-8")
    return path


if __name__ == "__main__":
    unittest.main()
