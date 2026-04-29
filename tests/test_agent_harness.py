from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AgentHarnessTest(unittest.TestCase):
    def test_agents_md_is_a_map_not_the_full_manual(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        line_count = len(agents.splitlines())

        self.assertLessEqual(line_count, 180)
        for required_pointer in (
            "docs/harness/README.md",
            "docs/productization/agent-execution-contract.md",
            "docs/productization/full-copilot-next-execution-doc.md",
            "docs/productization/prd-completion-audit-and-gap-tasks.md",
        ):
            self.assertIn(required_pointer, agents)

    def test_harness_knowledge_base_has_required_indexes(self) -> None:
        for path in (
            ROOT / "docs" / "harness" / "README.md",
            ROOT / "docs" / "harness" / "QUALITY_SCORE.md",
            ROOT / "docs" / "harness" / "TECH_DEBT_GARBAGE_COLLECTION.md",
            ROOT / "docs" / "productization" / "agent-execution-contract.md",
        ):
            self.assertTrue(path.exists(), f"missing harness artifact: {path.relative_to(ROOT)}")

    def test_agent_harness_check_script_passes(self) -> None:
        completed = subprocess.run(
            [sys.executable, "scripts/check_agent_harness.py"],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
