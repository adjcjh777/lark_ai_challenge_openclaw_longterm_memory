from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SymphonySetupTest(unittest.TestCase):
    def test_repo_contains_symphony_workflow_and_runbook(self) -> None:
        workflow = ROOT / "WORKFLOW.md"
        runbook = ROOT / "docs" / "reference" / "symphony-setup.md"

        self.assertTrue(workflow.exists(), "WORKFLOW.md is required for Symphony")
        self.assertTrue(runbook.exists(), "docs/reference/symphony-setup.md should document local setup")

    def test_workflow_points_to_this_repository_and_required_env(self) -> None:
        text = (ROOT / "WORKFLOW.md").read_text(encoding="utf-8")

        for required in (
            "tracker:",
            "kind: linear",
            "api_key: $LINEAR_API_KEY",
            "project_slug: $SYMPHONY_LINEAR_PROJECT_SLUG",
            "workspace:",
            "root: $SYMPHONY_WORKSPACE_ROOT",
            "SOURCE_REPO_URL",
            "adjcjh777/lark_ai_challenge_openclaw_longterm_memory",
            "codex",
            "app-server",
            "python3 scripts/check_openclaw_version.py",
            "python3 scripts/check_agent_harness.py",
        ):
            self.assertIn(required, text)

    def test_env_example_includes_symphony_runtime_variables(self) -> None:
        text = (ROOT / ".env.example").read_text(encoding="utf-8")

        for required in (
            "LINEAR_API_KEY=",
            "SYMPHONY_LINEAR_PROJECT_SLUG=",
            "SYMPHONY_WORKSPACE_ROOT=",
            "SOURCE_REPO_URL=",
            "CODEX_BIN=",
        ):
            self.assertIn(required, text)

    def test_symphony_setup_check_passes(self) -> None:
        completed = subprocess.run(
            [sys.executable, "scripts/check_symphony_setup.py"],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
