from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Callable

from .schemas import (
    ConfirmRequest,
    CopilotError,
    CreateCandidateRequest,
    ExplainVersionsRequest,
    PrefetchRequest,
    RejectRequest,
    SearchRequest,
    ValidationError,
)


REQUEST_TYPES: dict[str, Callable[[Any], Any]] = {
    "memory.search": SearchRequest.from_payload,
    "memory.create_candidate": CreateCandidateRequest.from_payload,
    "memory.confirm": ConfirmRequest.from_payload,
    "memory.reject": RejectRequest.from_payload,
    "memory.explain_versions": ExplainVersionsRequest.from_payload,
    "memory.prefetch": PrefetchRequest.from_payload,
}


def supported_tool_names() -> list[str]:
    return sorted(REQUEST_TYPES)


def error_response(
    code: str,
    message: str,
    *,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return CopilotError(code=code, message=message, retryable=retryable, details=details or {}).to_response()


def validate_tool_request(tool_name: str, payload: Any) -> dict[str, Any]:
    """Parse and validate a tool request payload.

    This is intentionally a request-parser envelope, not the final OpenClaw
    tool response. Service handlers will convert parsed requests into
    tool-specific outputs such as search results, candidates, and traces.
    """

    parser = REQUEST_TYPES.get(tool_name)
    if parser is None:
        return error_response(
            "validation_error",
            f"unsupported memory tool: {tool_name}",
            details={"supported_tools": supported_tool_names()},
        )

    try:
        request = parser(payload)
    except ValidationError as exc:
        return error_response("validation_error", str(exc), details={"tool": tool_name})

    return {
        "ok": True,
        "tool": tool_name,
        "parsed_request": _to_plain_dict(request),
    }


def _to_plain_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    raise TypeError(f"cannot serialize request value: {type(value).__name__}")
