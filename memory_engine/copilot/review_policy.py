from __future__ import annotations

from typing import Any

IMPORTANT_ACTOR_ROLES = {
    "admin",
    "decision_maker",
    "lead",
    "manager",
    "owner",
}
IMPORTANT_KEYWORDS = (
    "决定",
    "决策",
    "流程",
    "负责人",
    "截止",
    "风险",
    "项目进展",
    "上线",
    "部署",
    "变更",
    "deadline",
    "decision",
    "owner",
    "risk",
    "workflow",
)
REAL_FEISHU_SOURCE_TYPES = {
    "document_feishu",
    "feishu",
    "feishu_message",
    "feishu_meeting",
    "feishu_task",
    "lark_bitable",
    "lark_doc",
}
SENSITIVE_RISK_HINTS = (
    "credential",
    "customer",
    "finance",
    "legal",
    "personal",
    "private",
    "secret",
    "sensitive",
    "token",
)
VISIBILITY_LABELS = {"private", "team", "project"}


def evaluate_review_policy(
    *,
    candidate: dict[str, Any] | None = None,
    extracted: dict[str, Any] | None = None,
    risk_flags: list[str] | tuple[str, ...] | None = None,
    conflict: dict[str, Any] | bool | None = None,
    source: dict[str, Any] | None = None,
    actor: dict[str, Any] | str | None = None,
    current_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the pure review-routing policy for a candidate memory.

    The function is intentionally side-effect free. It does not call the
    Copilot service, governance state machine, Feishu APIs, or repository.
    """

    candidate_data = _merge_candidate_data(candidate, extracted)
    source_data = source or {}
    context = current_context or {}
    flags = [str(flag) for flag in (risk_flags or []) if str(flag)]
    has_conflict = _has_conflict(conflict)
    real_feishu_source = _is_real_feishu_source(source_data)
    important_actor = _is_important_actor(actor, source_data)
    important_content = _is_important_content(candidate_data)
    sensitive = _has_sensitive_risk(flags)

    reasons: list[str] = []
    if has_conflict:
        reasons.append("conflict_update")
    if sensitive:
        reasons.append("sensitive_risk")
    if important_actor:
        reasons.append("important_actor")
    if important_content:
        reasons.append("important_content")

    requires_human_review = any(
        (
            has_conflict,
            sensitive,
            important_actor,
            important_content,
        )
    )

    importance_level = _importance_level(
        candidate_data,
        has_conflict=has_conflict,
        sensitive=sensitive,
        important_actor=important_actor,
        important_content=important_content,
    )
    visibility_label = _visibility_label(candidate_data, context)

    if requires_human_review:
        decision = "human_review"
        delivery_channel = "routed_private_review"
        review_targets = _review_targets(source_data, actor, context)
        if real_feishu_source:
            reasons.append("real_feishu_source_private_review")
    else:
        decision = "auto_confirm"
        delivery_channel = "none"
        review_targets = []
        reasons.append("low_importance")
        reasons.append("safe_for_auto_confirm")

    return {
        "decision": decision,
        "importance_level": importance_level,
        "reasons": _dedupe(reasons),
        "review_targets": review_targets,
        "delivery_channel": delivery_channel,
        "visibility_label": visibility_label,
    }


def _merge_candidate_data(candidate: dict[str, Any] | None, extracted: dict[str, Any] | None) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if extracted:
        merged.update(extracted)
    if candidate:
        merged.update(candidate)
    return merged


def _has_conflict(conflict: dict[str, Any] | bool | None) -> bool:
    if isinstance(conflict, bool):
        return conflict
    if not isinstance(conflict, dict):
        return False
    return bool(conflict.get("has_conflict") or conflict.get("conflict") or conflict.get("memory_id"))


def _is_real_feishu_source(source: dict[str, Any]) -> bool:
    source_type = str(source.get("source_type") or source.get("type") or "").lower()
    platform = str(source.get("platform") or source.get("provider") or "").lower()
    return source_type in REAL_FEISHU_SOURCE_TYPES or platform in {"feishu", "lark"}


def _is_important_actor(actor: dict[str, Any] | str | None, source: dict[str, Any]) -> bool:
    if isinstance(actor, str):
        return actor.lower() in IMPORTANT_ACTOR_ROLES

    roles: list[str] = []
    if isinstance(actor, dict):
        roles.extend(str(role).lower() for role in actor.get("roles", []) if str(role))
        if actor.get("is_important") or actor.get("important_actor"):
            return True

    source_role = source.get("actor_role") or source.get("role")
    if source_role:
        roles.append(str(source_role).lower())
    if source.get("important_actor"):
        return True

    return any(role in IMPORTANT_ACTOR_ROLES for role in roles)


def _is_important_content(candidate: dict[str, Any]) -> bool:
    explicit = str(candidate.get("importance_level") or candidate.get("importance") or "").lower()
    if explicit in {"high", "critical", "important"}:
        return True
    if explicit == "low":
        return False

    text_parts = [
        candidate.get("text"),
        candidate.get("summary"),
        candidate.get("current_value"),
        candidate.get("value"),
        candidate.get("subject"),
        candidate.get("type"),
    ]
    text = " ".join(str(part) for part in text_parts if part)
    return any(keyword.lower() in text.lower() for keyword in IMPORTANT_KEYWORDS)


def _has_sensitive_risk(flags: list[str]) -> bool:
    if not flags:
        return False
    for flag in flags:
        normalized = flag.lower()
        if normalized in {"none", "low", "low_memory_signal"}:
            continue
        if any(hint in normalized for hint in SENSITIVE_RISK_HINTS):
            return True
        return True
    return False


def _importance_level(
    candidate: dict[str, Any],
    *,
    has_conflict: bool,
    sensitive: bool,
    important_actor: bool,
    important_content: bool,
) -> str:
    explicit = str(candidate.get("importance_level") or candidate.get("importance") or "").lower()
    if explicit in {"low", "medium", "high", "critical"} and not (has_conflict or sensitive or important_actor):
        return "high" if explicit == "critical" else explicit
    if has_conflict or sensitive:
        return "high"
    if important_actor or important_content:
        return "medium"
    return "low"


def _visibility_label(candidate: dict[str, Any], current_context: dict[str, Any]) -> str:
    permission = current_context.get("permission")
    if not isinstance(permission, dict):
        permission = {}

    requested_visibility = (
        candidate.get("visibility_label")
        or candidate.get("visibility")
        or candidate.get("visibility_policy")
        or permission.get("requested_visibility")
        or current_context.get("visibility")
    )
    label = str(requested_visibility or "").lower()
    if label in VISIBILITY_LABELS:
        return label

    scope = str(candidate.get("scope") or current_context.get("scope") or "")
    if scope.startswith("project:"):
        return "project"
    if scope.startswith("user:") or scope.startswith("private:"):
        return "private"
    return "team"


def _review_targets(
    source: dict[str, Any],
    actor: dict[str, Any] | str | None,
    current_context: dict[str, Any],
) -> list[str]:
    targets: list[str] = []
    _append_target(targets, source.get("owner_id") or source.get("owner_open_id") or source.get("owner_user_id"))
    _append_target(targets, source.get("actor_id") or source.get("actor_open_id") or source.get("actor_user_id"))

    if isinstance(actor, str):
        _append_target(targets, actor)
    elif isinstance(actor, dict):
        _append_target(targets, actor.get("open_id") or actor.get("user_id") or actor.get("id"))

    permission = current_context.get("permission")
    if not isinstance(permission, dict):
        permission = {}
    for key in ("reviewers", "reviewer_open_ids", "reviewer_user_ids"):
        values = permission.get(key) or current_context.get(key)
        if isinstance(values, (list, tuple, set)):
            for value in values:
                _append_target(targets, value)
        else:
            _append_target(targets, values)

    return targets


def _append_target(targets: list[str], value: Any) -> None:
    if value is None:
        return
    target = str(value).strip()
    if target and target not in targets:
        targets.append(target)


def _dedupe(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return deduped
