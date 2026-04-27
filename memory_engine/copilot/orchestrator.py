from __future__ import annotations

from dataclasses import replace

from .retrieval import LayerAwareRetriever, rerank_results
from .schemas import MemoryLayer, RetrievalTrace, RetrievalTraceStep, SearchRequest, SearchResponse


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
            step = layer_result.trace_step
            for result in layer_result.results:
                if result.memory_id in seen_memory_ids:
                    continue
                seen_memory_ids.add(result.memory_id)
                candidates.append(result)

            if len(candidates) >= request.top_k:
                top_k_satisfied = True
                if not step.note:
                    step = replace(step, note="top_k_satisfied_after_layer")
            steps.append(step)

        ranked = rerank_results(candidates)
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
        )

    def _final_reason(self, results: object, steps: list[RetrievalTraceStep]) -> str:
        if not results:
            return "no_active_memory_with_evidence"
        hit_layers = [step.layer for step in steps if step.hit_memory_ids]
        if MemoryLayer.HOT.value in hit_layers:
            return "top_k_satisfied_at_L1"
        if MemoryLayer.WARM.value in hit_layers:
            return "fallback_to_L2"
        if MemoryLayer.COLD.value in hit_layers:
            return "deep_trace_layer_filter_L3"
        return "top_k_reranked_with_evidence"
