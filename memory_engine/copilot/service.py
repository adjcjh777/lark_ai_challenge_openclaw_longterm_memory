from __future__ import annotations

from pathlib import Path

from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository

from .cognee_adapter import CogneeMemoryAdapter
from .governance import CopilotGovernance
from .orchestrator import MemorySearchOrchestrator
from .permissions import check_scope_access
from .retrieval import LayerAwareRetriever
from .schemas import ConfirmRequest, CreateCandidateRequest, ExplainVersionsRequest, RejectRequest, SearchRequest


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

    def _repository(self) -> MemoryRepository:
        if self.repository is not None:
            return self.repository
        conn = connect(self.db_path)
        init_db(conn)
        self.repository = MemoryRepository(conn)
        return self.repository
