from __future__ import annotations

import asyncio
import inspect
import os
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Any

from memory_engine.models import normalize_subject, parse_scope
from memory_engine.repository import MemoryRepository

from .cognee_adapter import CogneeMemoryAdapter
from .embeddings import (
    CuratedMemoryEmbeddingText,
    DeterministicEmbeddingProvider,
    OllamaEmbeddingProvider,
    cosine_similarity,
    create_embedding_provider,
)
from .schemas import Evidence, MemoryLayer, MemoryResult, RetrievalTraceStep, SearchRequest

MATCH_ORDER = ("keyword_index", "vector", "cognee", "repository_fallback")


@dataclass(frozen=True)
class RetrievalScoringConfig:
    subject_exact_bonus: float = 100.0
    subject_contains_bonus: float = 60.0
    token_subject_bonus: float = 10.0
    token_current_value_bonus: float = 5.0
    token_summary_bonus: float = 3.0
    token_evidence_bonus: float = 4.0
    vector_min_similarity: float = 0.08
    vector_weight: float = 80.0
    importance_weight: float = 20.0
    confidence_weight: float = 15.0
    recency_max_score: float = 10.0
    version_freshness_bonus: float = 5.0
    evidence_bonus: float = 20.0
    hot_layer_min_score: float = 180.0
    layer_bonus: dict[str, float] = field(
        default_factory=lambda: {
            MemoryLayer.HOT.value: 10.0,
            MemoryLayer.WARM.value: 3.0,
            MemoryLayer.COLD.value: 0.0,
        }
    )
    stale_shadow_filter_enabled: bool = True
    stale_shadow_min_anchor_overlap: int = 1


@dataclass(frozen=True)
class RecallIndexEntry:
    memory_id: str
    type: str
    subject: str
    current_value: str
    status: str
    layer: str
    version: int | None
    confidence: float
    importance: float
    updated_at: int
    recall_count: int
    evidence: Evidence
    evidence_id: str | None
    summary: str | None = None

    @property
    def index_text(self) -> str:
        return self.embedding_text().to_text()

    def embedding_text(self) -> CuratedMemoryEmbeddingText:
        return CuratedMemoryEmbeddingText(
            type=self.type,
            subject=self.subject,
            current_value=self.current_value,
            summary=self.summary,
            evidence_quote=self.evidence.quote,
        )

    def to_result(
        self,
        *,
        score: float,
        rank: int,
        matched_via: list[str],
        why_ranked: dict[str, Any],
    ) -> MemoryResult:
        return MemoryResult(
            memory_id=self.memory_id,
            type=self.type,
            subject=self.subject,
            current_value=self.current_value,
            status=self.status,
            layer=self.layer,
            version=self.version,
            score=round(score, 3),
            rank=rank,
            evidence=[self.evidence],
            matched_via=matched_via,
            why_ranked=why_ranked,
        )


@dataclass(frozen=True)
class LayerSearchResult:
    layer: MemoryLayer
    backend: str
    results: list[MemoryResult]
    trace_steps: list[RetrievalTraceStep]


@dataclass
class _MergedCandidate:
    entry: RecallIndexEntry | None
    result: MemoryResult
    keyword_score: float = 0.0
    vector_score: float = 0.0
    cognee_score: float = 0.0
    matched_via: set[str] | None = None

    def match_list(self) -> list[str]:
        matches = self.matched_via or set()
        return [name for name in MATCH_ORDER if name in matches]


