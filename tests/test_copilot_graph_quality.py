from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from memory_engine.db import init_db
from memory_engine.repository import now_ms
from scripts.check_copilot_graph_quality import run_graph_quality_check


class CopilotGraphQualityCheckTest(unittest.TestCase):
    def test_temp_seeded_graph_quality_passes(self) -> None:
        report = run_graph_quality_check()

        self.assertTrue(report["ok"], report)
        self.assertEqual("pass", report["checks"]["compiled_memory_graph"]["status"])
        self.assertEqual("pass", report["checks"]["edge_endpoints"]["status"])
        self.assertIn("grounded_by", report["summary"]["edges_by_type"])

    def test_graph_quality_detects_secret_like_metadata(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_graph_quality_", suffix=".sqlite") as tmp:
            conn = sqlite3.connect(tmp.name)
            conn.row_factory = sqlite3.Row
            init_db(conn)
            event_time = now_ms()
            with conn:
                conn.execute(
                    """
                    INSERT INTO knowledge_graph_nodes (
                      id, tenant_id, organization_id, node_type, node_key, label,
                      visibility_policy, status, metadata_json, first_seen_at,
                      last_seen_at, observation_count
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "kgn_secret",
                        "tenant:demo",
                        "org:demo",
                        "feishu_chat",
                        "chat_secret",
                        "Secret Chat",
                        "team",
                        "active",
                        '{"note":"app_secret=demo-secret"}',
                        event_time,
                        event_time,
                        1,
                    ),
                )
            conn.close()

            report = run_graph_quality_check(db_path=Path(tmp.name), seed_demo_data=True)

        self.assertFalse(report["ok"], report)
        self.assertEqual("fail", report["checks"]["secret_redaction"]["status"])
        self.assertIn("app_secret=", report["checks"]["secret_redaction"]["forbidden_substrings_found"])

    def test_graph_quality_detects_missing_edge_endpoint(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_graph_quality_", suffix=".sqlite") as tmp:
            conn = sqlite3.connect(tmp.name)
            conn.row_factory = sqlite3.Row
            init_db(conn)
            conn.commit()
            conn.execute("PRAGMA foreign_keys = OFF")
            event_time = now_ms()
            with conn:
                conn.execute(
                    """
                    INSERT INTO knowledge_graph_nodes (
                      id, tenant_id, organization_id, node_type, node_key, label,
                      visibility_policy, status, metadata_json, first_seen_at,
                      last_seen_at, observation_count
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "kgn_present",
                        "tenant:demo",
                        "org:demo",
                        "feishu_chat",
                        "chat_present",
                        "Present Chat",
                        "team",
                        "active",
                        "{}",
                        event_time,
                        event_time,
                        1,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO knowledge_graph_edges (
                      id, tenant_id, organization_id, source_node_id, target_node_id,
                      edge_type, metadata_json, first_seen_at, last_seen_at, observation_count
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "kge_broken",
                        "tenant:demo",
                        "org:demo",
                        "kgn_missing",
                        "kgn_present",
                        "member_of",
                        "{}",
                        event_time,
                        event_time,
                        1,
                    ),
                )
            conn.close()

            report = run_graph_quality_check(
                db_path=Path(tmp.name),
                seed_demo_data=True,
                max_orphan_ratio=1.0,
            )

        self.assertFalse(report["ok"], report)
        self.assertEqual("fail", report["checks"]["edge_endpoints"]["status"])
        self.assertIn("kgn_missing", report["checks"]["edge_endpoints"]["missing_endpoints"])


if __name__ == "__main__":
    unittest.main()
