from __future__ import annotations

import json
import unittest
from pathlib import Path

from memory_engine.copilot.tools import supported_tool_names, validate_tool_request


SCHEMA_PATH = Path("agent_adapters/openclaw/memory_tools.schema.json")
EXAMPLES_DIR = Path("agent_adapters/openclaw/examples")


class CopilotToolContractTest(unittest.TestCase):
    def test_openclaw_schema_lists_supported_tools(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        schema_tools = sorted(tool["name"] for tool in schema["tools"])

        self.assertEqual("2026.4.24", schema["openclaw_version"])
        self.assertEqual(supported_tool_names(), schema_tools)

    def test_schema_matches_parser_edge_contracts(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        tools = {tool["name"]: tool["input_schema"] for tool in schema["tools"]}

        search_filters = tools["memory.search"]["properties"]["filters"]
        self.assertFalse(search_filters["additionalProperties"])

        prefetch_context = tools["memory.prefetch"]["properties"]["current_context"]
        self.assertEqual(1, prefetch_context["minProperties"])

    def test_validate_tool_request_accepts_search_payload(self) -> None:
        result = validate_tool_request(
            "memory.search",
            {
                "query": "production deployment region",
                "scope": "project:feishu_ai_challenge",
                "top_k": 3,
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual("memory.search", result["tool"])
        self.assertIn("parsed_request", result)
        self.assertNotIn("results", result)
        self.assertEqual("active", result["parsed_request"]["filters"]["status"])

    def test_validate_tool_request_uses_standard_error_shape(self) -> None:
        result = validate_tool_request("memory.search", {"query": "deployment"})

        self.assertFalse(result["ok"])
        self.assertEqual("validation_error", result["error"]["code"])
        self.assertFalse(result["error"]["retryable"])
        self.assertEqual({"tool": "memory.search"}, result["error"]["details"])

    def test_examples_only_use_declared_tools(self) -> None:
        supported = set(supported_tool_names())
        example_paths = sorted(EXAMPLES_DIR.glob("*.json"))

        self.assertGreaterEqual(len(example_paths), 3)
        for path in example_paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            for step in payload["steps"]:
                self.assertIn(step["tool"], supported, msg=str(path))


if __name__ == "__main__":
    unittest.main()
