from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository, now_ms
from scripts.prepare_clean_demo_db import prepare_clean_demo_db


class CleanDemoDbTest(unittest.TestCase):
    def test_prepare_clean_demo_db_isolates_live_test_rows(self) -> None:
        with tempfile.TemporaryDirectory(prefix="clean_demo_db_test_") as temp_dir:
            temp_path = Path(temp_dir)
            source_db = temp_path / "live.sqlite"
            output_db = temp_path / "demo.sqlite"
            self._seed_live_noise(source_db)

            before_counts = self._counts(source_db)
            report = prepare_clean_demo_db(source_db=source_db, output_db=output_db)
            after_counts = self._counts(source_db)

            self.assertTrue(report["ok"])
            self.assertEqual(before_counts, after_counts)
            self.assertFalse(report["source_db_modified"])
            self.assertTrue(output_db.exists())
            self.assertEqual([], report["demo_replay"]["failed_steps"])
            self.assertFalse(report["demo_replay"]["production_feishu_write"])
            self.assertEqual({"demo_seed": 6}, report["output_counts"]["source_type_counts"])
            self.assertEqual(0, report["output_counts"]["feishu_group_policy_total"])
            self.assertEqual(4, report["output_counts"]["audit_total"])
            self.assertEqual(4, report["cleanliness"]["audit_events_after_replay"])
            self.assertIn("MEMORY_DB_PATH=", report["next_step"])

    def test_prepare_clean_demo_db_refuses_to_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory(prefix="clean_demo_db_test_") as temp_dir:
            temp_path = Path(temp_dir)
            source_db = temp_path / "live.sqlite"
            output_db = temp_path / "demo.sqlite"
            self._seed_live_noise(source_db)
            output_db.write_text("existing", encoding="utf-8")

            with self.assertRaises(ValueError):
                prepare_clean_demo_db(source_db=source_db, output_db=output_db)

            report = prepare_clean_demo_db(source_db=source_db, output_db=output_db, force=True)

            self.assertTrue(report["ok"])
            self.assertNotEqual(b"existing", output_db.read_bytes())

    def _seed_live_noise(self, db_path: Path) -> None:
        conn = connect(db_path)
        try:
            init_db(conn)
            repo = MemoryRepository(conn)
            candidate = repo.add_candidate(
                "project:feishu_ai_challenge",
                "测试 live 噪声：评委 demo 前不要展示这条。",
                source_type="feishu_message",
                source_id="live_test_msg_001",
                document_token=None,
                document_title=None,
                quote="测试 live 噪声：评委 demo 前不要展示这条。",
                created_by="live_tester",
            )
            ts = now_ms()
            with conn:
                conn.execute(
                    """
                    INSERT INTO feishu_group_policies (
                      id, tenant_id, organization_id, chat_id, scope, visibility_policy,
                      status, passive_memory_enabled, reviewer_open_ids, owner_open_ids,
                      notes, created_by, updated_by, created_at, updated_at, last_enabled_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "fgp_live_noise",
                        "tenant:demo",
                        "org:demo",
                        "oc_live_test_group",
                        "project:feishu_ai_challenge",
                        "team",
                        "active",
                        1,
                        json.dumps(["ou_live_reviewer"]),
                        json.dumps(["ou_live_owner"]),
                        "live test noise",
                        "ou_live_reviewer",
                        "ou_live_reviewer",
                        ts,
                        ts,
                        ts,
                    ),
                )
                repo.record_audit_event(
                    event_type="live_test_noise",
                    action="memory.create_candidate",
                    target_type="candidate",
                    target_id=candidate["memory_id"],
                    candidate_id=candidate["memory_id"],
                    actor_id="ou_live_reviewer",
                    scope="project:feishu_ai_challenge",
                    permission_decision="allow",
                    request_id="req_live_noise",
                    trace_id="trace_live_noise",
                    created_at=ts,
                )
        finally:
            conn.close()

    def _counts(self, db_path: Path) -> dict[str, int]:
        conn = sqlite3.connect(db_path)
        try:
            return {
                "memories": conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0],
                "raw_events": conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()[0],
                "audit": conn.execute("SELECT COUNT(*) FROM memory_audit_events").fetchone()[0],
                "group_policies": conn.execute("SELECT COUNT(*) FROM feishu_group_policies").fetchone()[0],
            }
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
