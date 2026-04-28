from __future__ import annotations

import unittest

from scripts.check_live_embedding_gate import format_gate_text, running_project_models


class LiveEmbeddingGateTest(unittest.TestCase):
    def test_running_project_models_parses_only_locked_models(self) -> None:
        output = """NAME                         ID              SIZE      PROCESSOR    CONTEXT    UNTIL
qwen3-embedding:0.6b-fp16   abc123          1.2 GB    100% GPU     32768      4 minutes from now
llama3.2:latest             def456          2.0 GB    100% CPU     4096       4 minutes from now
bge-m3:567m                 ghi789          1.2 GB    100% GPU     8192       4 minutes from now
"""

        self.assertEqual(["qwen3-embedding:0.6b-fp16", "bge-m3:567m"], running_project_models(output))

    def test_running_project_models_handles_empty_ps(self) -> None:
        self.assertEqual([], running_project_models("NAME    ID    SIZE    PROCESSOR    CONTEXT    UNTIL\n"))

    def test_format_gate_text_keeps_no_productized_live_boundary(self) -> None:
        text = format_gate_text(
            {
                "phase": "Phase D Live Cognee / Ollama Embedding Gate",
                "ok": True,
                "status": "pass",
                "scope": "live_embedding_gate_only",
                "boundary": "not productized live",
                "provider": {
                    "status": "pass",
                    "model": "ollama/qwen3-embedding:0.6b-fp16",
                    "endpoint": "http://localhost:11434",
                    "actual_dimensions": 1024,
                    "expected_dimensions": 1024,
                },
                "cognee_spike_dry_run": {"status": "pass", "skipped": False},
                "ollama_cleanup": {
                    "status": "pass",
                    "running_before_cleanup": ["qwen3-embedding:0.6b-fp16"],
                    "running_after_cleanup": [],
                },
            }
        )

        self.assertIn("not productized live", text)
        self.assertIn("after_cleanup=[]", text)


if __name__ == "__main__":
    unittest.main()
