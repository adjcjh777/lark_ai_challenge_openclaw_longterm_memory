from __future__ import annotations

import re
from typing import Any

from .schemas import CopilotError, PermissionContext, ValidationError

_SENSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("api_key", re.compile(r"(?i)\b(api[_-]?key|apikey)\s*[:=]\s*['\"]?[A-Za-z0-9._-]{8,}")),
    ("app_secret", re.compile(r"(?i)\b(app[_-]?secret|secret)\s*[:=]\s*['\"]?[A-Za-z0-9._-]{8,}")),
    ("password", re.compile(r"(?i)\b(password|passwd|pwd)\s*[:=]\s*['\"]?\S{6,}")),
    ("password", re.compile(r"(?i)(密码|口令)\s*(是|为|:|=)\s*['\"]?\S{6,}")),
    ("refresh_token", re.compile(r"(?i)\brefresh[_-]?token\s*[:=]\s*['\"]?[A-Za-z0-9._-]{8,}")),
    ("private_key", re.compile(r"(?i)(私钥|private[_ -]?key)[^，。\s]*\s+\S*\.ssh/\S+")),
    ("bearer_token", re.compile(r"(?i)\bauthorization\s*[:=]\s*bearer\s+[A-Za-z0-9._-]{8,}")),
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")),
    ("slack_style_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{12,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{12,}\b")),
)

DEFAULT_TENANT_ID = "tenant:demo"
DEFAULT_ORGANIZATION_ID = "org:demo"
VISIBILITY_POLICIES = {"private", "team", "organization", "tenant", "public_demo"}
REVIEW_ROLES = {"reviewer", "owner", "admin"}


def check_scope_access(
    scope: str | None,
    current_context: dict[str, Any] | None = None,
    *,
    action: str = "memory.search",
) -> CopilotError | None:
    if not scope:
        return CopilotError("scope_required", "scope is required")

    context = current_context or {}
    if not isinstance(context, dict):
        return _permission_error("malformed_permission_context", "current_context must be an object", action=action)

    context_scope = context.get("scope")
    if isinstance(context_scope, str) and context_scope and context_scope != scope:
        return _permission_error(
            "scope_mismatch",
            "current_context.scope does not match requested scope",
            action=action,
            requested_scope=scope,
            context_scope=context_scope,
        )

    permission_payload = context.get("permission")
    if permission_payload is None:
        return _permission_error("missing_permission_context", "current_context.permission is required", action=action)

    try:
        permission = PermissionContext.from_payload(permission_payload)
    except ValidationError:
        return _permission_error(
            "malformed_permission_context",
            "permission context is malformed",
            action=action,
            permission_payload=permission_payload,
        )

    # Translation map: OpenClaw-facing tool names (fmc_xxx) → Python-side tool names (memory.xxx)
    OPENCLAW_TO_PYTHON = {
        "fmc_memory_search": "memory.search",
        "fmc_memory_create_candidate": "memory.create_candidate",
        "fmc_memory_confirm": "memory.confirm",
        "fmc_memory_reject": "memory.reject",
        "fmc_memory_explain_versions": "memory.explain_versions",
        "fmc_memory_prefetch": "memory.prefetch",
        "fmc_heartbeat_review_due": "heartbeat.review_due",
    }
    translated_action = OPENCLAW_TO_PYTHON.get(permission.requested_action, permission.requested_action)
    if translated_action != action:
        return _permission_error(
            "malformed_permission_context",
            "permission requested_action does not match tool action",
            permission=permission,
            action=action,
            requested_action=permission.requested_action,
        )

    if permission.requested_visibility not in VISIBILITY_POLICIES:
        return _permission_error(
            "malformed_permission_context",
            "permission requested_visibility is unsupported",
            permission=permission,
            action=action,
            requested_visibility=permission.requested_visibility,
        )

    workspace_id = permission.source_context.workspace_id
    if workspace_id and workspace_id != scope:
        return _permission_error(
            "source_context_mismatch",
            "permission source_context.workspace_id does not match requested scope",
            permission=permission,
            action=action,
            requested_scope=scope,
            workspace_id=workspace_id,
        )

    expected_tenant_id = _context_string(context, "tenant_id") or DEFAULT_TENANT_ID
    expected_organization_id = _context_string(context, "organization_id") or DEFAULT_ORGANIZATION_ID

    if permission.actor.tenant_id != expected_tenant_id:
        return _permission_error(
            "tenant_mismatch", "actor tenant cannot access requested memory scope", permission=permission, action=action
        )

    if permission.actor.organization_id != expected_organization_id:
        return _permission_error(
            "organization_mismatch",
            "actor organization cannot access requested memory scope",
            permission=permission,
            action=action,
        )

    context_chat_id = _context_string(context, "chat_id")
    source_chat_id = permission.source_context.chat_id
    if context_chat_id and source_chat_id and source_chat_id != context_chat_id:
        return _permission_error(
            "source_context_mismatch",
            "permission source_context.chat_id does not match current chat",
            permission=permission,
            action=action,
            context_chat_id=context_chat_id,
            source_chat_id=source_chat_id,
        )

    context_document_id = _context_string(context, "document_id")
    source_document_id = permission.source_context.document_id
    if context_document_id and source_document_id and source_document_id != context_document_id:
        return _permission_error(
            "source_context_mismatch",
            "permission source_context.document_id does not match current document",
            permission=permission,
            action=action,
            context_document_id=context_document_id,
            source_document_id=source_document_id,
        )

    roles = {role.strip().lower() for role in permission.actor.roles}
    if action in {"memory.confirm", "memory.reject", "memory.needs_evidence", "memory.expire"} and not roles.intersection(
        REVIEW_ROLES
    ):
        return _permission_error(
            "review_role_required", "reviewer, owner, or admin role is required", permission=permission, action=action
        )

    if permission.requested_visibility == "private" and not roles.intersection(REVIEW_ROLES):
        return _permission_error(
            "visibility_private_non_owner",
            "private memory requires owner or reviewer access",
            permission=permission,
            action=action,
        )

    return None


