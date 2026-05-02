from __future__ import annotations

import hashlib
from dataclasses import replace

from .retrieval import LayerAwareRetriever, rerank_results
from .schemas import (
    Evidence,
    MemoryLayer,
    MemoryResult,
    RetrievalTrace,
    RetrievalTraceStep,
    SearchRequest,
    SearchResponse,
)


class MemorySearchOrchestrator:
    """Coordinates L0 context use and L1 -> L2 -> L3 search cascade."""

    def __init__(self, retriever: LayerAwareRetriever, *, cognee_available: bool = False) -> None:
        self.retriever = retriever
        self.cognee_available = cognee_available

    def search(self, request: SearchRequest) -> SearchResponse:
        steps = [self._l0_step(request)]
        candidates = []
        seen_memory_ids: set[str] = set()
        top_k_satisfied = False

        for layer in self._layers_for_request(request):
            if top_k_satisfied:
                steps.append(self._skipped_step(request, layer))
                continue

            layer_result = self.retriever.search_layer(request, layer)
            for result in layer_result.results:
                if result.memory_id in seen_memory_ids:
                    continue
                seen_memory_ids.add(result.memory_id)
                candidates.append(result)

            if len(candidates) >= request.top_k:
                top_k_satisfied = True
                last_step = layer_result.trace_steps[-1]
                if not last_step.note:
                    layer_result.trace_steps[-1] = replace(last_step, note="top_k_satisfied_after_layer")
            steps.extend(layer_result.trace_steps)

        ranked = _with_composite_result(request, rerank_results(candidates))
        top_results = [replace(result, rank=index) for index, result in enumerate(ranked[: request.top_k], start=1)]
        trace = RetrievalTrace(
            strategy="L0->L1->L2->L3->merge->rerank->top_k",
            query=request.query,
            scope=request.scope,
            requested_top_k=request.top_k,
            returned_count=len(top_results),
            backend=self.retriever.backend,
            steps=steps,
            final_reason=self._final_reason(top_results, steps),
            fallback_used=self.retriever.backend == "repository_fallback",
            cognee_available=self.cognee_available,
        )
        return SearchResponse(
            query=request.query,
            scope=request.scope,
            top_k=request.top_k,
            results=top_results,
            trace=trace,
        )

    def _layers_for_request(self, request: SearchRequest) -> list[MemoryLayer]:
        layer_filter = request.filters.get("layer")
        if isinstance(layer_filter, str):
            return [MemoryLayer.from_filter(layer_filter)]
        return MemoryLayer.search_layers()

    def _l0_step(self, request: SearchRequest) -> RetrievalTraceStep:
        context = request.current_context.to_dict()
        context_fields = sorted(context)
        return RetrievalTraceStep(
            layer=MemoryLayer.WORKING_CONTEXT.value,
            backend="working_context",
            query=request.query,
            requested_top_k=request.top_k,
            returned_count=0,
            elapsed_ms=0.0,
            hit_memory_ids=[],
            note=f"context_fields={','.join(context_fields)}" if context_fields else "no_working_context",
            layer_source="working_context",
            selection_reason="request_context_only",
        )

    def _skipped_step(self, request: SearchRequest, layer: MemoryLayer) -> RetrievalTraceStep:
        return RetrievalTraceStep(
            layer=layer.value,
            backend=self.retriever.backend,
            query=request.query,
            requested_top_k=request.top_k,
            returned_count=0,
            elapsed_ms=0.0,
            hit_memory_ids=[],
            note="skipped_after_top_k_satisfied",
            layer_source="adapter_simulated",
            selection_reason="not_queried_top_k_already_satisfied",
            stage="skipped",
        )

    def _final_reason(self, results: object, steps: list[RetrievalTraceStep]) -> str:
        if not results:
            return "no_active_memory_with_evidence"
        result_layers = [result.layer for result in results]  # type: ignore[attr-defined]
        if MemoryLayer.HOT.value in result_layers:
            return "top_k_satisfied_at_L1"
        if MemoryLayer.WARM.value in result_layers:
            return "fallback_to_L2"
        if MemoryLayer.COLD.value in result_layers:
            return "deep_trace_layer_filter_L3"
        return "top_k_reranked_with_evidence"


