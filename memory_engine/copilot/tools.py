from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Callable

from .schemas import (
    ConfirmRequest,
    CopilotError,
    CreateCandidateRequest,
    ExplainVersionsRequest,
    HeartbeatReviewDueRequest,
    PrefetchRequest,
    PermissionContext,
    RejectRequest,
    SearchRequest,
    ValidationError,
)
from .service import CopilotService


BRIDGE_VISIBILITIES = {"private", "team", "organization", "tenant", "public_demo"}

REQUEST_TYPES: dict[str, Callable[[Any], Any]] = {
    "memory.search": SearchRequest.from_payload,
    "memory.create_candidate": CreateCandidateRequest.from_payload,
    "memory.confirm": ConfirmRequest.from_payload,
    "memory.reject": RejectRequest.from_payload,
    "memory.explain_versions": ExplainVersionsRequest.from_payload,
    "memory.prefetch": PrefetchRequest.from_payload,
    "heartbeat.review_due": HeartbeatReviewDueRequest.from_payload,
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


def handle_tool_request(tool_name: str, payload: Any, *, service: CopilotService | None = None) -> dict[str, Any]:
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
        if tool_name in {"memory.search", "memory.prefetch"} and str(exc) == "scope is required":
            return error_response("scope_required", "scope is required", details={"tool": tool_name})
        return error_response("validation_error", str(exc), details={"tool": tool_name})

    copilot_service = service or CopilotService()
    if tool_name == "memory.search":
        return _with_bridge_metadata(copilot_service.search(request), tool_name, request)
    if tool_name == "memory.create_candidate":
        return _with_bridge_metadata(copilot_service.create_candidate(request), tool_name, request)
    if tool_name == "memory.confirm":
        return _with_bridge_metadata(copilot_service.confirm(request), tool_name, request)
    if tool_name == "memory.reject":
        return _with_bridge_metadata(copilot_service.reject(request), tool_name, request)
    if tool_name == "memory.explain_versions":
        return _with_bridge_metadata(copilot_service.explain_versions(request), tool_name, request)
    if tool_name == "memory.prefetch":
        return _with_bridge_metadata(copilot_service.prefetch(request), tool_name, request)
    if tool_name == "heartbeat.review_due":
        return _with_bridge_metadata(copilot_service.heartbeat_review_due(request), tool_name, request)

    return error_response(
        "validation_error",
        f"{tool_name} is declared but not implemented in the 2026-04-27 MVP slice",
        details={"tool": tool_name},
    )


def _to_plain_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    raise TypeError(f"cannot serialize request value: {type(value).__name__}")


def _with_bridge_metadata(response: dict[str, Any], tool_name: str, request: Any) -> dict[str, Any]:
    """Attach stable OpenClaw bridge metadata without changing service ownership."""

    bridged = dict(response)
    bridged["bridge"] = _bridge_metadata(tool_name, request, response)
    return bridged


def _bridge_metadata(tool_name: str, request: Any, response: dict[str, Any]) -> dict[str, Any]:
    context = _request_context(request)
    permission_payload = context.get("permission")
    permission = _parse_permission(permission_payload)

    metadata: dict[str, Any] = {
        "entrypoint": "openclaw_tool",
        "tool": tool_name,
        "permission_decision": _permission_decision(response, tool_name, permission_payload, permission),
    }
    request_id = _permission_field(permission_payload, permission, "request_id")
    trace_id = _permission_field(permission_payload, permission, "trace_id")
    if request_id:
        metadata["request_id"] = request_id
    if trace_id:
        metadata["trace_id"] = trace_id
    return metadata


def _request_context(request: Any) -> dict[str, Any]:
    context = getattr(request, "current_context", {})
    if hasattr(context, "to_dict"):
        context = context.to_dict()
    return dict(context) if isinstance(context, dict) else {}


def _parse_permission(permission_payload: Any) -> PermissionContext | None:
    if not isinstance(permission_payload, dict):
        return None
    try:
        return PermissionContext.from_payload(permission_payload)
    except ValidationError:
        return None


def _permission_decision(
    response: dict[str, Any],
    tool_name: str,
    permission_payload: Any,
    permission: PermissionContext | None,
) -> dict[str, Any]:
    error = response.get("error") if isinstance(response.get("error"), dict) else {}
    error_details = error.get("details") if isinstance(error.get("details"), dict) else {}
    denied = error.get("code") == "permission_denied"
    reason_code = error_details.get("reason_code") or ("permission_denied" if denied else "scope_access_granted")
    summary: dict[str, Any] = {
        "decision": "deny" if denied else "allow",
        "reason_code": str(reason_code),
        "requested_action": _schema_safe_action(_permission_field(permission_payload, permission, "requested_action"), tool_name),
    }
    requested_visibility = _permission_field(permission_payload, permission, "requested_visibility")
    if requested_visibility in BRIDGE_VISIBILITIES:
        summary["requested_visibility"] = requested_visibility
    actor = _permission_actor(permission_payload, permission)
    if actor:
        summary["actor"] = actor
    source_entrypoint = _source_entrypoint(permission_payload, permission)
    if source_entrypoint:
        summary["source_entrypoint"] = source_entrypoint
    return summary


def _permission_field(permission_payload: Any, permission: PermissionContext | None, field_name: str) -> str | None:
    if permission is not None:
        value = getattr(permission, field_name)
        return value if isinstance(value, str) and value else None
    if isinstance(permission_payload, dict):
        value = permission_payload.get(field_name)
        return value if isinstance(value, str) and value else None
    return None


def _schema_safe_action(value: str | None, fallback: str) -> str:
    if value in REQUEST_TYPES:
        return value
    return fallback


def _permission_actor(permission_payload: Any, permission: PermissionContext | None) -> dict[str, Any]:
    if permission is not None:
        return permission.actor.to_dict()
    if not isinstance(permission_payload, dict):
        return {}
    actor = permission_payload.get("actor")
    if not isinstance(actor, dict):
        return {}
    safe_actor: dict[str, Any] = {}
    for key in ("user_id", "open_id", "tenant_id", "organization_id"):
        value = actor.get(key)
        if isinstance(value, str) and value:
            safe_actor[key] = value
    roles = actor.get("roles")
    if isinstance(roles, list) and all(isinstance(role, str) for role in roles):
        safe_actor["roles"] = list(roles)
    return safe_actor


def _source_entrypoint(permission_payload: Any, permission: PermissionContext | None) -> str | None:
    if permission is not None:
        return permission.source_context.entrypoint
    if not isinstance(permission_payload, dict):
        return None
    source_context = permission_payload.get("source_context")
    if not isinstance(source_context, dict):
        return None
    entrypoint = source_context.get("entrypoint")
    return entrypoint if isinstance(entrypoint, str) and entrypoint else None