class LayerAwareRetriever:
    """Hybrid retrieval facade over the existing repository fallback.

    The legacy repository still owns storage. This facade builds a short
    RecallIndex over active curated memories, then combines keyword, vector and
    optional Cognee signals without embedding raw events.
    """

    backend = "hybrid_retrieval"

    def __init__(
        self,
        repository: MemoryRepository,
        *,
        cognee_adapter: CogneeMemoryAdapter | None = None,
        embedding_provider: DeterministicEmbeddingProvider | OllamaEmbeddingProvider | None = None,
        scoring_config: RetrievalScoringConfig | None = None,
    ) -> None:
        self.repository = repository
        self.cognee_adapter = cognee_adapter
        self.scoring_config = scoring_config or RetrievalScoringConfig()

        # Use provided provider or create one automatically
        if embedding_provider is not None:
            self.embedding_provider = embedding_provider
        else:
            self.embedding_provider = _load_ollama_embedding_provider()

    def search_layer(self, request: SearchRequest, layer: MemoryLayer) -> LayerSearchResult:
        trace_steps: list[RetrievalTraceStep] = []
        explicit_layer_filter = request.filters.get("layer") == layer.value

        entries, structured_note = self._structured_filter(request, layer)
        trace_steps.append(
            self._trace_step(
                request,
                layer,
                stage="structured",
                backend="structured_filter",
                returned_count=len(entries),
                hit_memory_ids=[entry.memory_id for entry in entries],
                note=structured_note,
                selection_reason="scope_status_layer_type_filter",
            )
        )
        if not entries:
            return LayerSearchResult(layer=layer, backend=self.backend, results=[], trace_steps=trace_steps)

        keyword_scores = self._keyword_scores(entries, request.query)
        keyword_hits = [memory_id for memory_id, score in keyword_scores.items() if score > 0]
        trace_steps.append(
            self._trace_step(
                request,
                layer,
                stage="keyword",
                backend="keyword_index",
                returned_count=len(keyword_hits),
                hit_memory_ids=keyword_hits,
                note=None if keyword_hits else "keyword_index_no_match",
                selection_reason="subject_current_value_summary_evidence_quote",
            )
        )

        vector_note = None
        try:
            vector_scores = self._vector_scores(entries, request.query)
        except Exception as exc:
            vector_scores = {}
            vector_note = f"vector_embedding_unavailable:{exc.__class__.__name__}"
        vector_hits = [memory_id for memory_id, score in vector_scores.items() if score > 0]
        trace_steps.append(
            self._trace_step(
                request,
                layer,
                stage="vector",
                backend="curated_vector",
                returned_count=len(vector_hits),
                hit_memory_ids=vector_hits,
                note=vector_note or (None if vector_hits else "vector_similarity_no_match"),
                selection_reason="curated_memory_embedding_only",
            )
        )

        cognee_results, cognee_note = self._cognee_results(request, entries)
        trace_steps.append(
            self._trace_step(
                request,
                layer,
                stage="cognee",
                backend="cognee",
                returned_count=len(cognee_results),
                hit_memory_ids=[result.memory_id for result in cognee_results],
                note=cognee_note,
                selection_reason="optional_recall_channel",
            )
        )

        ranked, dropped_missing_evidence, dropped_shadowed = self._merge_and_rerank(
            entries,
            query=request.query,
            keyword_scores=keyword_scores,
            vector_scores=vector_scores,
            cognee_results=cognee_results,
        )
        if layer == MemoryLayer.HOT and not explicit_layer_filter:
            ranked = [result for result in ranked if result.score >= self.scoring_config.hot_layer_min_score]
        note = None
        if not ranked:
            note = "no_hot_match_above_threshold" if layer == MemoryLayer.HOT and not explicit_layer_filter else None
            if dropped_missing_evidence:
                note = "dropped_missing_evidence"
            if dropped_shadowed:
                note = "stale_shadow_filtered"
        elif dropped_shadowed:
            note = f"stale_shadow_filtered:{dropped_shadowed}"
        trace_steps.append(
            self._trace_step(
                request,
                layer,
                stage="rerank",
                backend="hybrid_rerank",
                returned_count=len(ranked),
                hit_memory_ids=[result.memory_id for result in ranked[: request.top_k]],
                note=note,
                selection_reason="importance_recency_confidence_version_layer_evidence_stale_shadow_filter",
                dropped_count=dropped_missing_evidence + dropped_shadowed,
            )
        )
        return LayerSearchResult(
            layer=layer,
            backend=self.backend,
            results=ranked[: request.top_k],
            trace_steps=trace_steps,
        )

    def _structured_filter(
        self,
        request: SearchRequest,
        layer: MemoryLayer,
    ) -> tuple[list[RecallIndexEntry], str | None]:
        status_filter = request.filters.get("status", "active")
        if status_filter != "active":
            return [], "default_search_excludes_non_active_memory"

        layer_filter = request.filters.get("layer")
        if isinstance(layer_filter, str) and layer_filter != layer.value:
            return [], "skipped_by_layer_filter"
        if layer == MemoryLayer.COLD and layer_filter != layer.value:
            return [], "l3_raw_events_blocked_for_default_search"

        parsed_scope = parse_scope(request.scope)
        context = request.current_context.to_dict()
        tenant_id = _target_context_value(context, "tenant_id")
        organization_id = _target_context_value(context, "organization_id")
        rows = self.repository.conn.execute(
            """
            SELECT
              m.*,
              v.version_no,
              e.id AS evidence_id,
              e.source_type AS evidence_source_type,
              e.source_event_id AS evidence_source_event_id,
              e.quote AS evidence_quote,
              r.source_id AS raw_source_id,
              r.raw_json AS raw_json
            FROM memories m
            LEFT JOIN memory_versions v ON v.id = m.active_version_id
            LEFT JOIN memory_evidence e
              ON e.id = (
                SELECT latest_e.id
                FROM memory_evidence latest_e
                WHERE latest_e.memory_id = m.id
                  AND latest_e.version_id = m.active_version_id
                ORDER BY latest_e.created_at DESC
                LIMIT 1
              )
            LEFT JOIN raw_events r ON r.id = e.source_event_id
            WHERE m.scope_type = ?
              AND m.scope_id = ?
              AND m.tenant_id = ?
              AND m.organization_id = ?
              AND m.status = 'active'
            ORDER BY m.updated_at DESC, m.id
            """,
            (parsed_scope.scope_type, parsed_scope.scope_id, tenant_id, organization_id),
        ).fetchall()

        expected_type = request.filters.get("type")
        entries = []
        for row in rows:
            if expected_type and row["type"] != expected_type:
                continue
            entries.append(self._row_to_index_entry(row, layer=layer))
        return entries, None

    def _row_to_index_entry(self, row: Any, *, layer: MemoryLayer) -> RecallIndexEntry:
        evidence = Evidence(
            source_type=str(row["evidence_source_type"] or "unknown"),
            source_id=row["raw_source_id"] or row["evidence_source_event_id"],
            quote=row["evidence_quote"],
        )
        return RecallIndexEntry(
            memory_id=str(row["id"]),
            type=str(row["type"]),
            subject=str(row["subject"]),
            current_value=str(row["current_value"]),
            status=str(row["status"]),
            layer=layer.value,
            version=row["version_no"],
            confidence=float(row["confidence"] or 0),
            importance=float(row["importance"] or 0),
            updated_at=int(row["updated_at"] or 0),
            recall_count=int(row["recall_count"] or 0),
            evidence=evidence,
            evidence_id=row["evidence_id"],
            summary=row["reason"],
        )

    def _keyword_scores(self, entries: list[RecallIndexEntry], query: str) -> dict[str, float]:
        scores: dict[str, float] = {}
        normalized_query = normalize_subject(query)
        tokens = set(_tokens(query))
        for entry in entries:
            score = 0.0
            if normalize_subject(entry.subject) == normalized_query:
                score += self.scoring_config.subject_exact_bonus
            if entry.subject and entry.subject in query:
                score += self.scoring_config.subject_contains_bonus
            haystacks = {
                "subject": entry.subject,
                "current_value": entry.current_value,
                "summary": entry.summary or "",
                "evidence": entry.evidence.quote or "",
            }
            for token in tokens:
                if not token:
                    continue
                if token in haystacks["subject"].lower():
                    score += self.scoring_config.token_subject_bonus
                if token in haystacks["current_value"].lower():
                    score += self.scoring_config.token_current_value_bonus
                if token in haystacks["summary"].lower():
                    score += self.scoring_config.token_summary_bonus
                if token in haystacks["evidence"].lower():
                    score += self.scoring_config.token_evidence_bonus
            if score > 0:
                scores[entry.memory_id] = round(score, 3)
        return scores

    def _vector_scores(self, entries: list[RecallIndexEntry], query: str) -> dict[str, float]:
        query_vector = self.embedding_provider.embed_text(query)
        scores: dict[str, float] = {}
        for entry in entries:
            entry_vector = self.embedding_provider.embed_curated_memory(entry.embedding_text())
            similarity = cosine_similarity(query_vector, entry_vector)
            if similarity > self.scoring_config.vector_min_similarity:
                scores[entry.memory_id] = round(similarity * self.scoring_config.vector_weight, 3)
        return scores

    def _cognee_results(
        self,
        request: SearchRequest,
        entries: list[RecallIndexEntry],
    ) -> tuple[list[MemoryResult], str | None]:
        if self.cognee_adapter is None or not self.cognee_adapter.is_configured:
            return [], "cognee_adapter_unavailable"

        entries_by_id = {entry.memory_id: entry for entry in entries}
        try:
            raw_results = self.cognee_adapter.search(request.scope, request.query, limit=request.top_k)
        except Exception as exc:
            return [], f"cognee_unavailable:{exc.__class__.__name__}"

        if inspect.isawaitable(raw_results):
            try:
                raw_results = _run_awaitable_sync(raw_results)
            except Exception as exc:
                return [], f"cognee_unavailable:{exc.__class__.__name__}"

        results = []
        dropped_unmatched = 0
        for rank, item in enumerate(raw_results or [], start=1):
            if not isinstance(item, dict):
                continue
            memory_id = str(item.get("memory_id") or "")
            entry = entries_by_id.get(memory_id)
            if entry is not None:
                results.append(
                    entry.to_result(
                        score=float(item.get("score") or 0) * 100,
                        rank=rank,
                        matched_via=["cognee"],
                        why_ranked={
                            "cognee_score": float(item.get("score") or 0) * 100,
                            "provenance": "copilot_ledger",
                        },
                    )
                )
                continue

            dropped_unmatched += 1
        if dropped_unmatched:
            return results, f"cognee_unmatched_ledger_results_dropped:{dropped_unmatched}"
        return results, None

    def _merge_and_rerank(
        self,
        entries: list[RecallIndexEntry],
        *,
        query: str,
        keyword_scores: dict[str, float],
        vector_scores: dict[str, float],
        cognee_results: list[MemoryResult],
    ) -> tuple[list[MemoryResult], int, int]:
        merged: dict[str, _MergedCandidate] = {}
        now_ms = int(time.time() * 1000)

        for entry in entries:
            keyword_score = keyword_scores.get(entry.memory_id, 0.0)
            vector_score = vector_scores.get(entry.memory_id, 0.0)
            if keyword_score <= 0 and vector_score <= 0:
                continue
            base = entry.to_result(score=0.0, rank=0, matched_via=[], why_ranked={})
            matches = set()
            if keyword_score > 0:
                matches.add("keyword_index")
            if vector_score > 0:
                matches.add("vector")
            merged[entry.memory_id] = _MergedCandidate(
                entry=entry,
                result=base,
                keyword_score=keyword_score,
                vector_score=vector_score,
                matched_via=matches,
            )

        for result in cognee_results:
            candidate = merged.get(result.memory_id)
            if candidate is None:
                candidate = _MergedCandidate(
                    entry=None,
                    result=result,
                    matched_via=set(result.matched_via or ["cognee"]),
                )
                merged[result.memory_id] = candidate
            else:
                candidate.matched_via = candidate.matched_via or set()
                candidate.matched_via.add("cognee")
            candidate.cognee_score = max(candidate.cognee_score, float(result.score or 0))

        ranked: list[MemoryResult] = []
        dropped_missing_evidence = 0
        for candidate in merged.values():
            evidence = candidate.result.evidence
            evidence_complete = bool(evidence and any(item.quote for item in evidence))
            if not evidence_complete:
                dropped_missing_evidence += 1
                continue

            entry = candidate.entry
            importance = entry.importance if entry else 0.3
            confidence = entry.confidence if entry else 0.3
            recency_score = _recency_score(
                now_ms,
                entry.updated_at if entry else now_ms,
                max_score=self.scoring_config.recency_max_score,
            )
            version_freshness = self.scoring_config.version_freshness_bonus if candidate.result.version else 0.0
            layer_bonus = self.scoring_config.layer_bonus.get(candidate.result.layer, 0.0)
            evidence_score = self.scoring_config.evidence_bonus
            importance_score = importance * self.scoring_config.importance_weight
            confidence_score = confidence * self.scoring_config.confidence_weight
            score = (
                candidate.keyword_score
                + candidate.vector_score
                + candidate.cognee_score
                + importance_score
                + confidence_score
                + recency_score
                + version_freshness
                + layer_bonus
                + evidence_score
            )
            score_breakdown = {
                "signals": {
                    "keyword_score": round(candidate.keyword_score, 3),
                    "vector_score": round(candidate.vector_score, 3),
                    "cognee_score": round(candidate.cognee_score, 3),
                },
                "quality": {
                    "importance": {
                        "value": round(importance, 3),
                        "weight": self.scoring_config.importance_weight,
                        "contribution": round(importance_score, 3),
                    },
                    "confidence": {
                        "value": round(confidence, 3),
                        "weight": self.scoring_config.confidence_weight,
                        "contribution": round(confidence_score, 3),
                    },
                    "recency_score": round(recency_score, 3),
                },
                "bonuses": {
                    "version_freshness": version_freshness,
                    "layer_bonus": layer_bonus,
                    "evidence_score": evidence_score,
                },
                "total": round(score, 3),
            }
            why_ranked = {
                "keyword_score": round(candidate.keyword_score, 3),
                "vector_score": round(candidate.vector_score, 3),
                "cognee_score": round(candidate.cognee_score, 3),
                "importance": round(importance, 3),
                "confidence": round(confidence, 3),
                "recency_score": round(recency_score, 3),
                "version_freshness": version_freshness,
                "layer_bonus": layer_bonus,
                "evidence_complete": evidence_complete,
                "score_breakdown": score_breakdown,
                "score_thresholds": {
                    "vector_min_similarity": self.scoring_config.vector_min_similarity,
                    "hot_layer_min_score": self.scoring_config.hot_layer_min_score,
                    "requires_active_status": True,
                    "requires_evidence": True,
                    "stale_shadow_filter_enabled": self.scoring_config.stale_shadow_filter_enabled,
                    "stale_shadow_min_anchor_overlap": self.scoring_config.stale_shadow_min_anchor_overlap,
                },
                "filtering": {
                    "status": "kept",
                    "reasons": [],
                },
            }
            ranked.append(
                replace(
                    candidate.result,
                    score=round(score, 3),
                    matched_via=candidate.match_list(),
                    why_ranked=why_ranked,
                )
            )

        ordered = sorted(ranked, key=lambda item: (-item.score, item.rank, item.memory_id))
        filtered, dropped_shadowed = self._filter_shadowed_stale_results(ordered, query=query)
        return [replace(result, rank=index) for index, result in enumerate(filtered, start=1)], dropped_missing_evidence, dropped_shadowed

    def _filter_shadowed_stale_results(self, ordered: list[MemoryResult], *, query: str) -> tuple[list[MemoryResult], int]:
        if not self.scoring_config.stale_shadow_filter_enabled or len(ordered) < 2:
            return ordered, 0

        kept: list[MemoryResult] = []
        dropped = 0
        anchors = _anchor_tokens(query)
        for result in ordered:
            shadowing_result = next(
                (
                    prior
                    for prior in kept
                    if _is_shadowed_by_newer_result(
                        stale_candidate=result,
                        newer_candidate=prior,
                        anchors=anchors,
                        min_anchor_overlap=self.scoring_config.stale_shadow_min_anchor_overlap,
                    )
                ),
                None,
            )
            if shadowing_result is None:
                kept.append(result)
                continue

            dropped += 1
            result.why_ranked["filtering"] = {
                "status": "dropped",
                "reasons": ["shadowed_by_higher_ranked_current_update"],
                "shadowed_by_memory_id": shadowing_result.memory_id,
            }
        return kept, dropped

    def _trace_step(
        self,
        request: SearchRequest,
        layer: MemoryLayer,
        *,
        stage: str,
        backend: str,
        returned_count: int,
        hit_memory_ids: list[str],
        note: str | None,
        selection_reason: str,
        dropped_count: int = 0,
    ) -> RetrievalTraceStep:
        return RetrievalTraceStep(
            layer=layer.value,
            backend=backend,
            query=request.query,
            requested_top_k=request.top_k,
            returned_count=returned_count,
            elapsed_ms=0.0,
            hit_memory_ids=hit_memory_ids,
            note=note,
            layer_source="adapter_simulated",
            selection_reason=selection_reason,
            dropped_count=dropped_count,
            stage=stage,
        )


