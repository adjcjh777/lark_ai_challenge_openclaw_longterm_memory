from __future__ import annotations

import unittest
from pathlib import Path

from scripts.check_copilot_admin_ui_smoke import _NODE_SMOKE_SCRIPT

ROOT = Path(__file__).resolve().parents[1]


class CopilotAdminUiSmokeScriptTest(unittest.TestCase):
    def test_ui_smoke_includes_pixel_integrity_gate(self) -> None:
        self.assertIn("visual_pixel_integrity", _NODE_SMOKE_SCRIPT)
        self.assertIn("analyzePng", _NODE_SMOKE_SCRIPT)
        self.assertIn("unique_colors", _NODE_SMOKE_SCRIPT)
        self.assertIn("dominant_color_ratio", _NODE_SMOKE_SCRIPT)
        self.assertIn("visual_metrics", _NODE_SMOKE_SCRIPT)

    def test_ui_smoke_supports_visual_baseline_diff_gate(self) -> None:
        self.assertIn("visual-baseline.json", _NODE_SMOKE_SCRIPT)
        self.assertIn("comparePng", _NODE_SMOKE_SCRIPT)
        self.assertIn("maxPixelDiffRatio", _NODE_SMOKE_SCRIPT)
        self.assertIn("maxMeanPixelDelta", _NODE_SMOKE_SCRIPT)
        self.assertIn("visual_diffs", _NODE_SMOKE_SCRIPT)
        self.assertIn("updateVisualBaseline", _NODE_SMOKE_SCRIPT)

    def test_ci_runs_visual_baseline_update_and_compare(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("--update-visual-baseline", workflow)
        self.assertGreaterEqual(workflow.count("--visual-baseline-dir /tmp/copilot-admin-ui-baseline"), 2)
        self.assertIn("/tmp/copilot-admin-ui-baseline/visual-baseline.json", workflow)


if __name__ == "__main__":
    unittest.main()
