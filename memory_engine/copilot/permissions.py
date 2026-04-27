from __future__ import annotations

import re
from typing import Any

from .schemas import CopilotError


_SENSITIVE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("api_key", re.compile(r"(?i)\b(api[_-]?key|apikey)\s*[:=]\s*['\"]?[A-Za-z0-9._-]{8,}")),
    ("app_secret", re.compile(r"(?i)\b(app[_-]?secret|secret)\s*[:=]\s*['\"]?[A-Za-z0-9._-]{8,}")),
    ("password", re.compile(r"(?i)\b(password|passwd|pwd)\s*[:=]\s*['\"]?\S{6,}")),
    ("bearer_token", re.compile(r"(?i)\bauthorization\s*[:=]\s*bearer\s+[A-Za-z0-9._-]{8,}")),
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")),
    ("slack_style_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{12,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{12,}\b")),
)


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
