from __future__ import annotations

import asyncio
import tempfile
import unittest

from memory_engine.copilot.embeddings import DeterministicEmbeddingProvider
from memory_engine.copilot.retrieval import RecallIndexEntry
from memory_engine.copilot.schemas import Evidence, SearchRequest
from memory_engine.copilot.service import CopilotService
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository

SCOPE = "project:feishu_ai_challenge"


def current_context(
    action: str = "memory.search",
    *,
    tenant_id: str = "tenant:demo",
    organization_id: str = "org:demo",
) -> dict[str, object]:
    return {
        "scope": SCOPE,
        "tenant_id": tenant_id,
        "organization_id": organization_id,
        "permission": {
            "request_id": f"req_{action.replace('.', '_')}",
            "trace_id": f"trace_{action.replace('.', '_')}",
            "actor": {
                "user_id": "ou_test",
                "tenant_id": tenant_id,
                "organization_id": organization_id,
                "roles": ["member", "reviewer"],
            },
            "source_context": {"entrypoint": "unit_test", "workspace_id": SCOPE},
            "requested_action": action,
            "requested_visibility": "team",
            "timestamp": "2026-05-07T00:00:00+08:00",
        },
    }


class CopilotRetrievalTest(unittest.TestCase):
    def test_search_can_summarize_complementary_active_memories(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_retrieval_composite_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(SCOPE, "API 接口文档用 Swagger/OpenAPI 3.0 格式。", source_type="unit_test")
            repo.remember(SCOPE, "文档放在 docs/api/ 目录下，用 Markdown 格式存一份副本。", source_type="unit_test")

            response = CopilotService(repository=repo, embedding_provider=DeterministicEmbeddingProvider()).search(
                SearchRequest.from_payload(
                    {
                        "query": "API documentation format and where to store it",
                        "scope": SCOPE,
                        "current_context": current_context(),
                    }
                )
            )
            conn.close()

        self.assertTrue(response["ok"])
        self.assertEqual("composite_summary", response["results"][0]["matched_via"][0])
        self.assertIn("Swagger/OpenAPI 3.0 format", response["results"][0]["current_value"])
        self.assertIn("docs/api/", response["results"][0]["current_value"])
        self.assertIn("Swagger/OpenAPI 3.0 格式，docs/api/", response["results"][0]["evidence"][0]["quote"])
        self.assertEqual(True, response["results"][0]["why_ranked"]["composite_summary"])

    def test_search_trace_shows_l0_and_hybrid_stages_when_warm_fallback_is_needed(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_retrieval_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(
                "project:feishu_ai_challenge",
                "评测报告周日 20:00 前完成，负责人是程俊豪。",
                source_type="unit_test",
            )

            response = CopilotService(repository=repo).search(
                SearchRequest.from_payload(
                    {
                        "query": "谁负责评测报告",
                        "scope": "project:feishu_ai_challenge",
                        "current_context": {
                            "session_id": "sess_1",
                            "chat_id": "chat_1",
                            "task_id": "task_1",
                            "scope": "project:feishu_ai_challenge",
                            "permission": current_context()["permission"],
                        },
                    }
                )
            )
            conn.close()

        self.assertTrue(response["ok"])
        self.assertEqual(1, len(response["results"]))
        self.assertEqual("active", response["results"][0]["status"])
        self.assertEqual("L2", response["results"][0]["layer"])
        self.assertIn("程俊豪", response["results"][0]["current_value"])
        self.assertIn("keyword_index", response["results"][0]["matched_via"])
        self.assertIn("why_ranked", response["results"][0])
        self.assertEqual(["L1", "L2", "L3"], response["trace"]["layers"])
        self.assertIn("structured", response["trace"]["stages"])
        self.assertIn("keyword", response["trace"]["stages"])
        self.assertIn("vector", response["trace"]["stages"])
        self.assertIn("cognee", response["trace"]["stages"])
        self.assertIn("rerank", response["trace"]["stages"])
        l1_rerank = _trace_step(response, layer="L1", stage="rerank")
        self.assertEqual("no_hot_match_above_threshold", l1_rerank["note"])
        self.assertEqual("fallback_to_L2", response["trace"]["final_reason"])
        l3_structured = _trace_step(response, layer="L3", stage="structured")
        self.assertEqual("l3_raw_events_blocked_for_default_search", l3_structured["note"])
        self.assertEqual("adapter_simulated", _trace_step(response, layer="L2", stage="keyword")["layer_source"])

    def test_search_layer_filter_can_select_hot_path(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_retrieval_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(
                "project:feishu_ai_challenge",
                "生产部署必须加 --canary --region cn-shanghai。",
                source_type="unit_test",
            )

            response = CopilotService(repository=repo).search(
                SearchRequest.from_payload(
                    {
                        "query": "生产部署参数",
                        "scope": "project:feishu_ai_challenge",
                        "current_context": current_context(),
                        "filters": {"layer": "L1"},
                    }
                )
            )
            conn.close()

        self.assertTrue(response["ok"])
        self.assertEqual(1, len(response["results"]))
        self.assertEqual("L1", response["results"][0]["layer"])
        self.assertEqual(["L1"], response["trace"]["layers"])
        self.assertIn("keyword_index", response["results"][0]["matched_via"])
        self.assertTrue(response["results"][0]["why_ranked"]["evidence_complete"])
        why_ranked = response["results"][0]["why_ranked"]
        self.assertEqual(response["results"][0]["score"], why_ranked["score_breakdown"]["total"])
        self.assertIn("signals", why_ranked["score_breakdown"])
        self.assertEqual(180.0, why_ranked["score_thresholds"]["hot_layer_min_score"])
        self.assertTrue(why_ranked["score_thresholds"]["stale_shadow_filter_enabled"])

    def test_default_search_trace_keeps_all_layers_after_l1_hit(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_retrieval_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(
                "project:feishu_ai_challenge",
                "生产部署必须加 --canary --region cn-shanghai。",
                source_type="unit_test",
            )

            response = CopilotService(repository=repo).search(
                SearchRequest.from_payload(
                    {
                        "query": "生产部署参数",
                        "scope": "project:feishu_ai_challenge",
                        "top_k": 1,
                        "current_context": current_context(),
                    }
                )
            )
            conn.close()

        self.assertTrue(response["ok"])
        self.assertEqual(["L1", "L2", "L3"], response["trace"]["layers"])
        self.assertEqual("top_k_satisfied_at_L1", response["trace"]["final_reason"])
        self.assertEqual("top_k_satisfied_after_layer", _trace_step(response, layer="L1", stage="rerank")["note"])
        self.assertEqual("skipped_after_top_k_satisfied", _trace_step(response, layer="L2", stage="skipped")["note"])
        self.assertEqual("skipped_after_top_k_satisfied", _trace_step(response, layer="L3", stage="skipped")["note"])

    def test_default_search_does_not_return_candidates_or_raw_l3_events(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_retrieval_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.add_candidate(
                "project:feishu_ai_challenge",
                "客户项目验收标准需要候选复核。",
                source_type="unit_test",
                source_id="doc_1",
                document_token="doc_token_1",
                document_title="验收标准",
                quote="客户项目验收标准需要候选复核。",
            )
            repo.add_noise_event("project:feishu_ai_challenge", "raw events 里有一条不该默认返回的历史证据")

            response = CopilotService(repository=repo).search(
                SearchRequest.from_payload(
                    {
                        "query": "验收标准",
                        "scope": "project:feishu_ai_challenge",
                        "top_k": 3,
                        "current_context": current_context(),
                    }
                )
            )
            conn.close()

        self.assertTrue(response["ok"])
        self.assertEqual([], response["results"])
        self.assertEqual("no_active_memory_with_evidence", response["trace"]["final_reason"])
        self.assertIn("L3", response["trace"]["layers"])
        self.assertEqual(
            "l3_raw_events_blocked_for_default_search", _trace_step(response, layer="L3", stage="structured")["note"]
        )

    def test_default_search_filters_shadowed_stale_active_memory(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_retrieval_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(
                "project:feishu_ai_challenge",
                "规则：数据同步 cron 表达式为 0 2 * * *（每天凌晨 2 点）。",
                source_type="unit_test",
            )
            repo.remember(
                "project:feishu_ai_challenge",
                "数据同步改成每 6 小时执行一次，cron 改成 0 */6 * * *。",
                source_type="unit_test",
            )

            response = CopilotService(repository=repo).search(
                SearchRequest.from_payload(
                    {
                        "query": "数据同步频率",
                        "scope": "project:feishu_ai_challenge",
                        "top_k": 3,
                        "current_context": current_context(),
                    }
                )
            )
            conn.close()

        self.assertTrue(response["ok"])
        values = [item["current_value"] for item in response["results"]]
        self.assertTrue(any("0 */6 * * *" in value for value in values))
        self.assertFalse(any("0 2 * * *" in value for value in values))
        self.assertEqual("stale_shadow_filtered:1", _trace_step(response, layer="L2", stage="rerank")["note"])

    def test_missing_evidence_candidate_does_not_enter_top_results(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_retrieval_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(
                "project:feishu_ai_challenge",
                "生产部署必须加 --canary --region cn-shanghai。",
                source_type="unit_test",
            )
            conn.execute("UPDATE memory_evidence SET quote = NULL")
            conn.commit()

            response = CopilotService(repository=repo).search(
                SearchRequest.from_payload(
                    {
                        "query": "生产部署参数",
                        "scope": "project:feishu_ai_challenge",
                        "current_context": current_context(),
                    }
                )
            )
            conn.close()

        self.assertTrue(response["ok"])
        self.assertEqual([], response["results"])
        self.assertEqual("no_active_memory_with_evidence", response["trace"]["final_reason"])
        l1_rerank = _trace_step(response, layer="L1", stage="rerank")
        self.assertEqual("dropped_missing_evidence", l1_rerank["note"])
        self.assertEqual(1, l1_rerank["dropped_count"])

    def test_search_filters_active_memories_by_permission_tenant_and_org(self) -> None:
        with tempfile.NamedTemporaryFile(prefix="copilot_retrieval_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(
                "project:feishu_ai_challenge",
                "生产部署必须加 --canary --region cn-shanghai。",
                source_type="unit_test",
            )
            conn.execute("UPDATE memories SET tenant_id = 'tenant:other', organization_id = 'org:other'")
            conn.commit()

            response = CopilotService(repository=repo).search(
                SearchRequest.from_payload(
                    {
                        "query": "生产部署参数",
                        "scope": "project:feishu_ai_challenge",
                        "current_context": current_context(),
                    }
                )
            )
            conn.close()

        self.assertTrue(response["ok"])
        self.assertEqual([], response["results"])
        self.assertNotIn("--canary", str(response))

    def test_cognee_result_missing_provenance_is_backfilled_from_ledger(self) -> None:
        class FakeCogneeAdapter:
            is_configured = True

            def __init__(self, memory_id: str) -> None:
                self.memory_id = memory_id

            def search(self, scope: str, query: str, **kwargs: object) -> list[dict[str, object]]:
                return [{"memory_id": self.memory_id, "score": 0.91}]

        with tempfile.NamedTemporaryFile(prefix="copilot_retrieval_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            remembered = repo.remember(
                "project:feishu_ai_challenge",
                "OpenClaw 开发版本固定为 2026.4.24，不能主动运行升级命令。",
                source_type="unit_test",
            )

            response = CopilotService(
                repository=repo,
                cognee_adapter=FakeCogneeAdapter(remembered["memory_id"]),  # type: ignore[arg-type]
            ).search(
                SearchRequest.from_payload(
                    {
                        "query": "OpenClaw 版本锁是多少",
                        "scope": "project:feishu_ai_challenge",
                        "current_context": current_context(),
                    }
                )
            )
            conn.close()

        self.assertTrue(response["ok"])
        self.assertIn("cognee", response["results"][0]["matched_via"])
        self.assertIn("2026.4.24", response["results"][0]["evidence"][0]["quote"])
        self.assertIsNone(_trace_step(response, layer="L1", stage="cognee").get("note"))

    def test_cognee_only_result_without_ledger_match_is_dropped(self) -> None:
        class FakeCogneeAdapter:
            is_configured = True

            def search(self, scope: str, query: str, **kwargs: object) -> list[dict[str, object]]:
                return [
                    {
                        "memory_id": "cognee_external_1",
                        "current_value": "这条只有 Cognee 文本，没有 Copilot ledger evidence pointer。",
                        "score": 0.99,
                        "evidence": [{"quote": "Cognee 自带 quote 不能当作 Copilot 证据"}],
                    }
                ]

        with tempfile.NamedTemporaryFile(prefix="copilot_retrieval_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            repo.remember(
                "project:feishu_ai_challenge",
                "OpenClaw 开发版本固定为 2026.4.24，不能主动运行升级命令。",
                source_type="unit_test",
            )

            response = CopilotService(
                repository=repo,
                cognee_adapter=FakeCogneeAdapter(),  # type: ignore[arg-type]
            ).search(
                SearchRequest.from_payload(
                    {
                        "query": "完全不同的 Cognee 外部答案",
                        "scope": "project:feishu_ai_challenge",
                        "current_context": current_context(),
                    }
                )
            )
            conn.close()

        self.assertTrue(response["ok"])
        self.assertFalse(any(result["memory_id"] == "cognee_external_1" for result in response["results"]))
        self.assertEqual(
            "cognee_unmatched_ledger_results_dropped:1",
            _trace_step(response, layer="L1", stage="cognee")["note"],
        )

    def test_async_cognee_search_is_normalized_in_sync_service_path(self) -> None:
        class AsyncCogneeAdapter:
            is_configured = True

            def __init__(self, memory_id: str) -> None:
                self.memory_id = memory_id

            async def search(self, scope: str, query: str, **kwargs: object) -> list[dict[str, object]]:
                await asyncio.sleep(0)
                return [{"memory_id": self.memory_id, "score": 0.91}]

        with tempfile.NamedTemporaryFile(prefix="copilot_retrieval_", suffix=".sqlite") as tmp:
            conn = connect(tmp.name)
            init_db(conn)
            repo = MemoryRepository(conn)
            remembered = repo.remember(
                "project:feishu_ai_challenge",
                "OpenClaw 开发版本固定为 2026.4.24，不能主动运行升级命令。",
                source_type="unit_test",
            )

            response = CopilotService(
                repository=repo,
                cognee_adapter=AsyncCogneeAdapter(remembered["memory_id"]),  # type: ignore[arg-type]
            ).search(
                SearchRequest.from_payload(
                    {
                        "query": "OpenClaw 版本锁是多少",
                        "scope": "project:feishu_ai_challenge",
                        "current_context": current_context(),
                    }
                )
            )
            conn.close()

        self.assertTrue(response["ok"])
        self.assertIn("cognee", response["results"][0]["matched_via"])
        self.assertIsNone(_trace_step(response, layer="L1", stage="cognee").get("note"))

    def test_async_cognee_search_is_normalized_with_running_event_loop(self) -> None:
        class AsyncCogneeAdapter:
            is_configured = True

            def __init__(self, memory_id: str) -> None:
                self.memory_id = memory_id

            async def search(self, scope: str, query: str, **kwargs: object) -> list[dict[str, object]]:
                await asyncio.sleep(0)
                return [{"memory_id": self.memory_id, "score": 0.88}]

        async def run_search() -> dict[str, object]:
            with tempfile.NamedTemporaryFile(prefix="copilot_retrieval_", suffix=".sqlite") as tmp:
                conn = connect(tmp.name)
                init_db(conn)
                repo = MemoryRepository(conn)
                remembered = repo.remember(
                    "project:feishu_ai_challenge",
                    "OpenClaw 开发版本固定为 2026.4.24，不能主动运行升级命令。",
                    source_type="unit_test",
                )

                response = CopilotService(
                    repository=repo,
                    cognee_adapter=AsyncCogneeAdapter(remembered["memory_id"]),  # type: ignore[arg-type]
                ).search(
                    SearchRequest.from_payload(
                        {
                            "query": "OpenClaw 版本锁是多少",
                            "scope": "project:feishu_ai_challenge",
                            "current_context": current_context(),
                        }
                    )
                )
                conn.close()
                return response

        response = asyncio.run(run_search())

        self.assertTrue(response["ok"])
        self.assertIn("cognee", response["results"][0]["matched_via"])
        self.assertIsNone(_trace_step(response, layer="L1", stage="cognee").get("note"))

    def test_recall_index_and_embedding_use_curated_fields_only(self) -> None:
        entry = RecallIndexEntry(
            memory_id="mem_1",
            type="workflow",
            subject="生产部署",
            current_value="生产部署必须加 --canary",
            status="active",
            layer="L2",
            version=1,
            confidence=0.75,
            importance=0.8,
            updated_at=1,
            recall_count=0,
            evidence=Evidence(source_type="unit_test", source_id="evt_1", quote="生产部署必须加 --canary"),
            evidence_id="evi_1",
            summary="发布规则",
        )

        self.assertIn("type: workflow", entry.index_text)
        self.assertIn("subject: 生产部署", entry.index_text)
        self.assertIn("current_value: 生产部署必须加 --canary", entry.index_text)
        self.assertIn("summary: 发布规则", entry.index_text)
        self.assertIn("evidence.quote: 生产部署必须加 --canary", entry.index_text)
        self.assertNotIn("raw_event", entry.index_text)

        embedder = DeterministicEmbeddingProvider(dimension=16)
        self.assertEqual(
            embedder.embed_curated_memory(entry.embedding_text()), embedder.embed_curated_memory(entry.embedding_text())
        )


def _trace_step(response: dict[str, object], *, layer: str, stage: str) -> dict[str, object]:
    for step in response["trace"]["steps"]:  # type: ignore[index]
        if step["layer"] == layer and step.get("stage") == stage:
            return step
    raise AssertionError(f"trace step not found: layer={layer} stage={stage}")


if __name__ == "__main__":
    unittest.main()
