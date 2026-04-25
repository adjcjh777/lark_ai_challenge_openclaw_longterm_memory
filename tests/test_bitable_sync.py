from __future__ import annotations

import unittest
from pathlib import Path

from memory_engine.bitable_sync import collect_sync_payload, setup_commands, sync_payload
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository
from temp_utils import WorkspaceTempDir


class BitableSyncTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = WorkspaceTempDir("bitable")
        self.db_path = Path(self.temp_dir.name) / "memory.sqlite"
        self.conn = connect(self.db_path)
        init_db(self.conn)
        self.repo = MemoryRepository(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    def test_collects_ledger_and_version_rows(self) -> None:
        created = self.repo.remember(
            "project:feishu_ai_challenge",
            "生产部署必须加 --canary --region cn-shanghai",
            source_type="test",
            source_id="msg_1",
        )
        self.repo.remember(
            "project:feishu_ai_challenge",
            "不对，生产部署 region 改成 ap-shanghai",
            source_type="test",
            source_id="msg_2",
        )

        payload = collect_sync_payload(self.conn)

        ledger = payload["tables"]["ledger"]
        versions = payload["tables"]["versions"]
        self.assertEqual(1, len(ledger["rows"]))
        self.assertEqual(2, len(versions["rows"]))
        self.assertEqual(created["memory_id"], ledger["rows"][0][ledger["fields"].index("memory_id")])
        self.assertEqual("active", ledger["rows"][0][ledger["fields"].index("status")])
        self.assertEqual(2, ledger["rows"][0][ledger["fields"].index("version")])

        statuses = {row[versions["fields"].index("status")] for row in versions["rows"]}
        self.assertEqual({"active", "superseded"}, statuses)

    def test_dry_run_returns_commands_without_lark_cli(self) -> None:
        self.repo.remember("project:feishu_ai_challenge", "生产部署必须加 --canary")
        payload = collect_sync_payload(self.conn)

        result = sync_payload(payload, setup_target(), dry_run=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertEqual({"ledger": 1, "versions": 1, "benchmark": 0}, result["tables"])
        self.assertEqual(2, len(result["commands"]))

    def test_benchmark_summary_row_can_be_included(self) -> None:
        benchmark_path = Path(self.temp_dir.name) / "benchmark.json"
        benchmark_path.write_text(
            '{"summary":{"case_count":3,"case_pass_rate":1.0,"conflict_accuracy":1.0,'
            '"stale_leakage_rate":0.0,"evidence_coverage":1.0,"avg_latency_ms":0.2}}',
            encoding="utf-8",
        )

        payload = collect_sync_payload(self.conn, benchmark_json=benchmark_path, benchmark_name="day1")
        benchmark = payload["tables"]["benchmark"]

        self.assertEqual(1, len(benchmark["rows"]))
        self.assertEqual("day1", benchmark["rows"][0][benchmark["fields"].index("benchmark_name")])
        self.assertEqual(3, benchmark["rows"][0][benchmark["fields"].index("case_count")])

    def test_scope_filter_limits_memory_rows(self) -> None:
        self.repo.remember("project:feishu_ai_challenge", "生产部署必须加 --canary")
        self.repo.remember("project:other", "周报优先发飞书文档")

        payload = collect_sync_payload(self.conn, scope="project:other")
        ledger = payload["tables"]["ledger"]
        versions = payload["tables"]["versions"]

        self.assertEqual(1, len(ledger["rows"]))
        self.assertEqual("project:other", ledger["rows"][0][ledger["fields"].index("scope")])
        self.assertEqual(1, len(versions["rows"]))
        self.assertEqual("project:other", versions["rows"][0][versions["fields"].index("scope")])


def setup_target():
    from memory_engine.bitable_sync import BitableTarget

    return BitableTarget(base_token="app_test")


if __name__ == "__main__":
    unittest.main()
