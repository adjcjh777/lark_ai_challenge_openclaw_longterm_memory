from __future__ import annotations

from pathlib import Path

from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository

from .cognee_adapter import CogneeMemoryAdapter
from .governance import CopilotGovernance
from .orchestrator import MemorySearchOrchestrator
from .permissions import check_scope_access
from .retrieval import LayerAwareRetriever
from .schemas import (
    ConfirmRequest,
    CreateCandidateRequest,
    ExplainVersionsRequest,
    PrefetchRequest,
    RejectRequest,
    SearchRequest,
    WorkingContext,
    WORKING_CONTEXT_FIELDS,
)


class CopilotService:
    """Application service for Copilot-owned memory contracts."""

    def __init__(
        self,
        *,
        repository: MemoryRepository | None = None,
        db_path: str | Path | None = None,
        cognee_adapter: CogneeMemoryAdapter | None = None,
    ) -> None:
        self.repository = repository
        self.db_path = db_path
        self.cognee_adapter = cognee_adapter

    def search(self, request: SearchRequest) -> dict[str, object]:
        permission_error = check_scope_access(request.scope, request.current_context.to_dict())
        if permission_error is not None:
            return permission_error.to_response()

        retriever = LayerAwareRetriever(self._repository(), cognee_adapter=self.cognee_adapter)
        orchestrator = MemorySearchOrchestrator(
            retriever,
            cognee_available=self.cognee_adapter is not None and self.cognee_adapter.is_configured,
        )
        return orchestrator.search(request).to_dict()

    def create_candidate(self, request: CreateCandidateRequest) -> dict[str, object]:
        permission_error = check_scope_access(request.scope, request.current_context)
        if permission_error is not None:
            return permission_error.to_response()
        return CopilotGovernance(self._repository()).create_candidate(request)

    def confirm(self, request: ConfirmRequest) -> dict[str, object]:
        return CopilotGovernance(self._repository()).confirm(request)

    def reject(self, request: RejectRequest) -> dict[str, object]:
        return CopilotGovernance(self._repository()).reject(request)

    def explain_versions(self, request: ExplainVersionsRequest) -> dict[str, object]:
        return CopilotGovernance(self._repository()).explain_versions(request)

    def prefetch(self, request: PrefetchRequest) -> dict[str, object]:
        permission_error = check_scope_access(request.scope, request.current_context)
        if permission_error is not None:
            return permission_error.to_response()

        search_request = SearchRequest(
            query=_prefetch_query(request.task, request.current_context),
            scope=request.scope,
            top_k=request.top_k,
            filters={"status": "active"},
            current_context=WorkingContext.from_payload(_working_context_only(request.current_context) or None),
        )
        search_response = self.search(search_request)
        if not search_response.get("ok"):
            return search_response

        results = list(search_response.get("results") or [])
        trace = dict(search_response.get("trace") or {})
        relevant = [_compact_memory(result) for result in results]
        risks = [item for item in relevant if item.get("type") == "risk" or _mentions_risk(item.get("current_value"))]
        deadlines = [item for item in relevant if item.get("type") == "deadline" or _mentions_deadline(item.get("current_value"))]
        return {
            "ok": True,
            "tool": "memory.prefetch",
            "task": request.task,
            "scope": request.scope,
            "top_k": request.top_k,
            "context_pack": {
                "summary": _prefetch_summary(request.task, relevant, risks, deadlines),
                "relevant_memories": relevant,
                "risks": risks,
                "deadlines": deadlines,
                "version_status": [
                    {
                        "memory_id": item.get("memory_id"),
                        "status": item.get("status"),
                        "version": item.get("version"),
                    }
                    for item in relevant
                ],
                "trace_summary": {
                    "strategy": trace.get("strategy"),
                    "layers": trace.get("layers") or [],
                    "returned_count": trace.get("returned_count", len(relevant)),
                    "final_reason": trace.get("final_reason"),
                    "matched_memory_ids": [item.get("memory_id") for item in relevant],
                },
                "stale_superseded_filtered": True,
                "raw_events_included": False,
            },
            "state_mutation": "none",
        }

    def _repository(self) -> MemoryRepository:
        if self.repository is not None:
            return self.repository
        conn = connect(self.db_path)
        init_db(conn)
        self.repository = MemoryRepository(conn)
        return self.repository


def _working_context_only(context: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in context.items() if key in WORKING_CONTEXT_FIELDS}


def _prefetch_query(task: str, context: dict[str, object]) -> str:
    parts = [task]
    for key in ("intent", "thread_topic", "current_message", "task"):
        value = context.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    metadata = context.get("metadata")
    if isinstance(metadata, dict):
        parts.extend(str(value) for value in metadata.values() if isinstance(value, str) and value.strip())
    return " ".join(parts)


def _compact_memory(memory: dict[str, object]) -> dict[str, object]:
    evidence = memory.get("evidence") if isinstance(memory.get("evidence"), list) else []
    compact_evidence = []
    for item in evidence[:2]:
        if not isinstance(item, dict):
            continue
        compact_evidence.append(
            {
                "source_type": item.get("source_type"),
                "source_id": item.get("source_id"),
                "quote": item.get("quote"),
            }
        )
    return {
        "memory_id": memory.get("memory_id"),
        "type": memory.get("type"),
        "subject": memory.get("subject"),
        "current_value": memory.get("current_value"),
        "status": memory.get("status"),
        "layer": memory.get("layer"),
        "version": memory.get("version"),
        "score": memory.get("score"),
        "evidence": compact_evidence,
        "matched_via": memory.get("matched_via") or [],
        "why_ranked": memory.get("why_ranked") or {},
    }


def _mentions_risk(value: object) -> bool:
    text = str(value or "").lower()
    return any(keyword in text for keyword in ("risk", "风险", "blocked", "blocker"))


def _mentions_deadline(value: object) -> bool:
    text = str(value or "")
    return "deadline" in text.lower() or "截止" in text or "上线前" in text


def _prefetch_summary(
    task: str,
    relevant: list[dict[str, object]],
    risks: list[dict[str, object]],
    deadlines: list[dict[str, object]],
) -> str:
    if not relevant:
        return f"{task}: 未找到可带入任务上下文的 active 记忆。"
    parts = [f"{task}: 找到 {len(relevant)} 条可带入任务前上下文的 active 记忆"]
    if risks:
        parts.append(f"{len(risks)} 条风险")
    if deadlines:
        parts.append(f"{len(deadlines)} 条截止时间")
    return "，".join(parts) + "。"
