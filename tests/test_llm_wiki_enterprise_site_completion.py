from __future__ import annotations

import unittest

from scripts.check_llm_wiki_enterprise_site_completion import run_completion_audit


class LlmWikiEnterpriseSiteCompletionTest(unittest.TestCase):
    def test_completion_audit_verifies_staging_but_keeps_goal_blocked(self) -> None:
        result = run_completion_audit()

        self.assertTrue(result["staging_ok"], result)
        self.assertFalse(result["goal_complete"], result)
        self.assertEqual("staging_verified_production_blocked", result["status"])
        self.assertEqual([], result["missing_or_weak_checks"])
        self.assertIn("知识图谱", result["objective"])
        self.assertEqual(
            {
                "LLM Wiki enterprise knowledge site",
                "Knowledge graph integration",
                "Visible knowledge graph backend",
                "Admin UI optimization",
                "Launch gates",
                "No-overclaim boundary",
            },
            {row["requirement"] for row in result["prompt_to_artifact"]},
        )
        self.assertTrue(all(row["status"] == "pass" for row in result["prompt_to_artifact"]))
        self.assertIn(
            "enterprise_idp_sso",
            {blocker["id"] for blocker in result["production_blockers"]},
        )
        self.assertIn(
            "productized_live_long_run",
            {blocker["id"] for blocker in result["production_blockers"]},
        )


if __name__ == "__main__":
    unittest.main()
