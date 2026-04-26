from __future__ import annotations

from pathlib import Path

from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository

from .cognee_adapter import CogneeMemoryAdapter
from .permissions import check_scope_access
from .schemas import MemoryResult, RecallTrace, SearchRequest, SearchResponse


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
        permission_error = check_scope_access(request.scope, request.current_context)
        if permission_error is not None:
            return permission_error.to_response()

        repository = self._repository()
        candidates = repository.recall_candidates(request.scope, request.query, limit=request.top_k)
        results = [
            MemoryResult.from_repository_candidate(candidate)
            for candidate in candidates
            if candidate.get("status") == request.filters.get("status", "active")
        ]

        trace = RecallTrace(
            strategy="repository.recall_candidates",
            query=request.query,
            scope=request.scope,
            requested_top_k=request.top_k,
            returned_count=len(results),
            fallback_used=True,
            cognee_available=self.cognee_adapter is not None and self.cognee_adapter.is_configured,
        )
        return SearchResponse(
            query=request.query,
            scope=request.scope,
            top_k=request.top_k,
            results=results,
            trace=trace,
        ).to_dict()

    def _repository(self) -> MemoryRepository:
        if self.repository is not None:
            return self.repository
        conn = connect(self.db_path)
        init_db(conn)
        self.repository = MemoryRepository(conn)
        return self.repository