def rerank_results(results: list[MemoryResult]) -> list[MemoryResult]:
    ordered = sorted(results, key=lambda item: (-item.score, item.layer, item.rank, item.memory_id))
    return [replace(result, rank=index) for index, result in enumerate(ordered, start=1)]


def _tokens(text: str) -> list[str]:
    lowered = text.lower()
    words = [part for part in lowered.replace("，", " ").replace("。", " ").split() if part]
    cjk_chars = [char for char in lowered if "\u4e00" <= char <= "\u9fff"]
    ascii_chunks = []
    current = []
    for char in lowered:
        if char.isascii() and (char.isalnum() or char in "_./:-"):
            current.append(char)
        elif current:
            ascii_chunks.append("".join(current))
            current = []
    if current:
        ascii_chunks.append("".join(current))
    return words + cjk_chars + ascii_chunks + _semantic_query_expansions(lowered)


def _semantic_query_expansions(lowered: str) -> list[str]:
    expansions: list[str] = []
    if "coding standards" in lowered or "code standards" in lowered:
        expansions.extend(["代码规范", "规范", "typescript", "type"])
    if "frontend" in lowered or "components" in lowered:
        expansions.extend(["前端", "react", "component", "functional"])
    if "api documentation" in lowered or "documentation format" in lowered:
        expansions.extend(["接口文档", "文档", "swagger", "openapi", "docs/api", "markdown"])
    if "where to store" in lowered:
        expansions.extend(["目录", "放在", "docs/api"])
    if "准备" in lowered:
        expansions.extend(["必须", "规则", "权限", "scope", "配置", "规范", "流程", "checklist"])
    return expansions


