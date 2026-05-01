from __future__ import annotations

import unittest
from datetime import datetime, timezone

from scripts.check_copilot_admin_tls_probe import run_tls_probe


VALID_CERT = {
    "subject": ((("commonName", "memory.company.internal"),),),
    "subjectAltName": (("DNS", "memory.company.internal"),),
    "notAfter": "Jan  1 00:00:00 2099 GMT",
}


class CopilotAdminTlsProbeTest(unittest.TestCase):
    def test_tls_probe_emits_manifest_patch_for_valid_endpoint(self) -> None:
        result = run_tls_probe(
            url="https://memory.company.internal/admin",
            certificate_fetcher=lambda host, port, timeout: VALID_CERT,
            hsts_fetcher=lambda url, timeout: {
                "status": 200,
                "strict_transport_security": "max-age=31536000; includeSubDomains",
            },
            now=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        )

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["production_ready_claim"])
        self.assertEqual([], result["failed_checks"])
        patch = result["production_manifest_patch"]["production_domain_tls"]
        self.assertEqual("https://memory.company.internal/admin", patch["url"])
        self.assertEqual("commonName=memory.company.internal", patch["certificate_subject"])
        self.assertEqual("2099-01-01T00:00:00+00:00", patch["certificate_expires_at"])
        self.assertTrue(patch["hsts_enabled"])
        self.assertIn("tls_probe:memory.company.internal:", patch["evidence_refs"][0])

    def test_tls_probe_rejects_placeholder_url_without_network(self) -> None:
        called = {"cert": False, "hsts": False}

        def cert_fetcher(host: str, port: int, timeout: float):
            called["cert"] = True
            return VALID_CERT

        def hsts_fetcher(url: str, timeout: float):
            called["hsts"] = True
            return {"status": 200, "strict_transport_security": "max-age=31536000"}

        result = run_tls_probe(
            url="https://localhost",
            certificate_fetcher=cert_fetcher,
            hsts_fetcher=hsts_fetcher,
        )

        self.assertFalse(result["ok"], result)
        self.assertEqual(["url"], result["failed_checks"])
        self.assertFalse(called["cert"])
        self.assertFalse(called["hsts"])
        self.assertIn("host_is_not_placeholder", result["checks"]["url"]["missing_or_placeholder"])

    def test_tls_probe_rejects_hostname_mismatch_and_missing_hsts(self) -> None:
        result = run_tls_probe(
            url="https://memory.company.internal",
            certificate_fetcher=lambda host, port, timeout: {
                "subject": ((("commonName", "other.company.internal"),),),
                "subjectAltName": (("DNS", "other.company.internal"),),
                "notAfter": "Jan  1 00:00:00 2099 GMT",
            },
            hsts_fetcher=lambda url, timeout: {"status": 200, "strict_transport_security": ""},
        )

        self.assertFalse(result["ok"], result)
        self.assertIn("certificate", result["failed_checks"])
        self.assertIn("hsts", result["failed_checks"])
        self.assertIn("hostname_matches_certificate", result["checks"]["certificate"]["missing_or_placeholder"])
        self.assertIn("hsts_header_present", result["checks"]["hsts"]["missing_or_placeholder"])


if __name__ == "__main__":
    unittest.main()
