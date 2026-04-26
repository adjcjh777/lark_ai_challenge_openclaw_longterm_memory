from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from memory_engine.models import parse_scope


MAX_TOP_K = 10
DEFAULT_SEARCH_TOP_K = 3
DEFAULT_PREFETCH_TOP_K = 5

MEMORY_TYPES = {"decision", "deadline", "owner", "workflow", "risk", "document", "preference"}
MEMORY_STATUSES = {"candidate", "active", "superseded", "rejected", "stale", "archived"}
MEMORY_LAYERS = {"L1", "L2", "L3"}

ERROR_CODES = {
    "scope_required",
    "permission_denied",
    "memory_not_found",
    "candidate_not_confirmable",
    "validation_error",
    "sensitive_content_blocked",
    "internal_error",
}


class ValidationError(ValueError):
    """Raised when an OpenClaw tool payload does not match the Copilot contract."""


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
class CandidateSource:
    source_type: str
    source_id: str
    actor_id: str
    created_at: str
    quote: str
    source_chat_id: str | None = None
    source_doc_id: str | None = None

    @classmethod
    def from_payload(cls, payload: Any) -> "CandidateSource":
        data = _require_object(payload, "source")
        return cls(
            source_type=_require_string(data, "source_type"),
            source_id=_require_string(data, "source_id"),
            actor_id=_require_string(data, "actor_id"),
            created_at=_require_string(data, "created_at"),
            quote=_require_string(data, "quote"),
            source_chat_id=_optional_string(data, "source_chat_id"),
            source_doc_id=_optional_string(data, "source_doc_id"),
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
        return result


@dataclass(frozen=True)
class SearchRequest:
    query: str
    scope: str
    top_k: int = DEFAULT_SEARCH_TOP_K
    filters: dict[str, Any] = field(default_factory=lambda: {"status": "active"})
    current_context: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Any) -> "SearchRequest":
        data = _require_object(payload, "payload")
        scope = _require_scope(data)
        filters = _optional_object(data, "filters")
        if "status" not in filters:
            filters["status"] = "active"
        return cls(
            query=_require_string(data, "query"),
            scope=scope,
            top_k=_top_k(data.get("top_k"), default=DEFAULT_SEARCH_TOP_K),
            filters=filters,
            current_context=_optional_object(data, "current_context"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "scope": self.scope,
            "top_k": self.top_k,
            "filters": dict(self.filters),
            "current_context": dict(self.current_context),
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
        return cls(
            text=_require_string(data, "text"),
            scope=_require_scope(data),
            source=CandidateSource.from_payload(data.get("source")),
            current_context=_optional_object(data, "current_context"),
            auto_confirm=bool(data.get("auto_confirm", False)),
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

    @classmethod
    def from_payload(cls, payload: Any) -> "ConfirmRequest":
        data = _require_object(payload, "payload")
        return cls(
            candidate_id=_require_string(data, "candidate_id"),
            scope=_require_scope(data),
            actor_id=_require_string(data, "actor_id"),
            reason=_optional_string(data, "reason"),
        )


@dataclass(frozen=True)
class RejectRequest:
    candidate_id: str
    scope: str
    actor_id: str
    reason: str | None = None

    @classmethod
    def from_payload(cls, payload: Any) -> "RejectRequest":
        data = _require_object(payload, "payload")
        return cls(
            candidate_id=_require_string(data, "candidate_id"),
            scope=_require_scope(data),
            actor_id=_require_string(data, "actor_id"),
            reason=_optional_string(data, "reason"),
        )


@dataclass(frozen=True)
class ExplainVersionsRequest:
    memory_id: str
    scope: str
    include_archived: bool = False

    @classmethod
    def from_payload(cls, payload: Any) -> "ExplainVersionsRequest":
        data = _require_object(payload, "payload")
        return cls(
            memory_id=_require_string(data, "memory_id"),
            scope=_require_scope(data),
            include_archived=bool(data.get("include_archived", False)),
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
        current_context = _optional_object(data, "current_context")
        if not current_context:
            raise ValidationError("current_context is required")
        return cls(
            task=_require_string(data, "task"),
            scope=_require_scope(data),
            current_context=current_context,
            top_k=_top_k(data.get("top_k"), default=DEFAULT_PREFETCH_TOP_K),
        )


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


def _require_scope(data: dict[str, Any]) -> str:
    scope = _require_string(data, "scope")
    try:
        parse_scope(scope)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return scope


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
