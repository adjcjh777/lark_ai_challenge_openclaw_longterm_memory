from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from memory_engine.db import init_db
from scripts.export_copilot_admin_launch_evidence import (
    SCHEMA_VERSION,
    export_launch_evidence_bundle,
)


class CopilotAdminLaunchEvidenceTest(unittest.TestCase):
    def test_launch_evidence_bundle_exports_redacted_staging_artifacts(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_launch_evidence_", suffix=".sqlite") as db_tmp:
            conn = sqlite3.connect(db_tmp.name)
            conn.row_factory = sqlite3.Row
            init_db(conn)
            conn.close()
            with tempfile.TemporaryDirectory(prefix="copilot_launch_evidence.") as out_tmp:
                manifest = export_launch_evidence_bundle(
                    db_path=Path(db_tmp.name),
                    output_dir=Path(out_tmp),
                    scope="project:launch_evidence",
                    tenant_id="tenant:demo",
                    organization_id="org:demo",
                    audit_min_events=1,
                    seed_demo_data=True,
                )

                self.assertTrue(manifest["ok"], manifest)
                self.assertEqual(SCHEMA_VERSION, manifest["schema_version"])
                self.assertTrue(manifest["staging_ok"], manifest)
                self.assertFalse(manifest["goal_complete"], manifest)
                self.assertTrue(manifest["production_blocked"], manifest)
                self.assertEqual("pass", manifest["redaction"]["status"])

                output_dir = Path(out_tmp)
                expected_files = {
                    "manifest.json",
                    "summary.json",
                    "wiki.json",
                    "graph.json",
                    "graph-quality.json",
                    "audit.json",
                    "audit-readonly-gate.json",
                    "deploy-bundle.json",
                    "production-evidence.json",
                    "completion-audit.json",
                    "launch-readiness.json",
                }
                self.assertTrue(expected_files.issubset({path.name for path in output_dir.glob("*.json")}))
                serialized = "\n".join(path.read_text(encoding="utf-8") for path in output_dir.glob("*.json"))
                self.assertNotIn("demo-secret", serialized)
                self.assertIn("production_blockers", serialized)

                graph_quality = json.loads((output_dir / "graph-quality.json").read_text(encoding="utf-8"))
                self.assertTrue(graph_quality["ok"])
                audit_gate = json.loads((output_dir / "audit-readonly-gate.json").read_text(encoding="utf-8"))
                self.assertTrue(audit_gate["ok"])


if __name__ == "__main__":
    unittest.main()
