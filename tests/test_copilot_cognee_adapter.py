from __future__ import annotations

import asyncio
import os
import sys
import types
import unittest
from unittest.mock import patch

from memory_engine.copilot.cognee_adapter import (
    CogneeAdapterNotConfigured,
    CogneeMemoryAdapter,
    curated_memory_document,
    _patch_cognee_embedding_batch_limit,
)


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

        self.assertEqual(
            "test_prefix_project_feishu_ai_challenge", adapter.dataset_for_scope("project:feishu_ai_challenge")
        )
        self.assertEqual("test_prefix_chat_oc_123", adapter.dataset_for_scope("chat:oc-123"))

    def test_unconfigured_adapter_fails_without_changing_state(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
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
        self.assertEqual("生产部署必须加 --canary", args[0])

    def test_sync_curated_memory_adds_ledger_metadata_then_cognifies(self) -> None:
        client = FakeCogneeClient()
        adapter = CogneeMemoryAdapter(client=client)
        memory = {
            "memory_id": "mem_1",
            "version_id": "ver_1",
            "version": 1,
            "type": "workflow",
            "subject": "生产部署",
            "current_value": "生产部署必须加 --canary --region cn-shanghai",
            "summary": "确认后的生产部署规则",
            "status": "active",
            "evidence": {
                "source_type": "unit_test",
                "source_id": "evt_1",
                "quote": "决定：生产部署必须加 --canary --region cn-shanghai。",
            },
        }

        result = adapter.sync_curated_memory("project:feishu_ai_challenge", memory)

        self.assertTrue(result["ok"])
        self.assertEqual(["add", "cognify"], [call[0] for call in client.calls])
        add_args, add_kwargs = client.calls[0][1], client.calls[0][2]
        self.assertIn("memory_id: mem_1", add_args[0])
        self.assertIn("provenance: copilot_ledger", add_args[0])
        self.assertIn("current_value: 生产部署必须加 --canary", add_args[0])
        self.assertNotIn("raw_json", add_args[0])
        self.assertEqual("mem_1", add_kwargs["metadata"]["memory_id"])
        self.assertEqual("copilot_ledger", add_kwargs["metadata"]["provenance"])
        self.assertEqual("feishu_memory_copilot_project_feishu_ai_challenge", client.calls[1][2]["datasets"])

    def test_sync_curated_memory_retries_without_metadata_for_installed_cognee_sdk_shape(self) -> None:
        class MetadataRejectingCogneeClient(FakeCogneeClient):
            def add(self, *args: object, **kwargs: object) -> dict[str, object]:
                if "metadata" in kwargs:
                    raise TypeError("add() got an unexpected keyword argument 'metadata'")
                self.calls.append(("add", args, kwargs))
                return {"ok": True}

        client = MetadataRejectingCogneeClient()
        adapter = CogneeMemoryAdapter(client=client)
        memory = {
            "memory_id": "mem_sdk_shape",
            "version_id": "ver_sdk_shape",
            "version": 2,
            "type": "decision",
            "subject": "Cognee sync",
            "current_value": "Confirmed memory must sync without repository fallback.",
            "summary": "SDK add() does not accept metadata.",
            "status": "active",
            "evidence": {
                "source_type": "unit_test",
                "source_id": "evt_sdk_shape",
                "quote": "Confirmed memory must sync without repository fallback.",
            },
        }

        result = adapter.sync_curated_memory("project:feishu_ai_challenge", memory)

        self.assertTrue(result["ok"])
        self.assertEqual(["add", "cognify"], [call[0] for call in client.calls])
        add_args, add_kwargs = client.calls[0][1], client.calls[0][2]
        self.assertNotIn("metadata", add_kwargs)
        self.assertIn("memory_id: mem_sdk_shape", add_args[0])
        self.assertIn("source_id: evt_sdk_shape", add_args[0])
        self.assertIn("provenance: copilot_ledger", add_args[0])
        self.assertEqual("feishu_memory_copilot_project_feishu_ai_challenge", client.calls[1][2]["datasets"])

    def test_sync_curated_memory_resolves_async_sdk_calls(self) -> None:
        class AsyncCogneeClient(FakeCogneeClient):
            async def add(self, *args: object, **kwargs: object) -> dict[str, object]:
                self.calls.append(("add", args, kwargs))
                return {"ok": True}

            async def cognify(self, *args: object, **kwargs: object) -> dict[str, object]:
                self.calls.append(("cognify", args, kwargs))
                return {"ok": True}

        client = AsyncCogneeClient()
        adapter = CogneeMemoryAdapter(client=client)

        result = adapter.sync_curated_memory(
            "project:feishu_ai_challenge",
            {
                "memory_id": "mem_async_sdk",
                "version_id": "ver_async_sdk",
                "version": 1,
                "type": "decision",
                "subject": "Cognee async SDK",
                "current_value": "Async Cognee calls are awaited inside the adapter.",
                "status": "active",
                "evidence": {"source_type": "unit_test", "source_id": "evt_async_sdk", "quote": "Async call."},
            },
        )

        self.assertTrue(result["ok"])
        self.assertEqual(["add", "cognify"], [call[0] for call in client.calls])
        self.assertEqual({"ok": True}, result["add_result"])
        self.assertEqual({"ok": True}, result["cognify_result"])

    def test_curated_memory_document_uses_only_curated_fields(self) -> None:
        document = curated_memory_document(
            {
                "type": "decision",
                "subject": "评审流程",
                "current_value": "候选记忆必须人工确认",
                "raw_json": {"token": "should_not_leak"},
                "evidence": {"quote": "决定：候选记忆必须人工确认。"},
            }
        )

        self.assertIn("current_value: 候选记忆必须人工确认", document)
        self.assertIn("evidence_quote: 决定：候选记忆必须人工确认。", document)
        self.assertNotIn("should_not_leak", document)

    def test_remember_candidate_text_falls_back_to_add_when_sdk_lacks_remember(self) -> None:
        class LegacyCogneeClient:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

            def add(self, *args: object, **kwargs: object) -> dict[str, object]:
                self.calls.append(("add", args, kwargs))
                return {"ok": True}

        client = LegacyCogneeClient()
        adapter = CogneeMemoryAdapter(client=client)

        adapter.remember_candidate_text(
            "project:feishu_ai_challenge",
            "生产部署必须加 --canary",
            source_type="unit_test",
        )

        method, args, kwargs = client.calls[-1]
        self.assertEqual("add", method)
        self.assertEqual("生产部署必须加 --canary", args[0])
        self.assertEqual("feishu_memory_copilot_project_feishu_ai_challenge", kwargs["dataset_name"])

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
        self.assertEqual("search", client.calls[-1][0])
        self.assertIn("生产部署参数", client.calls[-1][1])

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

    def test_sync_memory_withdrawal_forgets_memory_in_scope_dataset(self) -> None:
        client = FakeCogneeClient()
        adapter = CogneeMemoryAdapter(client=client)

        result = adapter.sync_memory_withdrawal("project:feishu_ai_challenge", "mem_1", reason="rejected")

        self.assertTrue(result["ok"])
        method, args, kwargs = client.calls[-1]
        self.assertEqual("forget", method)
        self.assertEqual(("mem_1",), args)
        self.assertEqual("feishu_memory_copilot_project_feishu_ai_challenge", kwargs["dataset_name"])
        self.assertEqual({"reason": "rejected"}, kwargs["metadata"])

    def test_cognee_embedding_batch_limit_splits_litellm_batches(self) -> None:
        class FakeLiteLLMEmbeddingEngine:
            def __init__(self) -> None:
                self.batch_sizes: list[int] = []

            async def embed_text(self, text: list[str]) -> list[list[float]]:
                self.batch_sizes.append(len(text))
                return [[float(len(item))] for item in text]

        module_name = "cognee.infrastructure.databases.vector.embeddings.LiteLLMEmbeddingEngine"
        fake_module = types.ModuleType(module_name)
        fake_module.LiteLLMEmbeddingEngine = FakeLiteLLMEmbeddingEngine

        with patch.dict(sys.modules, {module_name: fake_module}), patch.dict(
            os.environ, {"COGNEE_EMBEDDING_MAX_BATCH_SIZE": "3"}
        ):
            _patch_cognee_embedding_batch_limit()
            engine = FakeLiteLLMEmbeddingEngine()
            vectors = asyncio.run(engine.embed_text(["a", "bb", "ccc", "dddd", "eeeee", "ffffff", "ggggggg"]))

        self.assertEqual([[1.0], [2.0], [3.0], [4.0], [5.0], [6.0], [7.0]], vectors)
        self.assertEqual([3, 3, 1], engine.batch_sizes)


if __name__ == "__main__":
    unittest.main()