def _target_context_value(context: dict[str, Any], field_name: str) -> str:
    value = context.get(field_name)
    if isinstance(value, str) and value:
        return value
    permission = context.get("permission")
    actor = permission.get("actor") if isinstance(permission, dict) else {}
    actor = actor if isinstance(actor, dict) else {}
    value = actor.get(field_name)
    if isinstance(value, str) and value:
        return value
    if field_name == "tenant_id":
        return "tenant:demo"
    if field_name == "organization_id":
        return "org:demo"
    return ""


def _recency_score(now_ms: int, updated_at: int, *, max_score: float = 10.0) -> float:
    if updated_at <= 0:
        return 0.0
    age_days = max((now_ms - updated_at) / 86_400_000, 0.0)
    return max(0.0, max_score - age_days)


def _anchor_tokens(text: str) -> set[str]:
    lowered = text.lower()
    anchors: set[str] = set()

    for token in _tokens(lowered):
        if token.isascii() and len(token) >= 2:
            anchors.add(token)

    cjk_chars = [char for char in lowered if "\u4e00" <= char <= "\u9fff"]
    for index in range(len(cjk_chars) - 1):
        anchors.add("".join(cjk_chars[index : index + 2]))
    for index in range(len(cjk_chars) - 2):
        anchors.add("".join(cjk_chars[index : index + 3]))
    return {anchor for anchor in anchors if anchor not in _ANCHOR_STOPWORDS}


