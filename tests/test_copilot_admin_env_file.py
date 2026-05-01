from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_copilot_admin_env_file import DEFAULT_EXAMPLE_PATH, check_admin_env_file


class CopilotAdminEnvFileTest(unittest.TestCase):
    def test_example_env_keeps_placeholders_and_loopback(self) -> None:
        result = check_admin_env_file(DEFAULT_EXAMPLE_PATH, expect_example=True)

        self.assertTrue(result["ok"], result)
        self.assertEqual("example", result["mode"])
        self.assertEqual([], result["failed_checks"])
        self.assertEqual("placeholder", result["checks"]["tokens"]["admin_token_state"])
        self.assertEqual("placeholder", result["checks"]["tokens"]["viewer_token_state"])
        self.assertEqual("loopback", result["checks"]["host"]["host_class"])
        self.assertEqual("example_manifest", result["checks"]["production_evidence_manifest"]["path_state"])

    def test_runtime_env_requires_replaced_distinct_tokens(self) -> None:
        with tempfile.TemporaryDirectory(prefix="copilot_admin_env_") as tmp:
            path = Path(tmp) / "admin.env"
            path.write_text(
                "\n".join(
                    [
                        "MEMORY_DB_PATH=/opt/feishu_ai_challenge/data/memory.sqlite",
                        "FEISHU_MEMORY_COPILOT_ADMIN_PRODUCTION_EVIDENCE_MANIFEST=/etc/feishu-memory-copilot/production-evidence.json",
                        "FEISHU_MEMORY_COPILOT_ADMIN_HOST=0.0.0.0",
                        "FEISHU_MEMORY_COPILOT_ADMIN_PORT=8765",
                        "FEISHU_MEMORY_COPILOT_ADMIN_TOKEN=admin-token-redacted",
                        "FEISHU_MEMORY_COPILOT_ADMIN_VIEWER_TOKEN=viewer-token-redacted",
                        "FEISHU_MEMORY_COPILOT_ADMIN_SSO_ENABLED=1",
                        "FEISHU_MEMORY_COPILOT_ADMIN_SSO_USER_HEADER=X-Forwarded-User",
                        "FEISHU_MEMORY_COPILOT_ADMIN_SSO_EMAIL_HEADER=X-Forwarded-Email",
                        "FEISHU_MEMORY_COPILOT_ADMIN_SSO_ADMIN_USERS=admin@example.com",
                        "FEISHU_MEMORY_COPILOT_ADMIN_SSO_ALLOWED_DOMAINS=example.com",
                    ]
                ),
                encoding="utf-8",
            )

            result = check_admin_env_file(path, expect_example=False)

        self.assertTrue(result["ok"], result)
        self.assertEqual("runtime", result["mode"])
        self.assertEqual("configured_redacted", result["checks"]["tokens"]["admin_token_state"])
        self.assertEqual("configured_redacted", result["checks"]["tokens"]["viewer_token_state"])
        self.assertEqual("remote_or_unspecified", result["checks"]["host"]["host_class"])
        self.assertTrue(result["checks"]["host"]["requires_token_for_remote"])
        self.assertEqual("configured_redacted", result["redacted_summary"]["FEISHU_MEMORY_COPILOT_ADMIN_TOKEN"])
        self.assertEqual("runtime_manifest", result["checks"]["production_evidence_manifest"]["path_state"])
        self.assertNotIn("admin-token-redacted", str(result))

    def test_runtime_env_rejects_placeholders_and_unrelated_secrets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="copilot_admin_env_bad_") as tmp:
            path = Path(tmp) / "admin.env"
            path.write_text(
                "\n".join(
                    [
                        "MEMORY_DB_PATH=/opt/feishu_ai_challenge/data/memory.sqlite",
                        "FEISHU_MEMORY_COPILOT_ADMIN_PRODUCTION_EVIDENCE_MANIFEST=/opt/feishu_ai_challenge/deploy/copilot-admin.production-evidence.example.json",
                        "FEISHU_MEMORY_COPILOT_ADMIN_HOST=127.0.0.1",
                        "FEISHU_MEMORY_COPILOT_ADMIN_PORT=8765",
                        "FEISHU_MEMORY_COPILOT_ADMIN_TOKEN=__CHANGE_ME_ADMIN_TOKEN__",
                        "FEISHU_MEMORY_COPILOT_ADMIN_VIEWER_TOKEN=__CHANGE_ME_ADMIN_TOKEN__",
                        "FEISHU_APP_SECRET=should-not-live-here",
                    ]
                ),
                encoding="utf-8",
            )

            result = check_admin_env_file(path, expect_example=False)

        self.assertFalse(result["ok"], result)
        self.assertIn("tokens", result["failed_checks"])
        self.assertIn("production_evidence_manifest", result["failed_checks"])
        self.assertIn("sso", result["failed_checks"])
        self.assertIn("secret_hygiene", result["failed_checks"])


if __name__ == "__main__":
    unittest.main()
