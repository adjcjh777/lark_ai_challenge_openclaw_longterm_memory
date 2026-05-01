from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memory_engine.copilot.knowledge_site import export_knowledge_site
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository, now_ms


class CopilotKnowledgeSiteTest(unittest.TestCase):
    def test_exports_static_wiki_and_graph_site_bundle(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_site_", suffix=".sqlite") as db_tmp:
            conn = connect(db_tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(
                "project:admin_demo",
                "后台服务默认只绑定 127.0.0.1，app_secret=demo-secret 不能外泄。",
                source_type="unit_test",
            )
            repo.add_candidate(
                "project:admin_demo",
                "候选记忆必须先 review 再 active。",
                source_type="unit_test",
                source_id="candidate_source",
                document_token="candidate_doc",
                document_title="Candidate Review",
                quote="候选记忆必须先 review 再 active。",
            )
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
                        "Secret test chat",
                        "team",
                        "active",
                        json.dumps({"note": "token=demo-secret"}),
                        event_time,
                        event_time,
                        1,
                    ),
                )
            conn.close()

            with tempfile.TemporaryDirectory(prefix="copilot_site_out_") as out_tmp:
                result = export_knowledge_site(
                    db_path=db_tmp.name,
                    output_dir=out_tmp,
                    scope="project:admin_demo",
                )
                output_dir = Path(result["output_dir"])

                self.assertTrue(result["ok"])
                self.assertEqual(str(output_dir / "index.html"), result["entrypoint"])
                self.assertEqual("index.html", result["manifest"]["entrypoint"])
                self.assertTrue((output_dir / "index.html").exists())
                self.assertTrue((output_dir / "data" / "manifest.json").exists())
                self.assertTrue((output_dir / "data" / "wiki.json").exists())
                self.assertTrue((output_dir / "data" / "graph.json").exists())
                self.assertTrue((output_dir / "data" / "graph-quality.json").exists())
                self.assertTrue((output_dir / "wiki" / "project_admin_demo.md").exists())

                index_html = (output_dir / "index.html").read_text(encoding="utf-8")
                self.assertIn("Feishu Memory Copilot Knowledge Site", index_html)
                self.assertIn("Created By", index_html)
                self.assertIn("https://deerflow.tech", index_html)
                self.assertIn('data-design-system="copilot-static-knowledge-site/v1"', index_html)
                self.assertIn("--radius-panel", index_html)
                self.assertIn("--panel-muted", index_html)
                self.assertIn("Knowledge Graph", index_html)
                self.assertIn('id="graphDetail"', index_html)
                self.assertIn('id="relationshipFocus"', index_html)
                self.assertIn("data-node-id", index_html)
                self.assertIn("data-edge-id", index_html)
                self.assertIn("Relationship Focus", index_html)
                self.assertIn("Evidence paths", index_html)
                self.assertIn("Graph quality", index_html)
                self.assertIn("compiled graph", index_html)
                self.assertIn("Related edges", index_html)
                self.assertIn("detail-grid", index_html)
                self.assertIn("window.COPILOT_KNOWLEDGE_SITE", index_html)
                self.assertNotIn("demo-secret", index_html)
                self.assertIn("app_secret=[REDACTED]", index_html)
                self.assertIn("token=[REDACTED]", index_html)

                markdown = (output_dir / "wiki" / "project_admin_demo.md").read_text(encoding="utf-8")
                self.assertIn("# 项目记忆卡册：project:admin_demo", markdown)
                self.assertNotIn("demo-secret", markdown)

                graph = json.loads((output_dir / "data" / "graph.json").read_text(encoding="utf-8"))
                self.assertIn("memory", {node["node_type"] for node in graph["nodes"]})
                self.assertIn("grounded_by", {edge["edge_type"] for edge in graph["edges"]})
                self.assertNotIn("demo-secret", json.dumps(graph, ensure_ascii=False))

                graph_quality = json.loads((output_dir / "data" / "graph-quality.json").read_text(encoding="utf-8"))
                self.assertIn(graph_quality["status"], {"pass", "fail"})
                self.assertEqual("pass", graph_quality["checks"]["compiled_memory_graph"]["status"])
                self.assertNotIn("demo-secret", json.dumps(graph_quality, ensure_ascii=False))

                manifest = json.loads((output_dir / "data" / "manifest.json").read_text(encoding="utf-8"))
                self.assertTrue(manifest["read_only"])
                self.assertIn("no production deployment", manifest["boundary"])
                self.assertEqual(graph_quality["status"], manifest["graph_quality_status"])


if __name__ == "__main__":
    unittest.main()
