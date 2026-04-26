from __future__ import annotations

from typing import Any

from .schemas import CopilotError


def check_scope_access(scope: str | None, current_context: dict[str, Any] | None = None) -> CopilotError | None:
    if not scope:
        return CopilotError("scope_required", "scope is required")

    context = current_context or {}
    context_scope = context.get("scope")
    if isinstance(context_scope, str) and context_scope and context_scope != scope:
        return CopilotError(
            "permission_denied",
            "current_context.scope does not match requested scope",
            details={"requested_scope": scope, "context_scope": context_scope},
        )

    allowed_scopes = context.get("allowed_scopes")
    if allowed_scopes is None:
        return None
    if not isinstance(allowed_scopes, list) or not all(isinstance(item, str) for item in allowed_scopes):
        return CopilotError(
            "validation_error",
            "current_context.allowed_scopes must be a list of scope strings",
            details={"field": "current_context.allowed_scopes"},
        )
    if scope not in allowed_scopes:
        return CopilotError(
            "permission_denied",
            "requested scope is not in current_context.allowed_scopes",
            details={"requested_scope": scope, "allowed_scopes": allowed_scopes},
        )
    return None
