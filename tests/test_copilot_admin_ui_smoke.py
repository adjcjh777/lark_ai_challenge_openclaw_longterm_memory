from __future__ import annotations

import unittest

from scripts.check_copilot_admin_ui_smoke import _NODE_SMOKE_SCRIPT


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


if __name__ == "__main__":
    unittest.main()
