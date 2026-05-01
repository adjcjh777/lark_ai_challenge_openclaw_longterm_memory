from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_copilot_admin_design_system import run_design_system_check


class CopilotAdminDesignSystemTest(unittest.TestCase):
    def test_current_admin_and_static_site_pass_design_system_gate(self) -> None:
        report = run_design_system_check()

        self.assertTrue(report["ok"], report)
        self.assertEqual([], report["failed_checks"])
        self.assertEqual("pass", report["checks"]["admin"]["status"])
        self.assertEqual("pass", report["checks"]["static_site"]["status"])

    def test_design_system_gate_rejects_retired_palette_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="copilot_design_system_") as tmp:
            root = Path(tmp)
            admin_path = root / "memory_engine" / "copilot" / "admin.py"
            static_path = root / "memory_engine" / "copilot" / "knowledge_site.py"
            admin_path.parent.mkdir(parents=True)
            admin_path.write_text(
                """
                <body data-design-system="copilot-admin-ui/v1">
                :root {
                  --surface-muted: #f8fafc;
                  --surface-tint: #eef6f3;
                  --radius-control: 6px;
                  --radius-panel: 8px;
                  --space-2: 8px;
                  --space-3: 12px;
                  --space-4: 16px;
                  --warning-surface: #fff7ed;
                  --info-surface: #eff6ff;
                }
                .legacy { background: #fffdf8; }
                """,
                encoding="utf-8",
            )
            static_path.write_text(
                """
                <body data-design-system="copilot-static-knowledge-site/v1">
                :root {
                  --panel-muted: #f8fafc;
                  --radius-control: 6px;
                  --radius-panel: 8px;
                  --space-2: 8px;
                  --space-3: 12px;
                  --space-4: 16px;
                  --warning-surface: #fff7ed;
                  --info-surface: #eff6ff;
                }
                """,
                encoding="utf-8",
            )

            report = run_design_system_check(root=root)

        self.assertFalse(report["ok"], report)
        self.assertIn("admin", report["failed_checks"])
        self.assertIn("#fffdf8", report["checks"]["admin"]["retired_palette_hits"])


if __name__ == "__main__":
    unittest.main()