def _default_permission_context(
    action: str,
    scope: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Generate a default permission context for OpenClaw Agent calls."""
    import uuid
    from datetime import datetime, timezone

    user_id = context.get("user_id") or "openclaw_agent"
    return {
        "request_id": f"req_{uuid.uuid4().hex[:12]}",
        "trace_id": f"trace_{uuid.uuid4().hex[:12]}",
        "actor": {
            "user_id": user_id,
            "tenant_id": DEFAULT_TENANT_ID,
            "organization_id": DEFAULT_ORGANIZATION_ID,
            "roles": ["member"],
        },
        "source_context": {
            "entrypoint": "openclaw_agent",
            "workspace_id": scope,
        },
        "requested_action": action,
        "requested_visibility": "team",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _permission_error(
    reason_code: str,
    message: str,
    *,
    action: str,
    permission: PermissionContext | None = None,
    permission_payload: Any | None = None,
    **details: Any,
) -> CopilotError:
    error_details: dict[str, Any] = {
        "reason_code": reason_code,
        "action": action,
        "visible_fields": [],
        "redacted_fields": ["current_value", "summary", "evidence"],
    }
    if permission is not None:
        error_details["request_id"] = permission.request_id
        error_details["trace_id"] = permission.trace_id
        error_details["tenant_id"] = permission.actor.tenant_id
        error_details["organization_id"] = permission.actor.organization_id
    elif isinstance(permission_payload, dict):
        request_id = permission_payload.get("request_id")
        trace_id = permission_payload.get("trace_id")
        if isinstance(request_id, str):
            error_details["request_id"] = request_id
        if isinstance(trace_id, str):
            error_details["trace_id"] = trace_id
    error_details.update(details)
    return CopilotError("permission_denied", message, details=error_details)


def _context_string(context: dict[str, Any], key: str) -> str | None:
    value = context.get(key)
    return value if isinstance(value, str) and value else None


def demo_permission_context(
    action: str,
    scope: str,
    *,
    actor_id: str = "benchmark",
    roles: list[str] | None = None,
    visibility: str = "team",
    entrypoint: str = "benchmark",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an explicit demo/benchmark permission context for local fallback paths."""

    context: dict[str, Any] = {
        "scope": scope,
        "permission": {
            "request_id": f"req_{action.replace('.', '_')}",
            "trace_id": f"trace_{action.replace('.', '_')}",
            "actor": {
                "user_id": actor_id,
                "tenant_id": DEFAULT_TENANT_ID,
                "organization_id": DEFAULT_ORGANIZATION_ID,
                "roles": roles if roles is not None else ["member", "reviewer"],
            },
            "source_context": {
                "entrypoint": entrypoint,
                "workspace_id": scope,
            },
            "requested_action": action,
            "requested_visibility": visibility,
            "timestamp": "2026-05-07T00:00:00+08:00",
        },
    }
    if metadata:
        context["metadata"] = dict(metadata)
    return context


def sensitive_risk_flags(*texts: str | None) -> list[str]:
    """Return stable risk flags for obvious secret-like snippets."""

    combined = "\n".join(text for text in texts if text)
    flags = [flag for flag, pattern in _SENSITIVE_PATTERNS if pattern.search(combined)]
    if not flags:
        return []
    return ["sensitive_content", *sorted(set(flags))]


def redact_sensitive_text(text: str | None) -> str:
    """Redact obvious secret-like snippets before reminder/card dry-run output."""

    if not text:
        return ""
    redacted = text
    for flag, pattern in _SENSITIVE_PATTERNS:
        redacted = pattern.sub(f"[REDACTED:{flag}]", redacted)
    return redacted