def _result_text(result: MemoryResult) -> str:
    evidence_text = " ".join(str(item.quote or "") for item in result.evidence)
    return f"{result.subject} {result.current_value} {evidence_text}".lower()


def _is_shadowed_by_newer_result(
    *,
    stale_candidate: MemoryResult,
    newer_candidate: MemoryResult,
    anchors: set[str],
    min_anchor_overlap: int,
) -> bool:
    if stale_candidate.memory_id == newer_candidate.memory_id:
        return False
    if stale_candidate.status != "active" or newer_candidate.status != "active":
        return False
    if newer_candidate.score < stale_candidate.score:
        return False

    stale_text = _result_text(stale_candidate)
    newer_text = _result_text(newer_candidate)
    if not _has_update_intent(newer_text):
        return False

    anchor_overlap = {anchor for anchor in anchors if anchor in stale_text and anchor in newer_text}
    if len(anchor_overlap) < min_anchor_overlap:
        return False

    stale_anchors = _anchor_tokens(stale_text)
    newer_anchors = _anchor_tokens(newer_text)
    shared_memory_anchors = stale_anchors & newer_anchors
    return bool(shared_memory_anchors)


def _has_update_intent(text: str) -> bool:
    return any(marker in text for marker in _UPDATE_INTENT_MARKERS)