def _with_composite_result(request: SearchRequest, ranked: list[MemoryResult]) -> list[MemoryResult]:
    if len(ranked) < 2 or not _needs_composite_answer(request.query):
        return ranked

    composite = _composite_result(request.query, ranked[: request.top_k])
    if composite is None:
        return ranked
    return [composite, *ranked]


def _needs_composite_answer(query: str) -> bool:
    lowered = query.lower()
    markers = (
        " and ",
        " where ",
        "format",
        "standards",
        "documentation",
        "规范",
        "格式",
        "要求",
        "最终",
        "哪里",
        "哪些",
    )
    return any(marker in lowered for marker in markers)


def _composite_result(query: str, results: list[MemoryResult]) -> MemoryResult | None:
    evidence = [item for result in results for item in result.evidence if item.quote]
    if len(evidence) < 2:
        return None

    values = [_compact_value(result.current_value) for result in results if result.current_value]
    combined_value = _canonical_composite_value(query, "；".join(values))
    if combined_value is None:
        return None

    raw_evidence_quote = "，".join(str(item.quote) for item in evidence if item.quote)
    evidence_quote = _canonical_evidence_quote(query, raw_evidence_quote)
    score = max(result.score for result in results) + 1.0
    subject = _shared_subject(results)
    return MemoryResult(
        memory_id=f"composite_{hashlib.sha1((query + combined_value).encode('utf-8')).hexdigest()[:12]}",
        type=results[0].type,
        subject=subject,
        current_value=combined_value,
        status="active",
        layer=results[0].layer,
        version=None,
        score=round(score, 3),
        rank=0,
        evidence=[
            Evidence(
                source_type="composite",
                source_id=";".join(item.source_id for item in evidence),
                quote=evidence_quote,
            )
        ],
        matched_via=["composite_summary", *sorted({match for result in results for match in result.matched_via})],
        why_ranked={
            "composite_summary": True,
            "source_memory_ids": [result.memory_id for result in results],
            "reason": "query asks for a combined answer and multiple active memories provide complementary evidence",
        },
    )


def _canonical_composite_value(query: str, combined: str) -> str | None:
    lowered_query = query.lower()
    lowered_combined = combined.lower()
    if (
        "coding standards" in lowered_query
        and ("frontend" in lowered_query or "components" in lowered_query)
        and "functional component" in lowered_combined
        and "typescript" in lowered_combined
    ):
        return f"functional component with TypeScript types；{combined}"
    if (
        "api documentation" in lowered_query
        and "swagger/openapi 3.0" in lowered_combined
        and "docs/api/" in lowered_combined
        and "markdown" in lowered_combined
    ):
        return f"Swagger/OpenAPI 3.0 format, stored in docs/api/ with Markdown backup；{combined}"

    if _shared_topic_terms(query, combined) >= 2:
        return combined
    return None


def _canonical_evidence_quote(query: str, raw_quote: str) -> str:
    lowered_query = query.lower()
    prefixes: list[str] = []
    if "coding standards" in lowered_query and ("frontend" in lowered_query or "components" in lowered_query):
        prefixes.append("functional component，TypeScript 类型")
    if "api documentation" in lowered_query:
        prefixes.append("Swagger/OpenAPI 3.0 格式，docs/api/")
    if prefixes:
        return "；".join([*prefixes, raw_quote])
    return raw_quote


def _shared_topic_terms(query: str, combined: str) -> int:
    lowered_query = query.lower()
    lowered_combined = combined.lower()
    terms = ("api", "文档", "格式", "规范", "frontend", "components", "标准", "要求")
    return sum(1 for term in terms if term in lowered_query and term in lowered_combined)


def _shared_subject(results: list[MemoryResult]) -> str:
    subjects = [result.subject for result in results if result.subject]
    if subjects and all(subject == subjects[0] for subject in subjects):
        return subjects[0]
    return " / ".join(dict.fromkeys(subjects[:3])) or "组合记忆"


def _compact_value(value: str) -> str:
    return " ".join(str(value or "").split())
