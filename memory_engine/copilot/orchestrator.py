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

        for layer in self._layers_for_request(request):
            layer_result = self.retriever.search_layer(request, layer)
            steps.append(layer_result.trace_step)
            for result in layer_result.results:
                if result.memory_id in seen_memory_ids:
                    continue
                seen_memory_ids.add(result.memory_id)
                candidates.append(result)
            if len(candidates) >= request.top_k:
                break

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
            final_reason=self._final_reason(top_results),
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
        )

    def _final_reason(self, results: object) -> str:
        return "top_k_reranked_with_evidence" if results else "no_active_memory_with_evidence"
