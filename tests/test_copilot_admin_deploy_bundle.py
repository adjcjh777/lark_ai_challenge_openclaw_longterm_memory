from __future__ import annotations

import unittest

from scripts.check_copilot_admin_deploy_bundle import BOUNDARY, run_deploy_bundle_check


class CopilotAdminDeployBundleTest(unittest.TestCase):
    def test_deploy_bundle_is_staging_ready_but_production_blocked(self) -> None:
        result = run_deploy_bundle_check()

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["staging_bundle_ok"], result)
        self.assertTrue(result["production_blocked"], result)
        self.assertEqual(BOUNDARY, result["boundary"])
        self.assertEqual([], result["failed_checks"])
        self.assertIn("nginx_tls_reverse_proxy", {check["name"] for check in result["checks"]})
        self.assertIn("systemd_hardening", {check["name"] for check in result["checks"]})
        self.assertIn("completion_audit_gate", {check["name"] for check in result["checks"]})
        self.assertTrue(all(check["status"] == "pass" for check in result["checks"]))
        self.assertIn("real_enterprise_idp", {blocker["id"] for blocker in result["production_blockers"]})
        self.assertIn("production_database", {blocker["id"] for blocker in result["production_blockers"]})


if __name__ == "__main__":
    unittest.main()
