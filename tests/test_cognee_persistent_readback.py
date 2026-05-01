from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memory_engine.copilot.cognee_adapter import CogneeMemoryAdapter
from scripts.check_cognee_persistent_readback import read_curated_sync_report, verify_cognee_persistent_readback


class CogneePersistentReadbackTest(unittest.TestCase):
    def test_verifies_reopened_store_with_matching_memory_id(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cognee_readback_") as temp_dir:
            root = Path(temp_dir)
            data_root = root / "data"
            system_root = root / "system"
            data_root.mkdir()
            system_root.mkdir()
            result = verify_cognee_persistent_readback(
                curated_sync_report={
                    "ok": True,
                    "scope": "project:feishu_ai_challenge",
                    "dataset_name": "feishu_memory_copilot_project_feishu_ai_challenge",
                    "memory_id": "mem_readback",
                    "data_root": str(data_root),
                    "system_root": str(system_root),
                },
                adapter_factory=lambda: CogneeMemoryAdapter(client=_SearchClient()),
            )

        self.assertTrue(result["ok"], result)
        self.assertEqual([], result["failed_checks"])
        self.assertEqual("pass", result["checks"]["store_reopened"]["status"])
        self.assertEqual("pass", result["checks"]["reopened_search_ok"]["status"])
        self.assertTrue(result["matched_memory"])

    def test_fails_when_store_roots_are_missing(self) -> None:
        result = verify_cognee_persistent_readback(
            curated_sync_report={
                "ok": True,
                "memory_id": "mem_missing",
                "data_root": "/tmp/not-a-real-cognee-data-root",
                "system_root": "/tmp/not-a-real-cognee-system-root",
            },
            adapter_factory=lambda: CogneeMemoryAdapter(client=_SearchClient()),
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("data_root_exists", result["failed_checks"])
        self.assertIn("system_root_exists", result["failed_checks"])
        self.assertIn("reopened_search_ok", result["failed_checks"])

    def test_reads_noisy_curated_sync_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cognee_readback_") as temp_dir:
            path = Path(temp_dir) / "report.json"
            path.write_text(
                "Pipeline loaded.\n"
                + json.dumps({"ok": True, "memory_id": "mem_noise", "data_root": "/tmp/data"}),
                encoding="utf-8",
            )

            report = read_curated_sync_report(path)

        self.assertEqual("mem_noise", report["memory_id"])


class _SearchClient:
    def search(self, *_args, **_kwargs):
        return [
            {
                "memory_id": "mem_readback",
                "current_value": "memory_id: mem_readback\nCognee curated sync gate readback ok",
                "score": 0.91,
                "metadata": {"memory_id": "mem_readback", "status": "active"},
            }
        ]


if __name__ == "__main__":
    unittest.main()