_ANCHOR_STOPWORDS = {
    "一个",
    "不是",
    "不能",
    "不用",
    "不再",
    "我们",
    "这个",
    "那个",
    "项目",
    "规则",
    "决定",
    "最终",
    "确认",
}

_UPDATE_INTENT_MARKERS = (
    "不对",
    "改成",
    "改到",
    "换成",
    "调到",
    "调回",
    "切回",
    "不用",
    "不再",
    "还是得",
    "最终",
    "统一",
    "迁移",
    "已迁移",
    "变更",
    "已变更",
    "拍板",
    "还是回",
    "回到",
    "instead",
    "switch",
)


def _load_ollama_embedding_provider() -> OllamaEmbeddingProvider | DeterministicEmbeddingProvider:
    """Load OllamaEmbeddingProvider with fallback to DeterministicEmbeddingProvider.

    This function tries to create an OllamaEmbeddingProvider first. If it fails
    (e.g., litellm not available, Ollama not running), it falls back to
    DeterministicEmbeddingProvider.
    """
    provider_name = os.environ.get("EMBEDDING_PROVIDER", "ollama")
    if provider_name != "ollama":
        return create_embedding_provider(provider=provider_name, fallback=True)

    try:
        provider = create_embedding_provider(provider="ollama", fallback=False)
        if isinstance(provider, OllamaEmbeddingProvider):
            return provider
    except Exception as exc:
        # Log at debug level to avoid noise in test environments
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(
            "Failed to create OllamaEmbeddingProvider: %s. Falling back to DeterministicEmbeddingProvider.",
            exc,
        )

    return DeterministicEmbeddingProvider()


def _event_loop_is_running() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


async def _await_value(awaitable: Any) -> Any:
    return await awaitable


def _run_awaitable_sync(awaitable: Any) -> Any:
    if not _event_loop_is_running():
        return asyncio.run(_await_value(awaitable))

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(_await_value(awaitable))
        except BaseException as exc:  # pragma: no cover - re-raised in caller thread
            error["exc"] = exc

    thread = threading.Thread(target=runner, name="copilot-cognee-await", daemon=True)
    thread.start()
    thread.join()
    if "exc" in error:
        raise error["exc"]
    return result.get("value")
