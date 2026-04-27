from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any

from memory_engine.repository import MemoryRepository

from .schemas import MemoryLayer, MemoryResult, RetrievalTraceStep, SearchRequest


@dataclass(frozen=True)
class LayerSearchResult:
    layer: MemoryLayer
    backend: str
    results: list[MemoryResult]
    trace_step: RetrievalTraceStep


class LayerAwareRetriever:
    """Layer-aware retrieval facade over the existing repository fallback.

    The legacy repository does not yet persist a `layer` column. This facade is
    the narrow 2026-04-28 adapter boundary: it simulates L1/L2/L3 routing without
    changing the old SQLite schema.
    """

    backend = "repository_fallback"

    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    def search_layer(self, request: SearchRequest, layer: MemoryLayer) -> LayerSearchResult:
        started = time.perf_counter()
        results: list[MemoryResult] = []
        note: str | None = None

        if request.filters.get("status", "active") != "active":
            note = "default_search_excludes_non_active_memory"
        elif request.filters.get("layer") and request.filters["layer"] != layer.value:
            note = "skipped_by_layer_filter"
        elif layer == MemoryLayer.COLD:
            note = "l3_raw_events_blocked_for_default_search"
        else:
            candidates = self.repository.recall_candidates(request.scope, request.query, limit=request.top_k)
            results = self._filter_and_map_candidates(candidates, request=request, layer=layer)
            if layer == MemoryLayer.HOT:
                results = [result for result in results if result.score >= 100]
                if not results:
                    note = "no_hot_match_above_threshold"

        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        step = RetrievalTraceStep(
            layer=layer.value,
            backend=self.backend,
            query=request.query,
            requested_top_k=request.top_k,
            returned_count=len(results),
            elapsed_ms=elapsed_ms,
            hit_memory_ids=[result.memory_id for result in results],
            note=note,
        )
        return LayerSearchResult(layer=layer, backend=self.backend, results=results, trace_step=step)

    def _filter_and_map_candidates(
        self,
        candidates: list[dict[str, Any]],
        *,
        request: SearchRequest,
        layer: MemoryLayer,
    ) -> list[MemoryResult]:
        expected_type = request.filters.get("type")
        results: list[MemoryResult] = []
        for candidate in candidates:
            if expected_type and candidate.get("type") != expected_type:
                continue
            if candidate.get("status") != "active":
                continue
            mapped = MemoryResult.from_repository_candidate({**candidate, "layer": layer.value})
            if not any(evidence.quote for evidence in mapped.evidence):
                continue
            results.append(mapped)
        return results


def rerank_results(results: list[MemoryResult]) -> list[MemoryResult]:
    layer_bonus = {
        MemoryLayer.HOT.value: 10.0,
        MemoryLayer.WARM.value: 3.0,
        MemoryLayer.COLD.value: 0.0,
    }
    rescored = [
        replace(result, score=round(result.score + layer_bonus.get(result.layer, 0.0), 3))
        for result in results
    ]
    ordered = sorted(rescored, key=lambda item: (-item.score, item.layer, item.rank, item.memory_id))
    return [replace(result, rank=index) for index, result in enumerate(ordered, start=1)]
