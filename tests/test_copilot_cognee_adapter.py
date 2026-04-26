from __future__ import annotations

import asyncio
import unittest

from memory_engine.copilot.cognee_adapter import CogneeAdapterNotConfigured, CogneeMemoryAdapter


class FakeCogneeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def remember(self, *args: object, **kwargs: object) -> dict[str, object]:
        self.calls.append(("remember", args, kwargs))
        return {"ok": True}

    def recall(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
        self.calls.append(("recall", args, kwargs))
        return [{"text": "生产部署必须加 --canary", "metadata": {"memory_id": "mem_1", "status": "active"}}]

    def improve(self, *args: object, **kwargs: object) -> dict[str, object]:
        self.calls.append(("improve", args, kwargs))
        return {"ok": True}

    def forget(self, *args: object, **kwargs: object) -> dict[str, object]:
        self.calls.append(("forget", args, kwargs))
        return {"ok": True}

    def add(self, *args: object, **kwargs: object) -> dict[str, object]:
        self.calls.append(("add", args, kwargs))
        return {"ok": True}

    def cognify(self, *args: object, **kwargs: object) -> dict[str, object]:
        self.calls.append(("cognify", args, kwargs))
        return {"ok": True}

    def search(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
        self.calls.append(("search", args, kwargs))
        return [
            {
                "text": "生产部署必须加 --canary --region cn-shanghai",
                "score": 0.87,
                "metadata": {
                    "memory_id": "mem_1",
                    "type": "workflow",
                    "subject": "生产部署",
                    "status": "active",
                    "version": 1,
                    "source_type": "unit_test",
                    "source_id": "evt_1",
                    "quote": "生产部署必须加 --canary --region cn-shanghai",
                },
            }
        ]


class CogneeAdapterContractTest(unittest.TestCase):
    def test_dataset_name_is_stable_for_scope(self) -> None:
        adapter = CogneeMemoryAdapter(dataset_prefix="test_prefix")

        self.assertEqual("test_prefix_project_feishu_ai_challenge", adapter.dataset_for_scope("project:feishu_ai_challenge"))
        self.assertEqual("test_prefix_chat_oc_123", adapter.dataset_for_scope("chat:oc-123"))

    def test_unconfigured_adapter_fails_without_changing_state(self) -> None:
        adapter = CogneeMemoryAdapter()

        with self.assertRaises(CogneeAdapterNotConfigured):
            adapter.add_raw_event("project:feishu_ai_challenge", "生产部署必须加 --canary")

    def test_adapter_passes_dataset_and_evidence_metadata(self) -> None:
        client = FakeCogneeClient()
        adapter = CogneeMemoryAdapter(client=client)

        adapter.add_raw_event(
            "project:feishu_ai_challenge",
            "生产部署必须加 --canary",
            source_type="unit_test",
            source_id="evt_1",
        )
        method, args, kwargs = client.calls[-1]

        self.assertEqual("add", method)
        self.assertEqual("feishu_memory_copilot_project_feishu_ai_challenge", kwargs["dataset_name"])
        self.assertEqual("生产部署必须加 --canary", args[0]["content"])
        self.assertEqual({"source_type": "unit_test", "source_id": "evt_1"}, args[0]["metadata"])

    def test_adapter_normalizes_search_without_rewriting_status(self) -> None:
        client = FakeCogneeClient()
        adapter = CogneeMemoryAdapter(client=client)

        results = adapter.search("project:feishu_ai_challenge", "生产部署参数")

        self.assertEqual(1, len(results))
        self.assertEqual("active", results[0]["status"])
        self.assertEqual("workflow", results[0]["type"])
        self.assertEqual("生产部署", results[0]["subject"])
        self.assertEqual("unit_test", results[0]["evidence"][0]["source_type"])
        self.assertIn("--canary", results[0]["evidence"][0]["quote"])

    def test_adapter_normalizes_async_search_results(self) -> None:
        class AsyncSearchClient(FakeCogneeClient):
            async def search(self, *args: object, **kwargs: object) -> list[dict[str, object]]:
                return super().search(*args, **kwargs)

        adapter = CogneeMemoryAdapter(client=AsyncSearchClient())

        results = asyncio.run(adapter.search("project:feishu_ai_challenge", "生产部署参数"))

        self.assertEqual(1, len(results))
        self.assertEqual("active", results[0]["status"])

    def test_delete_scope_defaults_to_dry_run(self) -> None:
        client = FakeCogneeClient()
        adapter = CogneeMemoryAdapter(client=client)

        result = adapter.delete_scope("project:feishu_ai_challenge")

        self.assertTrue(result["dry_run"])
        self.assertFalse(result["deleted"])
        self.assertEqual([], client.calls)


if __name__ == "__main__":
    unittest.main()
