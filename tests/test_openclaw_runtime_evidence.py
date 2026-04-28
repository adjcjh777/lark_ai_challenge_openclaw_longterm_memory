from __future__ import annotations

import tempfile
import unittest

from scripts.openclaw_runtime_evidence import build_evidence


class OpenClawRuntimeEvidenceTest(unittest.TestCase):
    def test_build_evidence_runs_required_phase_b_flows(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="openclaw_runtime_evidence_", suffix=".sqlite") as tmp:
            evidence = build_evidence(db_path=tmp.name, persistent=True)

        self.assertTrue(evidence["ok"])
        self.assertFalse(evidence["production_feishu_write"])
        self.assertEqual(
            [
                "historical_decision_search",
                "candidate_create_then_confirm",
                "task_prefetch_context_pack",
            ],
            [flow["name"] for flow in evidence["flows"]],
        )
        self.assertEqual(
            [
                "memory.search",
                "memory.create_candidate + memory.confirm",
                "memory.prefetch",
            ],
            [flow["tool"] for flow in evidence["flows"]],
        )
        self.assertTrue(all(flow["request_id"] for flow in evidence["flows"]))
        self.assertTrue(all(flow["trace_id"] for flow in evidence["flows"]))
        self.assertTrue(all(flow["permission_decision"]["decision"] == "allow" for flow in evidence["flows"]))

    def test_candidate_flow_promotes_candidate_to_active(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="openclaw_runtime_evidence_", suffix=".sqlite") as tmp:
            evidence = build_evidence(db_path=tmp.name, persistent=True)

        candidate_flow = next(flow for flow in evidence["flows"] if flow["name"] == "candidate_create_then_confirm")
        self.assertTrue(candidate_flow["output"]["create_candidate"]["ok"])
        self.assertEqual("candidate", candidate_flow["output"]["create_candidate"]["candidate"]["status"])
        self.assertTrue(candidate_flow["output"]["confirm"]["ok"])
        self.assertEqual("active", candidate_flow["output"]["confirm"]["memory"]["status"])


if __name__ == "__main__":
    unittest.main()
