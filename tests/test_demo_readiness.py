from __future__ import annotations

import unittest

from scripts.check_demo_readiness import evaluate_demo_replay, run_demo_readiness


class DemoReadinessTest(unittest.TestCase):
    def test_readiness_fails_when_any_demo_step_is_not_ok(self) -> None:
        replay = {
            "ok": True,
            "openclaw_example_contract": {"ok": True},
            "steps": [
                {"name": "green", "output": {"ok": True}},
                {"name": "red", "output": {"ok": False}},
            ],
        }

        check = evaluate_demo_replay(replay)

        self.assertEqual("fail", check["status"])
        self.assertEqual(["red"], check["failed_steps"])

    def test_readiness_fails_when_step_output_is_missing(self) -> None:
        replay = {
            "ok": True,
            "openclaw_example_contract": {"ok": True},
            "steps": [{"name": "missing_output"}],
        }

        check = evaluate_demo_replay(replay)

        self.assertEqual("fail", check["status"])
        self.assertEqual(["missing_output"], check["failed_steps"])

    def test_readiness_fails_when_step_output_is_not_a_dict(self) -> None:
        replay = {
            "ok": True,
            "openclaw_example_contract": {"ok": True},
            "steps": [{"name": "malformed_output", "output": "not-a-dict"}],
        }

        check = evaluate_demo_replay(replay)

        self.assertEqual("fail", check["status"])
        self.assertEqual(["malformed_output"], check["failed_steps"])

    def test_readiness_fails_when_step_output_lacks_ok_true(self) -> None:
        replay = {
            "ok": True,
            "openclaw_example_contract": {"ok": True},
            "steps": [{"name": "missing_ok", "output": {"status": "pass"}}],
        }

        check = evaluate_demo_replay(replay)

        self.assertEqual("fail", check["status"])
        self.assertEqual(["missing_ok"], check["failed_steps"])

    def test_readiness_fails_when_openclaw_example_contract_is_not_ok(self) -> None:
        replay = {
            "ok": True,
            "openclaw_example_contract": {"ok": False},
            "steps": [{"name": "green", "output": {"ok": True}}],
        }

        check = evaluate_demo_replay(replay)

        self.assertEqual("fail", check["status"])
        self.assertEqual([], check["failed_steps"])
        self.assertFalse(check["openclaw_example_contract_ok"])

    def test_readiness_report_is_demo_preproduction_only(self) -> None:
        report = run_demo_readiness(demo_json_output=None)

        self.assertTrue(report["ok"])
        self.assertEqual("Demo-ready + Pre-production Readiness", report["phase"])
        self.assertEqual("local_demo_readiness_only", report["scope"])
        self.assertIn("no production deployment", report["boundary"])
        self.assertEqual("pass", report["checks"]["demo_replay"]["status"])
        self.assertEqual([], report["checks"]["demo_replay"]["failed_steps"])
        self.assertIn(
            report["checks"]["provider_config"]["status"],
            {"pass", "warning", "not_configured", "fallback_used"},
        )


if __name__ == "__main__":
    unittest.main()
