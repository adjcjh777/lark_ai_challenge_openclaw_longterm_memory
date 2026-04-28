from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from memory_engine.models import parse_scope

MAX_TOP_K = 10
DEFAULT_SEARCH_TOP_K = 3
DEFAULT_PREFETCH_TOP_K = 5

MEMORY_TYPES = {"decision", "deadline", "owner", "workflow", "risk", "document", "preference"}
MEMORY_STATUSES = {"candidate", "active", "superseded", "rejected", "stale", "archived"}
MEMORY_LAYERS = {"L1", "L2", "L3"}
WORKING_CONTEXT_FIELDS = {
    "session_id",
    "chat_id",
    "task_id",
    "scope",
    "user_id",
    "tenant_id",
    "organization_id",
    "visibility_policy",
    "document_id",
    "intent",
    "thread_topic",
    "allowed_scopes",
    "metadata",
    "permission",
}

ERROR_CODES = {
    "scope_required",
    "permission_denied",
    "memory_not_found",
    "candidate_not_confirmable",
    "validation_error",
    "sensitive_content_blocked",
    "internal_error",
}

SOURCE_FIELDS = {
    "source_type",
    "source_id",
    "actor_id",
    "created_at",
    "quote",
    "source_url",
    "source_chat_id",
    "source_doc_id",
    "source_task_id",
    "source_meeting_id",
    "source_bitable_app_token",
    "source_bitable_table_id",
    "source_bitable_record_id",
}
SEARCH_FIELDS = {"query", "scope", "top_k", "filters", "current_context"}
SEARCH_FILTER_FIELDS = {"type", "layer", "status"}
CREATE_CANDIDATE_FIELDS = {"text", "scope", "source", "current_context", "auto_confirm"}
CONFIRM_FIELDS = {"candidate_id", "scope", "actor_id", "reason", "current_context"}
REJECT_FIELDS = {"candidate_id", "scope", "actor_id", "reason", "current_context"}
EXPLAIN_VERSIONS_FIELDS = {"memory_id", "scope", "include_archived", "current_context"}
PREFETCH_FIELDS = {"task", "scope", "current_context", "top_k"}
HEARTBEAT_REVIEW_DUE_FIELDS = {"scope", "current_context", "limit"}


class ValidationError(ValueError):
    """Raised when an OpenClaw tool payload does not match the Copilot contract."""


class MemoryLayer(str, Enum):
    WORKING_CONTEXT = "L0"
    HOT = "L1"
    WARM = "L2"
    COLD = "L3"

    @classmethod
    def search_layers(cls) -> list["MemoryLayer"]:
        return [cls.HOT, cls.WARM, cls.COLD]

    @classmethod
    def from_filter(cls, value: str) -> "MemoryLayer":
        for layer in cls.search_layers():
            if layer.value == value:
                return layer
        raise ValidationError(f"filters.layer must be one of: {', '.join(sorted(MEMORY_LAYERS))}")


@dataclass(frozen=True)
class CopilotError:
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_response(self) -> dict[str, Any]:
        if self.code not in ERROR_CODES:
            raise ValidationError(f"unsupported error code: {self.code}")
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
                "details": dict(self.details),
            },
        }


@dataclass(frozen=True)
class WorkingContext:
    session_id: str | None = None
    chat_id: str | None = None
    task_id: str | None = None
    scope: str | None = None
    user_id: str | None = None
    tenant_id: str | None = None
    organization_id: str | None = None
    visibility_policy: str | None = None
    document_id: str | None = None
    intent: str | None = None
    thread_topic: str | None = None
    allowed_scopes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    permission: Any = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any | None) -> "WorkingContext":
        if payload is None:
            return cls()
        data = _require_object(payload, "current_context")
        _reject_unknown_fields(data, WORKING_CONTEXT_FIELDS, "current_context")
        allowed_scopes = data.get("allowed_scopes", [])
        if allowed_scopes is None:
            allowed_scopes = []
        if not isinstance(allowed_scopes, list) or not all(isinstance(item, str) for item in allowed_scopes):
            raise ValidationError("current_context.allowed_scopes must be a list of scope strings")
        metadata = data.get("metadata", {})
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise ValidationError("current_context.metadata must be an object")
        permission = data.get("permission", {})
        return cls(
            session_id=_optional_string(data, "session_id"),
            chat_id=_optional_string(data, "chat_id"),
            task_id=_optional_string(data, "task_id"),
            scope=_optional_string(data, "scope"),
            user_id=_optional_string(data, "user_id"),
            tenant_id=_optional_string(data, "tenant_id"),
            organization_id=_optional_string(data, "organization_id"),
            visibility_policy=_optional_string(data, "visibility_policy"),
            document_id=_optional_string(data, "document_id"),
            intent=_optional_string(data, "intent"),
            thread_topic=_optional_string(data, "thread_topic"),
            allowed_scopes=list(allowed_scopes),
            metadata=dict(metadata),
            permission=dict(permission) if isinstance(permission, dict) else permission,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key in (
            "session_id",
            "chat_id",
            "task_id",
            "scope",
            "user_id",
            "tenant_id",
            "organization_id",
            "visibility_policy",
            "document_id",
            "intent",
            "thread_topic",
        ):
            value = getattr(self, key)
            if value:
                result[key] = value
        if self.allowed_scopes:
            result["allowed_scopes"] = list(self.allowed_scopes)
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        if self.permission:
            result["permission"] = dict(self.permission) if isinstance(self.permission, dict) else self.permission
        return result


@dataclass(frozen=True)
class PermissionActor:
    user_id: str | None
    open_id: str | None
    tenant_id: str
    organization_id: str
    roles: list[str]

    @classmethod
    def from_payload(cls, payload: Any) -> "PermissionActor":
        data = _require_object(payload, "current_context.permission.actor")
        user_id = _optional_string(data, "user_id")
        open_id = _optional_string(data, "open_id")
        if not user_id and not open_id:
            raise ValidationError("current_context.permission.actor.user_id or open_id is required")
        roles = data.get("roles")
        if (
            not isinstance(roles, list)
            or not roles
            or not all(isinstance(item, str) and item.strip() for item in roles)
        ):
            raise ValidationError("current_context.permission.actor.roles must be a non-empty list of strings")
        return cls(
            user_id=user_id,
            open_id=open_id,
            tenant_id=_require_string(data, "tenant_id"),
            organization_id=_require_string(data, "organization_id"),
            roles=[item.strip() for item in roles],
        )

    def primary_id(self) -> str:
        return self.user_id or self.open_id or ""

    def to_dict(self) -> dict[str, Any]:
        result = {
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "roles": list(self.roles),
        }
        if self.user_id:
            result["user_id"] = self.user_id
        if self.open_id:
            result["open_id"] = self.open_id
        return result


@dataclass(frozen=True)
class PermissionSourceContext:
    entrypoint: str
    workspace_id: str | None = None
    chat_id: str | None = None
    document_id: str | None = None

    @classmethod
    def from_payload(cls, payload: Any) -> "PermissionSourceContext":
        data = _require_object(payload, "current_context.permission.source_context")
        return cls(
            entrypoint=_require_string(data, "entrypoint"),
            workspace_id=_optional_string(data, "workspace_id"),
            chat_id=_optional_string(data, "chat_id"),
            document_id=_optional_string(data, "document_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        result = {"entrypoint": self.entrypoint}
        for key in ("workspace_id", "chat_id", "document_id"):
            value = getattr(self, key)
            if value:
                result[key] = value
        return result


@dataclass(frozen=True)
class PermissionContext:
    request_id: str
    trace_id: str
    actor: PermissionActor
    source_context: PermissionSourceContext
    requested_action: str
    requested_visibility: str
    timestamp: str

    @classmethod
    def from_payload(cls, payload: Any) -> "PermissionContext":
        data = _require_object(payload, "current_context.permission")
        return cls(
            request_id=_require_string(data, "request_id"),
            trace_id=_require_string(data, "trace_id"),
            actor=PermissionActor.from_payload(data.get("actor")),
            source_context=PermissionSourceContext.from_payload(data.get("source_context")),
            requested_action=_require_string(data, "requested_action"),
            requested_visibility=_require_string(data, "requested_visibility"),
            timestamp=_require_string(data, "timestamp"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "actor": self.actor.to_dict(),
            "source_context": self.source_context.to_dict(),
            "requested_action": self.requested_action,
            "requested_visibility": self.requested_visibility,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class Evidence:
    source_type: str
    source_id: str | None
    quote: str | None
    source_url: str | None = None
    source_chat_id: str | None = None
    source_doc_id: str | None = None
    source_task_id: str | None = None
    source_meeting_id: str | None = None
    source_bitable_app_token: str | None = None
    source_bitable_table_id: str | None = None
    source_bitable_record_id: str | None = None
    document_token: str | None = None
    document_title: str | None = None

    @classmethod
    def from_repository_source(cls, source: dict[str, Any] | None) -> "Evidence":
        source = source or {}
        return cls(
            source_type=str(source.get("source_type") or "unknown"),
            source_id=source.get("source_id"),
            quote=source.get("quote"),
            document_token=source.get("document_token"),
            document_title=source.get("document_title"),
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "quote": self.quote,
        }
        optional_values = {
            "source_url": self.source_url,
            "source_chat_id": self.source_chat_id,
            "source_doc_id": self.source_doc_id,
            "source_task_id": self.source_task_id,
            "source_meeting_id": self.source_meeting_id,
            "source_bitable_app_token": self.source_bitable_app_token,
            "source_bitable_table_id": self.source_bitable_table_id,
            "source_bitable_record_id": self.source_bitable_record_id,
            "document_token": self.document_token,
            "document_title": self.document_title,
        }
        result.update({key: value for key, value in optional_values.items() if value})
        return result


@dataclass(frozen=True)
class MemoryResult:
    memory_id: str
    type: str
    subject: str
    current_value: str
    status: str
    layer: str
    version: int | None
    score: float
    rank: int
    evidence: list[Evidence] = field(default_factory=list)
    matched_via: list[str] = field(default_factory=list)
    why_ranked: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_repository_candidate(cls, candidate: dict[str, Any]) -> "MemoryResult":
        status = str(candidate.get("status") or "")
        if status not in MEMORY_STATUSES:
            raise ValidationError(f"unsupported memory status from repository: {status}")
        layer = str(candidate.get("layer") or MemoryLayer.WARM.value)
        if layer not in MEMORY_LAYERS:
            raise ValidationError(f"unsupported memory layer from repository: {layer}")
        return cls(
            memory_id=str(candidate["memory_id"]),
            type=str(candidate["type"]),
            subject=str(candidate["subject"]),
            current_value=str(candidate.get("answer") or ""),
            status=status,
            layer=layer,
            version=candidate.get("version"),
            score=float(candidate.get("score") or 0),
            rank=int(candidate.get("rank") or 0),
            evidence=[Evidence.from_repository_source(candidate.get("source"))],
            matched_via=_matched_via(candidate.get("matched_via")),
            why_ranked=dict(candidate.get("why_ranked") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "memory_id": self.memory_id,
            "type": self.type,
            "subject": self.subject,
            "current_value": self.current_value,
            "status": self.status,
            "layer": self.layer,
            "version": self.version,
            "score": self.score,
            "rank": self.rank,
            "evidence": [item.to_dict() for item in self.evidence],
        }
        if self.matched_via:
            result["matched_via"] = list(self.matched_via)
        if self.why_ranked:
            result["why_ranked"] = dict(self.why_ranked)
        return result


@dataclass(frozen=True)
class CandidateMemory:
    candidate_id: str
    type: str
    subject: str
    current_value: str
    status: str = "candidate"
    version: int = 1
    evidence: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        if self.status != "candidate":
            raise ValidationError("CandidateMemory status must remain candidate")
        return {
            "candidate_id": self.candidate_id,
            "type": self.type,
            "subject": self.subject,
            "current_value": self.current_value,
            "status": self.status,
            "version": self.version,
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True)
class RetrievalTraceStep:
    layer: str
    backend: str
    query: str
    requested_top_k: int
    returned_count: int
    elapsed_ms: float = 0.0
    hit_memory_ids: list[str] = field(default_factory=list)
    note: str | None = None
    layer_source: str | None = None
    selection_reason: str | None = None
    dropped_count: int = 0
    stage: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "layer": self.layer,
            "backend": self.backend,
            "query": self.query,
            "requested_top_k": self.requested_top_k,
            "returned_count": self.returned_count,
            "elapsed_ms": self.elapsed_ms,
            "hit_memory_ids": list(self.hit_memory_ids),
        }
        if self.note:
            result["note"] = self.note
        if self.layer_source:
            result["layer_source"] = self.layer_source
        if self.selection_reason:
            result["selection_reason"] = self.selection_reason
        if self.dropped_count:
            result["dropped_count"] = self.dropped_count
        if self.stage:
            result["stage"] = self.stage
        return result


@dataclass(frozen=True)
class RetrievalTrace:
    strategy: str
    query: str
    scope: str
    requested_top_k: int
    returned_count: int
    backend: str
    steps: list[RetrievalTraceStep] = field(default_factory=list)
    final_reason: str = "top_k_reranked_with_evidence"
    fallback_used: bool = False
    cognee_available: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        layers: list[str] = []
        for step in self.steps:
            if step.layer in MEMORY_LAYERS and step.layer not in layers:
                layers.append(step.layer)
        return {
            "strategy": self.strategy,
            "query": self.query,
            "scope": self.scope,
            "requested_top_k": self.requested_top_k,
            "returned_count": self.returned_count,
            "backend": self.backend,
            "layers": layers,
            "stages": [step.stage for step in self.steps if step.stage],
            "steps": [step.to_dict() for step in self.steps],
            "final_reason": self.final_reason,
            "fallback_used": self.fallback_used,
            "cognee_available": self.cognee_available,
        }


RecallTrace = RetrievalTrace


@dataclass(frozen=True)
class SearchResponse:
    query: str
    scope: str
    top_k: int
    results: list[MemoryResult]
    trace: RetrievalTrace

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": True,
            "query": self.query,
            "scope": self.scope,
            "top_k": self.top_k,
            "results": [result.to_dict() for result in self.results],
            "trace": self.trace.to_dict(),
        }


@dataclass(frozen=True)
class CandidateSource:
    source_type: str
    source_id: str
    actor_id: str
    created_at: str
    quote: str
    source_url: str | None = None
    source_chat_id: str | None = None
    source_doc_id: str | None = None
    source_task_id: str | None = None
    source_meeting_id: str | None = None
    source_bitable_app_token: str | None = None
    source_bitable_table_id: str | None = None
    source_bitable_record_id: str | None = None

    @classmethod
    def from_payload(cls, payload: Any) -> "CandidateSource":
        data = _require_object(payload, "source")
        _reject_unknown_fields(data, SOURCE_FIELDS, "source")
        return cls(
            source_type=_require_string(data, "source_type"),
            source_id=_require_string(data, "source_id"),
            actor_id=_require_string(data, "actor_id"),
            created_at=_require_string(data, "created_at"),
            quote=_require_string(data, "quote"),
            source_url=_optional_string(data, "source_url"),
            source_chat_id=_optional_string(data, "source_chat_id"),
            source_doc_id=_optional_string(data, "source_doc_id"),
            source_task_id=_optional_string(data, "source_task_id"),
            source_meeting_id=_optional_string(data, "source_meeting_id"),
            source_bitable_app_token=_optional_string(data, "source_bitable_app_token"),
            source_bitable_table_id=_optional_string(data, "source_bitable_table_id"),
            source_bitable_record_id=_optional_string(data, "source_bitable_record_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "actor_id": self.actor_id,
            "created_at": self.created_at,
            "quote": self.quote,
        }
        if self.source_chat_id:
            result["source_chat_id"] = self.source_chat_id
        if self.source_doc_id:
            result["source_doc_id"] = self.source_doc_id
        if self.source_url:
            result["source_url"] = self.source_url
        if self.source_task_id:
            result["source_task_id"] = self.source_task_id
        if self.source_meeting_id:
            result["source_meeting_id"] = self.source_meeting_id
        if self.source_bitable_app_token:
            result["source_bitable_app_token"] = self.source_bitable_app_token
        if self.source_bitable_table_id:
            result["source_bitable_table_id"] = self.source_bitable_table_id
        if self.source_bitable_record_id:
            result["source_bitable_record_id"] = self.source_bitable_record_id
        return result


@dataclass(frozen=True)
class SearchRequest:
    query: str
    scope: str
    top_k: int = DEFAULT_SEARCH_TOP_K
    filters: dict[str, Any] = field(default_factory=lambda: {"status": "active"})
    current_context: WorkingContext = field(default_factory=WorkingContext)

    @classmethod
    def from_payload(cls, payload: Any) -> "SearchRequest":
        data = _require_object(payload, "payload")
        _reject_unknown_fields(data, SEARCH_FIELDS, "memory.search")
        scope = _require_scope(data)
        filters = _search_filters(data)
        if "status" not in filters:
            filters["status"] = "active"
        return cls(
            query=_require_string(data, "query"),
            scope=scope,
            top_k=_top_k(data.get("top_k"), default=DEFAULT_SEARCH_TOP_K),
            filters=filters,
            current_context=WorkingContext.from_payload(data.get("current_context")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "scope": self.scope,
            "top_k": self.top_k,
            "filters": dict(self.filters),
            "current_context": self.current_context.to_dict(),
        }


@dataclass(frozen=True)
class CreateCandidateRequest:
    text: str
    scope: str
    source: CandidateSource
    current_context: dict[str, Any] = field(default_factory=dict)
    auto_confirm: bool = False

    @classmethod
    def from_payload(cls, payload: Any) -> "CreateCandidateRequest":
        data = _require_object(payload, "payload")
        _reject_unknown_fields(data, CREATE_CANDIDATE_FIELDS, "memory.create_candidate")
        return cls(
            text=_require_string(data, "text"),
            scope=_require_scope(data),
            source=CandidateSource.from_payload(data.get("source")),
            current_context=_optional_object(data, "current_context"),
            auto_confirm=_optional_bool(data, "auto_confirm", default=False),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "scope": self.scope,
            "source": self.source.to_dict(),
            "current_context": dict(self.current_context),
            "auto_confirm": self.auto_confirm,
        }


@dataclass(frozen=True)
class ConfirmRequest:
    candidate_id: str
    scope: str
    actor_id: str
    reason: str | None = None
    current_context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "ConfirmRequest":
        data = _require_object(payload, "payload")
        _reject_unknown_fields(data, CONFIRM_FIELDS, "memory.confirm")
        current_context = _optional_object(data, "current_context")
        return cls(
            candidate_id=_require_string(data, "candidate_id"),
            scope=_require_scope(data),
            actor_id=_optional_string(data, "actor_id") or _actor_id_from_context(current_context) or "",
            reason=_optional_string(data, "reason"),
            current_context=current_context,
        )


@dataclass(frozen=True)
class RejectRequest:
    candidate_id: str
    scope: str
    actor_id: str
    reason: str | None = None
    current_context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "RejectRequest":
        data = _require_object(payload, "payload")
        _reject_unknown_fields(data, REJECT_FIELDS, "memory.reject")
        current_context = _optional_object(data, "current_context")
        return cls(
            candidate_id=_require_string(data, "candidate_id"),
            scope=_require_scope(data),
            actor_id=_optional_string(data, "actor_id") or _actor_id_from_context(current_context) or "",
            reason=_optional_string(data, "reason"),
            current_context=current_context,
        )


@dataclass(frozen=True)
class ExplainVersionsRequest:
    memory_id: str
    scope: str
    include_archived: bool = False
    current_context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "ExplainVersionsRequest":
        data = _require_object(payload, "payload")
        _reject_unknown_fields(data, EXPLAIN_VERSIONS_FIELDS, "memory.explain_versions")
        return cls(
            memory_id=_require_string(data, "memory_id"),
            scope=_require_scope(data),
            include_archived=_optional_bool(data, "include_archived", default=False),
            current_context=_optional_object(data, "current_context"),
        )


@dataclass(frozen=True)
class PrefetchRequest:
    task: str
    scope: str
    current_context: dict[str, Any]
    top_k: int = DEFAULT_PREFETCH_TOP_K

    @classmethod
    def from_payload(cls, payload: Any) -> "PrefetchRequest":
        data = _require_object(payload, "payload")
        _reject_unknown_fields(data, PREFETCH_FIELDS, "memory.prefetch")
        current_context = _require_non_empty_object(data, "current_context")
        return cls(
            task=_require_string(data, "task"),
            scope=_require_scope(data),
            current_context=current_context,
            top_k=_top_k(data.get("top_k"), default=DEFAULT_PREFETCH_TOP_K),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "scope": self.scope,
            "current_context": dict(self.current_context),
            "top_k": self.top_k,
        }


@dataclass(frozen=True)
class HeartbeatReviewDueRequest:
    scope: str
    current_context: dict[str, Any] = field(default_factory=dict)
    limit: int = 5

    @classmethod
    def from_payload(cls, payload: Any) -> "HeartbeatReviewDueRequest":
        data = _require_object(payload, "payload")
        _reject_unknown_fields(data, HEARTBEAT_REVIEW_DUE_FIELDS, "heartbeat.review_due")
        return cls(
            scope=_require_scope(data),
            current_context=_optional_object(data, "current_context"),
            limit=_limit(data.get("limit"), default=5),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "current_context": dict(self.current_context),
            "limit": self.limit,
        }


def _require_object(payload: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValidationError(f"{field_name} must be an object")
    return dict(payload)


def _optional_object(data: dict[str, Any], field_name: str) -> dict[str, Any]:
    value = data.get(field_name)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValidationError(f"{field_name} must be an object")
    return dict(value)


def _require_non_empty_object(data: dict[str, Any], field_name: str) -> dict[str, Any]:
    if field_name not in data:
        raise ValidationError(f"{field_name} is required")
    value = _optional_object(data, field_name)
    if not value:
        raise ValidationError(f"{field_name} must be a non-empty object")
    return value


def _require_string(data: dict[str, Any], field_name: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} is required")
    return value.strip()


def _optional_string(data: dict[str, Any], field_name: str) -> str | None:
    value = data.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string")
    value = value.strip()
    return value or None


def _optional_bool(data: dict[str, Any], field_name: str, *, default: bool) -> bool:
    value = data.get(field_name, default)
    if not isinstance(value, bool):
        raise ValidationError(f"{field_name} must be a boolean")
    return value


def _require_scope(data: dict[str, Any]) -> str:
    scope = _require_string(data, "scope")
    try:
        parse_scope(scope)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return scope


def _reject_unknown_fields(data: dict[str, Any], allowed_fields: set[str], context: str) -> None:
    unknown_fields = sorted(set(data) - allowed_fields)
    if unknown_fields:
        joined = ", ".join(unknown_fields)
        raise ValidationError(f"{context} contains unsupported field(s): {joined}")


def _search_filters(data: dict[str, Any]) -> dict[str, Any]:
    filters = _optional_object(data, "filters")
    _reject_unknown_fields(filters, SEARCH_FILTER_FIELDS, "memory.search.filters")
    if "type" in filters and filters["type"] not in MEMORY_TYPES:
        raise ValidationError(f"filters.type must be one of: {', '.join(sorted(MEMORY_TYPES))}")
    if "layer" in filters and filters["layer"] not in MEMORY_LAYERS:
        raise ValidationError(f"filters.layer must be one of: {', '.join(sorted(MEMORY_LAYERS))}")
    if "status" in filters and filters["status"] not in MEMORY_STATUSES:
        raise ValidationError(f"filters.status must be one of: {', '.join(sorted(MEMORY_STATUSES))}")
    return filters


def _actor_id_from_context(current_context: dict[str, Any]) -> str | None:
    permission = current_context.get("permission")
    if not isinstance(permission, dict):
        return None
    actor = permission.get("actor")
    if not isinstance(actor, dict):
        return None
    user_id = actor.get("user_id")
    if isinstance(user_id, str) and user_id.strip():
        return user_id.strip()
    open_id = actor.get("open_id")
    if isinstance(open_id, str) and open_id.strip():
        return open_id.strip()
    return None


def _matched_via(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    return []


def _top_k(value: Any, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError("top_k must be an integer")
    if value < 1:
        raise ValidationError("top_k must be at least 1")
    if value > MAX_TOP_K:
        raise ValidationError(f"top_k cannot exceed {MAX_TOP_K}")
    return value


def _limit(value: Any, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError("limit must be an integer")
    if value < 1:
        raise ValidationError("limit must be at least 1")
    if value > MAX_TOP_K:
        raise ValidationError(f"limit cannot exceed {MAX_TOP_K}")
    return value
