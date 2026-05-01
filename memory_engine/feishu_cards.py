from __future__ import annotations

import json
import re
from typing import Any

CARD_ACTION_KEY = "memory_engine_action"


def build_decision_card(
    *,
    title: str,
    conclusion: str,
    reason: str,
    status: str,
    version: str,
    source: str,
    overwritten: str,
    memory_id: str | None = None,
) -> dict[str, Any]:
    fields = [
        ("结论", conclusion),
        ("理由", reason),
        ("状态", status),
        ("版本", version),
        ("来源", source),
        ("是否被覆盖", overwritten),
    ]
    if memory_id:
        fields.append(("memory_id", memory_id))

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": title},
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": label not in {"结论", "理由"},
                        "text": {"tag": "lark_md", "content": f"**{label}**\n{value}"},
                    }
                    for label, value in fields
                ],
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "这是一条企业记忆卡片：它展示当前有效结论、版本状态和证据来源，而不是普通聊天摘要。",
                },
            },
        ],
    }


def build_update_card(
    *,
    title: str,
    old_rule: str,
    new_rule: str,
    reason: str,
    version: str,
    source: str,
    memory_id: str | None = None,
) -> dict[str, Any]:
    card = build_decision_card(
        title=title,
        conclusion=new_rule,
        reason=reason,
        status="active",
        version=version,
        source=source,
        overwritten="否（旧规则已 superseded）",
        memory_id=memory_id,
    )
    card["header"]["template"] = "orange"
    card["elements"].insert(
        1,
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**旧规则 -> 新规则**\n{old_rule} -> {new_rule}",
            },
        },
    )
    return card


def candidate_review_payload(candidate_response: dict[str, Any]) -> dict[str, Any]:
    """Build a typed review payload from Copilot service output only."""

    bridge = _bridge_payload(candidate_response)
    if _is_permission_denied(candidate_response, bridge):
        return _denied_surface_payload("copilot_candidate_review", "候选审核不可用", candidate_response, bridge)

    candidate = candidate_response.get("candidate") or {}
    memory = candidate_response.get("memory") if isinstance(candidate_response.get("memory"), dict) else {}
    conflict = candidate_response.get("conflict") or candidate.get("conflict") or {}
    evidence = candidate_response.get("evidence") or candidate.get("evidence") or memory.get("evidence") or {}
    risk_flags = list(candidate_response.get("risk_flags") or candidate.get("risk_flags") or [])
    permission_decision = bridge.get("permission_decision") if isinstance(bridge.get("permission_decision"), dict) else {}
    actor = permission_decision.get("actor") if isinstance(permission_decision.get("actor"), dict) else {}
    owner_id = candidate_response.get("owner_id") or candidate.get("owner_id") or memory.get("owner_id")
    queue_views = _queue_views(risk_flags, conflict)
    candidate_id = str(candidate_response.get("candidate_id") or candidate.get("candidate_id") or "")
    buttons = []
    if _review_actions_allowed(bridge, owner_id=owner_id):
        buttons = _candidate_review_buttons(
            candidate_id=candidate_id,
            review_status=str(candidate_response.get("review_status") or candidate.get("review_status") or "pending"),
            action=str(candidate_response.get("action") or ""),
            has_conflict=bool(conflict.get("has_conflict")),
        )
    return {
        "surface": "copilot_candidate_review",
        "title": "待确认记忆",
        "candidate_id": candidate_response.get("candidate_id") or candidate.get("candidate_id"),
        "memory_id": candidate_response.get("memory_id") or candidate.get("memory_id"),
        "version_id": candidate_response.get("version_id") or candidate.get("version_id"),
        "status": candidate_response.get("status") or candidate.get("status"),
        "review_status": candidate_response.get("review_status") or candidate.get("review_status") or "pending",
        "source_type": candidate_response.get("source_type") or evidence.get("source_type"),
        "risk_level": candidate_response.get("risk_level") or _risk_level(risk_flags),
        "conflict_status": candidate_response.get("conflict_status") or _conflict_status(conflict),
        "queue_views": queue_views,
        "suggested_queue_view": queue_views[0] if queue_views else "待我审核",
        "reviewer": _actor_id(actor),
        "owner_id": owner_id,
        "last_handler": candidate_response.get("last_handler"),
        "last_handled_at": candidate_response.get("last_handled_at"),
        "type": candidate.get("type") or memory.get("type"),
        "subject": candidate.get("subject") or memory.get("subject"),
        "new_value": candidate.get("current_value") or memory.get("current_value"),
        "summary": candidate.get("summary") or memory.get("summary"),
        "scope_hint": _scope_hint(
            visibility_policy=(
                candidate_response.get("visibility_policy")
                or candidate.get("visibility_policy")
                or memory.get("visibility_policy")
            ),
            scope=candidate_response.get("scope") or candidate.get("scope") or memory.get("scope"),
            permission_decision=permission_decision,
        ),
        "evidence": evidence,
        "risk_flags": risk_flags,
        "recommended_action": candidate_response.get("recommended_action") or candidate.get("recommended_action"),
        "conflict": {
            "has_conflict": bool(conflict.get("has_conflict")),
            "old_memory_id": conflict.get("old_memory_id"),
            "old_value": conflict.get("old_value"),
            "old_status": conflict.get("old_status"),
            "reason": conflict.get("reason"),
        },
        "user_content": {
            "decision": candidate.get("current_value") or memory.get("current_value"),
            "source": _source_summary(evidence),
            "evidence_quote": evidence.get("quote") if isinstance(evidence, dict) else None,
            "risk_level": candidate_response.get("risk_level") or _risk_level(risk_flags),
            "conflict_summary": _conflict_summary(conflict),
            "recommended_action": candidate_response.get("recommended_action") or candidate.get("recommended_action"),
        },
        "audit_details": _audit_details(bridge),
        "buttons": buttons,
        "state_mutation": _review_state_mutation(candidate_response),
        **bridge,
    }


def search_result_payload(search_response: dict[str, Any]) -> dict[str, Any]:
    """Build the stable IA payload for a memory.search result card."""

    bridge = _bridge_payload(search_response)
    if _is_permission_denied(search_response, bridge):
        denied = _denied_surface_payload("copilot_search_results", "搜索结果不可用", search_response, bridge)
        denied["user_content"] = {"results": [], "empty_state": "permission_denied"}
        denied["audit_details"] = _audit_details(bridge)
        return denied

    rows = search_response.get("results") if isinstance(search_response.get("results"), list) else []
    user_results = []
    buttons = []
    for index, item in enumerate(rows[:3], start=1):
        if not isinstance(item, dict):
            continue
        memory_id = item.get("memory_id")
        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        first_evidence = evidence[0] if evidence and isinstance(evidence[0], dict) else {}
        user_results.append(
            {
                "rank": index,
                "memory_id": memory_id,
                "subject": item.get("subject"),
                "current_conclusion": item.get("current_value"),
                "evidence_quote": first_evidence.get("quote"),
                "version_status": item.get("status") or "active",
                "version": item.get("version"),
                "superseded_filtered": True,
                "rank_reason": _rank_reason(item),
                "explanation": _search_result_explanation(item, first_evidence),
            }
        )
        if memory_id:
            buttons.append(
                {
                    "action": "versions",
                    "label": "解释版本",
                    "required_for_mvp": True,
                    "memory_id": memory_id,
                }
            )

    return {
        "surface": "copilot_search_results",
        "title": "当前有效记忆",
        "query": search_response.get("query"),
        "status": "found" if user_results else "not_found",
        "user_content": {
            "results": user_results,
            "empty_state": None if user_results else "没有找到可直接采用的当前有效结论。",
        },
        "audit_details": _audit_details(bridge),
        "buttons": buttons,
        "state_mutation": "none",
        **bridge,
    }


def version_chain_payload(explain_versions_response: dict[str, Any]) -> dict[str, Any]:
    """Build a typed version-chain payload without mutating memory state."""

    bridge = _bridge_payload(explain_versions_response)
    if _is_permission_denied(explain_versions_response, bridge):
        return _denied_surface_payload("copilot_version_chain", "记忆版本链不可用", explain_versions_response, bridge)

    versions = explain_versions_response.get("versions") or []
    active = explain_versions_response.get("active_version") if isinstance(explain_versions_response.get("active_version"), dict) else {}
    old_versions = [item for item in versions if isinstance(item, dict) and not item.get("is_active")]
    user_explanation = explain_versions_response.get("user_explanation")
    if not isinstance(user_explanation, dict):
        user_explanation = _version_user_explanation_fallback(active, old_versions, explain_versions_response)
    return {
        "surface": "copilot_version_chain",
        "title": "记忆版本链",
        "memory_id": explain_versions_response.get("memory_id"),
        "scope": explain_versions_response.get("scope"),
        "subject": explain_versions_response.get("subject"),
        "type": explain_versions_response.get("type"),
        "status": explain_versions_response.get("status"),
        "active_version": explain_versions_response.get("active_version"),
        "versions": versions,
        "supersedes": explain_versions_response.get("supersedes") or [],
        "explanation": explain_versions_response.get("explanation"),
        "user_explanation": user_explanation,
        "user_content": {
            "current_version": user_explanation.get("current_version") or active,
            "old_versions": user_explanation.get("old_versions") or old_versions,
            "override_reason": user_explanation.get("override_reason") or explain_versions_response.get("explanation"),
            "evidence_summary": user_explanation.get("evidence_summary"),
            "search_boundary": user_explanation.get("search_boundary"),
            "timeline": [_version_timeline_item(item) for item in versions if isinstance(item, dict)],
        },
        "audit_details": _audit_details(bridge),
        "buttons": [],
        "state_mutation": "none",
        **bridge,
    }


def prefetch_context_payload(prefetch_response: dict[str, Any]) -> dict[str, Any]:
    """Build the stable IA payload for a memory.prefetch context card."""

    bridge = _bridge_payload(prefetch_response)
    if _is_permission_denied(prefetch_response, bridge):
        denied = _denied_surface_payload("copilot_prefetch_context", "任务前上下文不可用", prefetch_response, bridge)
        denied["user_content"] = {
            "task": prefetch_response.get("task"),
            "rules": [],
            "risks": [],
            "deadlines": [],
            "missing_information": ["权限不足，无法生成任务前上下文。"],
            "raw_events_included": False,
            "superseded_filtered": True,
        }
        denied["audit_details"] = _audit_details(bridge)
        return denied

    pack = prefetch_response.get("context_pack") if isinstance(prefetch_response.get("context_pack"), dict) else {}
    memories = pack.get("relevant_memories") if isinstance(pack.get("relevant_memories"), list) else []
    risks = pack.get("risks") if isinstance(pack.get("risks"), list) else []
    deadlines = pack.get("deadlines") if isinstance(pack.get("deadlines"), list) else []
    return {
        "surface": "copilot_prefetch_context",
        "title": "任务前上下文",
        "task": prefetch_response.get("task"),
        "status": "ready" if memories else "empty",
        "user_content": {
            "task": prefetch_response.get("task"),
            "summary": pack.get("summary"),
            "rules": [_compact_context_item(item) for item in memories[:5] if isinstance(item, dict)],
            "risks": [_compact_context_item(item) for item in risks[:5] if isinstance(item, dict)],
            "deadlines": [_compact_context_item(item) for item in deadlines[:5] if isinstance(item, dict)],
            "missing_information": [] if memories else ["没有找到可带入本次任务的 active 记忆。"],
            "raw_events_included": bool(pack.get("raw_events_included")),
            "superseded_filtered": bool(pack.get("stale_superseded_filtered", True)),
        },
        "audit_details": _audit_details(bridge),
        "buttons": [],
        "state_mutation": "none",
        **bridge,
    }


def reminder_candidate_payload(reminder: dict[str, Any]) -> dict[str, Any]:
    """Build a typed reminder payload from heartbeat dry-run output."""

    bridge = _bridge_payload(reminder)
    if _is_permission_denied(reminder, bridge):
        denied = _denied_surface_payload("copilot_reminder_candidate", "提醒候选不可用", reminder, bridge)
        denied["current_value"] = None
        denied["target_actor"] = {}
        denied["cooldown"] = {}
        return denied

    permission_trace = reminder.get("permission_trace") if isinstance(reminder.get("permission_trace"), dict) else {}
    request_id = permission_trace.get("request_id")
    trace_id = permission_trace.get("trace_id")
    permission_decision = {
        "decision": permission_trace.get("decision") or "allow",
        "reason_code": permission_trace.get("reason_code") or "scope_access_granted",
        "requested_action": permission_trace.get("requested_action") or "heartbeat.review_due",
    }
    is_withheld = reminder.get("status") == "withheld"
    actions = reminder.get("actions") if isinstance(reminder.get("actions"), list) else []
    if not actions:
        actions = [
            {"action": "confirm_useful", "label": "确认提醒有用", "mode": "dry_run"},
            {"action": "ignore", "label": "忽略本次", "mode": "dry_run"},
            {"action": "snooze", "label": "延后", "mode": "dry_run"},
            {"action": "mute_same_type", "label": "关闭同类提醒", "mode": "dry_run"},
        ]
    return {
        "surface": "copilot_reminder_candidate",
        "title": "提醒候选",
        "reminder_id": reminder.get("reminder_id"),
        "memory_id": reminder.get("memory_id"),
        "scope": reminder.get("scope"),
        "subject": reminder.get("subject"),
        "current_value": "" if is_withheld else reminder.get("current_value"),
        "reason": reminder.get("reason"),
        "trigger": reminder.get("trigger"),
        "status": reminder.get("status"),
        "due_at": reminder.get("due_at"),
        "evidence": {} if is_withheld else reminder.get("evidence") or {},
        "target_actor": reminder.get("target_actor") if isinstance(reminder.get("target_actor"), dict) else {},
        "cooldown": reminder.get("cooldown") if isinstance(reminder.get("cooldown"), dict) else {},
        "request_id": request_id,
        "trace_id": trace_id,
        "permission_decision": permission_decision,
        "permission_reason": permission_decision["reason_code"],
        "risk_flags": list(reminder.get("risk_flags") or []),
        "recommended_action": reminder.get("recommended_action") or "review_reminder_candidate",
        "buttons": [dict(action) for action in actions],
        "next_review_at": reminder.get("next_review_at"),
        "mute_key": reminder.get("mute_key"),
        "state_mutation": "none",
    }


def build_candidate_review_card(candidate_response: dict[str, Any]) -> dict[str, Any]:
    payload = candidate_review_payload(candidate_response)
    if payload.get("status") == "permission_denied":
        card = _permission_denied_card("待确认记忆", payload)
        _apply_review_open_ids(card, candidate_response)
        return card

    conflict = payload["conflict"]
    title, template = _candidate_review_card_title_and_template(payload)
    fields = [
        ("状态", _candidate_review_status_label(payload)),
        ("主题", str(payload.get("subject") or "")),
        ("适用范围", str(payload.get("scope_hint") or "当前团队范围")),
    ]
    if conflict["has_conflict"] and payload.get("review_status") == "pending":
        fields.extend(
            [
                ("旧结论", str(conflict.get("old_value") or "未找到可展示的旧结论")),
                ("新结论", str(payload.get("new_value") or "")),
            ]
        )
    else:
        fields.append(("记忆内容", str(payload.get("new_value") or "")))
    fields.extend(
        [
            ("证据", str((payload.get("evidence") or {}).get("quote") or "")),
            ("来源", _source_summary(payload.get("evidence") or {})),
        ]
    )

    card = {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": {
            "template": template,
            "title": {"tag": "plain_text", "content": title},
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": label not in {"记忆内容", "旧结论", "新结论", "证据"},
                        "text": {"tag": "lark_md", "content": f"**{label}**\n{value}"},
                    }
                    for label, value in fields
                    if value
                ],
            },
            _compact_audit_block(payload.get("audit_details") or {}),
        ],
    }
    actions = []
    for button in payload.get("buttons") or []:
        action = button.get("action")
        if action == "merge":
            actions.append(
                _button(
                    "确认合并",
                    _review_button_type("confirm", selected_action=button.get("selected_action")),
                    {CARD_ACTION_KEY: "merge", "candidate_id": str(payload.get("candidate_id") or "")},
                    disabled=bool(button.get("disabled")),
                )
            )
            continue
        if action == "confirm":
            actions.append(
                _button(
                    "确认保存",
                    _review_button_type("confirm", selected_action=button.get("selected_action")),
                    {CARD_ACTION_KEY: "confirm", "candidate_id": str(payload.get("candidate_id") or "")},
                    disabled=bool(button.get("disabled")),
                )
            )
        elif action == "reject":
            actions.append(
                _button(
                    "拒绝候选",
                    _review_button_type("reject", selected_action=button.get("selected_action")),
                    {CARD_ACTION_KEY: "reject", "candidate_id": str(payload.get("candidate_id") or "")},
                    disabled=bool(button.get("disabled")),
                )
            )
        elif action == "needs_evidence":
            actions.append(
                _button(
                    "要求补证据",
                    _review_button_type("needs_evidence", selected_action=button.get("selected_action")),
                    {CARD_ACTION_KEY: "needs_evidence", "candidate_id": str(payload.get("candidate_id") or "")},
                    disabled=bool(button.get("disabled")),
                )
            )
        elif action == "expire":
            actions.append(
                _button(
                    "标记过期",
                    _review_button_type("expire", selected_action=button.get("selected_action")),
                    {CARD_ACTION_KEY: "expire", "candidate_id": str(payload.get("candidate_id") or "")},
                    disabled=bool(button.get("disabled")),
                )
            )
        elif action == "undo":
            actions.append(
                _button(
                    "撤销这次处理",
                    "default",
                    {CARD_ACTION_KEY: "undo", "candidate_id": str(payload.get("candidate_id") or "")},
                    disabled=bool(button.get("disabled")),
                )
            )
    if actions:
        card["elements"].append({"tag": "action", "actions": actions})
    _apply_review_open_ids(card, candidate_response)
    return card


def build_review_inbox_card(inbox_response: dict[str, Any]) -> dict[str, Any]:
    counts = inbox_response.get("counts") if isinstance(inbox_response.get("counts"), dict) else {}
    items = inbox_response.get("items") if isinstance(inbox_response.get("items"), list) else []
    fields: list[tuple[str, str]] = []
    count_summary = _review_counts_summary(counts)
    if count_summary:
        fields.append(("counts", count_summary))

    elements: list[dict[str, Any]] = []
    if fields:
        elements.append(
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": False,
                        "text": {"tag": "lark_md", "content": f"**{label}**\n{value}"},
                    }
                    for label, value in fields
                ],
            }
        )

    if items:
        for index, item in enumerate(items[:10], start=1):
            if not isinstance(item, dict):
                continue
            item_fields = _review_inbox_item_fields(item)
            if not item_fields:
                continue
            elements.append(
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": label not in {"新结论", "旧结论", "证据", "建议动作"},
                            "text": {
                                "tag": "lark_md",
                                "content": f"**{label} {index if label == '主题' else ''}**\n{value}",
                            },
                        }
                        for label, value in item_fields
                        if value
                    ],
                }
            )
            item_actions = _review_inbox_item_actions(item, index)
            if item_actions:
                elements.append({"tag": "action", "actions": item_actions})
    else:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "暂无待审核记忆。"}})

    card = {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": {
            "template": "orange",
            "title": {"tag": "plain_text", "content": "待审核记忆"},
        },
        "elements": elements,
    }
    _apply_review_open_ids(card, inbox_response)
    return card


def build_group_settings_card(settings_response: dict[str, Any]) -> dict[str, Any]:
    """Build a group settings card for the current Feishu sandbox."""

    fields = [
        (
            "当前群状态",
            f"{settings_response.get('chat_status') or 'pending_onboarding'}；"
            f"passive={str(bool(settings_response.get('passive_memory_enabled'))).lower()}",
        ),
        ("allowlist 群静默筛选", _group_silent_screening_label(settings_response)),
        ("审核投递方式", str(settings_response.get("review_delivery") or "DM/private")),
        ("auto-confirm policy", str(settings_response.get("auto_confirm_policy") or "")),
        ("onboarding policy", str(settings_response.get("onboarding_policy") or "")),
        ("scope", str(settings_response.get("scope") or "")),
        ("visibility", _visibility_label(settings_response.get("visibility_policy"))),
        ("运行边界", str(settings_response.get("production_boundary") or "受控 live sandbox，不是生产长期运行。")),
    ]
    fields.append(("写入动作", "/enable_memory 启用；/disable_memory 关闭。需要 reviewer/admin 授权。"))
    return {
        "config": {"wide_screen_mode": True, "update_multi": False},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "群级记忆设置"},
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": label in {"scope", "visibility"},
                        "text": {"tag": "lark_md", "content": f"**{label}**\n{value}"},
                    }
                    for label, value in fields
                    if value
                ],
            }
        ],
    }


def build_search_result_card(search_response: dict[str, Any]) -> dict[str, Any]:
    payload = search_result_payload(search_response)
    if payload.get("status") == "permission_denied":
        return _permission_denied_card("当前有效记忆", payload)

    results = payload["user_content"]["results"]
    if not results:
        fields = [("状态", payload["user_content"]["empty_state"])]
    else:
        fields = []
        for item in results:
            fields.extend(
                [
                    (f"当前结论 {item['rank']}", str(item.get("current_conclusion") or "")),
                    ("为什么采用", str(item.get("explanation") or "")),
                    ("证据", str(item.get("evidence_quote") or "")),
                    ("版本状态", f"{item.get('version_status') or 'active'}；已过滤旧值"),
                    ("排序理由", str(item.get("rank_reason") or "")),
                ]
            )
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "当前有效记忆"},
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": label not in {"当前结论 1", "当前结论 2", "当前结论 3", "为什么采用", "证据", "排序理由"},
                        "text": {"tag": "lark_md", "content": f"**{label}**\n{value}"},
                    }
                    for label, value in fields[:12]
                ],
            }
        ],
    }
    actions = [
        _button(
            str(button["label"]),
            "default",
            {CARD_ACTION_KEY: "versions", "memory_id": str(button.get("memory_id") or "")},
        )
        for button in (payload.get("buttons") or [])[:3]
        if button.get("action") == "versions" and button.get("memory_id")
    ]
    if actions:
        card["elements"].append({"tag": "action", "actions": actions})
    card["elements"].append(_audit_block(payload.get("audit_details") or {}))
    return card


def build_reminder_candidate_card(reminder: dict[str, Any]) -> dict[str, Any]:
    payload = reminder_candidate_payload(reminder)
    if payload.get("status") == "permission_denied":
        return _permission_denied_card("提醒候选", payload)
    fields = [
        ("状态", str(payload.get("status") or "")),
        ("触发原因", str(payload.get("trigger") or "")),
        ("主题", str(payload.get("subject") or "")),
        ("提醒内容", str(payload.get("current_value") or "")),
        ("为什么提醒", str(payload.get("reason") or "")),
        ("证据", str((payload.get("evidence") or {}).get("quote") or "")),
        ("目标对象", _format_json(payload.get("target_actor") or {})),
        ("冷却窗口", _format_json(payload.get("cooldown") or {})),
        ("风险", ", ".join(payload.get("risk_flags") or []) or "无"),
    ]
    if payload.get("request_id"):
        fields.append(("request_id", str(payload["request_id"])))
    if payload.get("trace_id"):
        fields.append(("trace_id", str(payload["trace_id"])))
    if payload.get("due_at"):
        fields.append(("截止时间", str(payload["due_at"])))

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "purple" if payload.get("risk_flags") else "wathet",
            "title": {"tag": "plain_text", "content": "提醒候选"},
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": label not in {"提醒内容", "为什么提醒", "证据", "目标对象", "冷却窗口"},
                        "text": {"tag": "lark_md", "content": f"**{label}**\n{value}"},
                    }
                    for label, value in fields
                ],
            },
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "本阶段只生成 dry-run 提醒候选，不直接发群或写 active 记忆。"},
            },
        ],
    }
    actions = []
    for button in payload.get("buttons") or []:
        action = button.get("action")
        label = str(button.get("label") or action or "")
        if action in {"confirm_useful", "ignore", "snooze", "mute_same_type"}:
            actions.append(
                _button(
                    label,
                    "primary" if action == "confirm_useful" else "default",
                    {
                        CARD_ACTION_KEY: str(action),
                        "reminder_id": str(payload.get("reminder_id") or ""),
                        "memory_id": str(payload.get("memory_id") or ""),
                        "scope": str(payload.get("scope") or ""),
                        "subject": str(payload.get("subject") or ""),
                        "trigger": str(payload.get("trigger") or ""),
                        "review_surface": "reminder_candidate",
                    },
                )
            )
    if actions:
        card["elements"].append({"tag": "action", "actions": actions})
    return card


def build_version_chain_card(explain_versions_response: dict[str, Any]) -> dict[str, Any]:
    payload = version_chain_payload(explain_versions_response)
    if payload.get("status") == "permission_denied":
        return _permission_denied_card("记忆版本链", payload)

    user_content = payload.get("user_content") if isinstance(payload.get("user_content"), dict) else {}
    current_version = user_content.get("current_version") if isinstance(user_content.get("current_version"), dict) else {}
    version_lines = []
    for item in user_content.get("timeline") or payload["versions"]:
        marker = "当前" if item.get("is_active") else "旧值"
        inactive = f"；{item['inactive_reason']}" if item.get("inactive_reason") else ""
        version = item.get("version") or item.get("version_no")
        version_lines.append(f"v{version} [{item.get('status')}] {marker}：{item.get('value')}{inactive}")

    explanation_fields = [
        ("当前结论", str(current_version.get("value") or (payload.get("active_version") or {}).get("value") or "")),
        ("为什么采用", str(user_content.get("override_reason") or payload.get("explanation") or "")),
        ("证据说明", str(user_content.get("evidence_summary") or "")),
        ("搜索边界", str(user_content.get("search_boundary") or "默认搜索只返回当前 active 版本。")),
    ]

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "记忆版本链"},
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": label == "搜索边界",
                        "text": {"tag": "lark_md", "content": f"**{label}**\n{value}"},
                    }
                    for label, value in explanation_fields
                ],
            },
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": True,
                        "text": {"tag": "lark_md", "content": f"**主题**\n{payload.get('subject') or ''}"},
                    },
                    {
                        "is_short": True,
                        "text": {"tag": "lark_md", "content": f"**状态**\n{payload.get('status') or ''}"},
                    },
                ],
            },
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "\n".join(version_lines)},
            },
            _audit_block(payload.get("audit_details") or {}),
        ],
    }


def build_prefetch_context_card(prefetch_response: dict[str, Any]) -> dict[str, Any]:
    payload = prefetch_context_payload(prefetch_response)
    if payload.get("status") == "permission_denied":
        return _permission_denied_card("任务前上下文", payload)

    content = payload["user_content"]
    fields = [
        ("任务", str(content.get("task") or "")),
        ("上下文摘要", str(content.get("summary") or "")),
        ("规则", _context_lines(content.get("rules") or [])),
        ("关键风险", _context_lines(content.get("risks") or []) or "无"),
        ("deadline / owner", _context_lines(content.get("deadlines") or []) or "无"),
        ("缺失信息", "\n".join(content.get("missing_information") or []) or "无"),
        ("过滤状态", "不包含原始事件；superseded 旧值已过滤"),
    ]
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "wathet",
            "title": {"tag": "plain_text", "content": "任务前上下文"},
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": label in {"任务", "deadline / owner"},
                        "text": {"tag": "lark_md", "content": f"**{label}**\n{value}"},
                    }
                    for label, value in fields
                ],
            },
            _audit_block(payload.get("audit_details") or {}),
        ],
    }


def build_card_from_text(text: str) -> dict[str, Any]:
    fields = _fields_from_text(text)
    card_name = fields.get("卡片") or fields.get("类型") or "企业记忆卡片"
    title = _headline(text) or card_name
    template = _template_for(card_name, fields.get("状态"))
    core_labels = ("结论", "理由", "状态", "版本", "来源", "是否被覆盖")
    display_fields = [(label, fields[label]) for label in core_labels if fields.get(label)]
    for label in ("主题", "候选序号", "记忆类型", "版本数量", "处理结果"):
        if fields.get(label):
            display_fields.append((label, fields[label]))

    elements: list[dict[str, Any]]
    if display_fields:
        elements = [
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": label not in {"结论", "理由"},
                        "text": {"tag": "lark_md", "content": f"**{label}**\n{value}"},
                    }
                    for label, value in display_fields[:10]
                ],
            }
        ]
    else:
        elements = [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": title},
            }
        ]

    detail_lines = _detail_lines(text)
    if detail_lines:
        elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "\n".join(detail_lines[:12])},
            }
        )

    actions = _actions_from_text(text)
    if actions:
        elements.append({"tag": "action", "actions": actions[:10]})

    elements.extend(
        [
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "这是一条企业记忆卡片：它展示当前有效结论、版本状态和证据来源，而不是普通聊天摘要。",
                },
            },
        ]
    )

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": template,
            "title": {"tag": "plain_text", "content": title[:80]},
        },
        "elements": elements,
    }


def _headline(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def _audit_details(bridge: dict[str, Any]) -> dict[str, Any]:
    decision = bridge.get("permission_decision") if isinstance(bridge.get("permission_decision"), dict) else {}
    return {
        "request_id": bridge.get("request_id"),
        "trace_id": bridge.get("trace_id"),
        "permission_decision": decision,
        "permission_reason": bridge.get("permission_reason") or decision.get("reason_code"),
    }


def _apply_review_open_ids(card: dict[str, Any], response: dict[str, Any]) -> None:
    open_ids = _review_open_ids(response)
    if open_ids:
        card["open_ids"] = open_ids


def _review_open_ids(response: dict[str, Any]) -> list[str]:
    review_policy = response.get("review_policy") if isinstance(response.get("review_policy"), dict) else {}
    delivery_channel = response.get("delivery_channel") or review_policy.get("delivery_channel")
    targets = (
        response.get("open_ids")
        or response.get("review_targets")
        or review_policy.get("open_ids")
        or review_policy.get("review_targets")
    )
    if delivery_channel and str(delivery_channel) != "routed_private_review":
        return []
    if targets is None:
        return []
    if isinstance(targets, str):
        targets = [targets]
    if not isinstance(targets, list):
        return []
    open_ids: list[str] = []
    seen: set[str] = set()
    for target in targets:
        value: Any = target
        if isinstance(target, dict):
            value = target.get("open_id") or target.get("user_id")
        if not isinstance(value, str):
            continue
        value = value.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        open_ids.append(value)
    return open_ids


def _review_counts_summary(counts: dict[str, Any]) -> str:
    if not counts:
        return ""
    lines = []
    labels = {
        "all": "全部待审",
        "mine": "待我审核",
        "conflicts": "冲突需判断",
        "conflict": "冲突需判断",
        "high_risk": "高风险",
        "pending": "待处理",
    }
    for key, value in counts.items():
        if isinstance(value, (str, int, float)):
            lines.append(f"{labels.get(str(key), str(key))}: {value}")
    return "\n".join(lines)


def _review_inbox_item_fields(item: dict[str, Any]) -> list[tuple[str, str]]:
    conflict = item.get("conflict") if isinstance(item.get("conflict"), dict) else {}
    evidence = item.get("evidence") or item.get("evidence_quote")
    new_value = item.get("new_value") or item.get("current_value") or item.get("value")
    old_value = item.get("old_value") or conflict.get("old_value")
    scope_hint = item.get("scope_hint") or _review_scope_hint(
        item.get("visibility") or item.get("visibility_policy") or item.get("scope")
    )
    fields = [
        ("主题", str(item.get("subject") or "未命名候选")),
        ("新结论", str(new_value or "")),
    ]
    if old_value:
        fields.append(("旧结论", str(old_value)))
    fields.extend(
        [
            ("证据", _evidence_quote(evidence)),
            ("适用范围", str(scope_hint or "当前团队范围")),
            ("建议动作", str(item.get("recommended_action") or item.get("suggested_action") or "人工审核")),
        ]
    )
    return fields


def _review_inbox_item_actions(item: dict[str, Any], index: int) -> list[dict[str, Any]]:
    candidate_id = str(item.get("candidate_id") or "")
    if not candidate_id:
        return []
    return [
        _button(
            f"确认第{index}条",
            "primary",
            {CARD_ACTION_KEY: "confirm", "candidate_id": candidate_id, "candidate_label": f"候选 {index}"},
        ),
        _button(
            f"拒绝第{index}条",
            "default",
            {CARD_ACTION_KEY: "reject", "candidate_id": candidate_id, "candidate_label": f"候选 {index}"},
        ),
        _button(
            f"补证据第{index}条",
            "default",
            {CARD_ACTION_KEY: "needs_evidence", "candidate_id": candidate_id, "candidate_label": f"候选 {index}"},
        ),
    ]


def _review_scope_hint(value: Any) -> str:
    return {
        "private": "仅自己",
        "team": "当前团队范围",
        "organization": "当前组织范围",
        "tenant": "当前租户范围",
        "public_demo": "公开演示数据",
        "project": "当前项目",
    }.get(str(value or ""), str(value or "当前团队范围"))


def _evidence_quote(evidence: Any) -> str:
    if isinstance(evidence, dict):
        return str(evidence.get("quote") or evidence.get("summary") or "")
    if isinstance(evidence, list):
        for item in evidence:
            quote = _evidence_quote(item)
            if quote:
                return quote
        return ""
    if isinstance(evidence, str):
        return evidence
    return ""


def _review_actions_allowed(bridge: dict[str, Any], *, owner_id: str | None = None) -> bool:
    decision = bridge.get("permission_decision")
    if not isinstance(decision, dict) or not decision:
        return True
    if decision.get("decision") != "allow":
        return False
    actor = decision.get("actor") if isinstance(decision.get("actor"), dict) else {}
    actor_id = _actor_id(actor)
    if owner_id and actor_id and actor_id == owner_id:
        return True
    roles = actor.get("roles") if isinstance(actor.get("roles"), list) else []
    return bool({"reviewer", "owner", "admin"} & {str(role) for role in roles})


def _source_summary(evidence: dict[str, Any]) -> str:
    if not isinstance(evidence, dict) or not evidence:
        return ""
    source_type = evidence.get("source_type") or "source"
    source_id = evidence.get("source_id")
    return f"{source_type}:{source_id}" if source_id else str(source_type)


def _risk_level(flags: list[Any]) -> str:
    flag_set = {str(flag) for flag in flags}
    if "sensitive_content" in flag_set:
        return "high"
    if flag_set & {"conflict_candidate", "manual_review_conflict", "needs_review"}:
        return "medium"
    return "low"


def _conflict_status(conflict: dict[str, Any]) -> str:
    if not isinstance(conflict, dict) or not conflict.get("has_conflict"):
        return "no_conflict"
    if conflict.get("old_status") == "active":
        return "overrides_active"
    return "possible_conflict"


def _queue_views(flags: list[Any], conflict: dict[str, Any]) -> list[str]:
    views = ["待我审核"]
    if isinstance(conflict, dict) and conflict.get("has_conflict"):
        views.append("冲突需判断")
    if _risk_level(flags) == "high" or "low_confidence" in {str(flag) for flag in flags}:
        views.append("高风险暂不建议确认")
    return views


def _actor_id(actor: dict[str, Any]) -> str | None:
    for key in ("user_id", "open_id"):
        value = actor.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _scope_hint(
    *,
    visibility_policy: Any = None,
    scope: Any = None,
    permission_decision: dict[str, Any] | None = None,
) -> str:
    policy = str(visibility_policy or "").strip().lower()
    if policy in {"private", "self", "owner", "only_me", "user"}:
        return "仅自己"
    if policy in {"group", "chat", "team"}:
        return "本群或团队"
    if policy in {"org", "organization", "tenant", "workspace"}:
        return "本组织"
    if policy in {"project", "current_project"}:
        return "当前项目"

    scope_text = str(scope or "").strip().lower()
    if scope_text.startswith(("user:", "private:", "self:")):
        return "仅自己"
    if scope_text.startswith(("chat:", "group:", "team:")):
        return "本群或团队"
    if scope_text.startswith(("org:", "organization:", "tenant:", "workspace:")):
        return "本组织"
    if scope_text.startswith("project:"):
        return "当前项目"

    decision = permission_decision if isinstance(permission_decision, dict) else {}
    requested_visibility = str(decision.get("requested_visibility") or "").strip().lower()
    if requested_visibility:
        return _scope_hint(visibility_policy=requested_visibility)
    return "当前团队范围"


def _visibility_label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "team"
    hint = _scope_hint(visibility_policy=raw)
    return f"{raw}（{hint}）"


def _group_silent_screening_label(settings_response: dict[str, Any]) -> str:
    allowlist = str(settings_response.get("allowlist_summary") or "not configured")
    status = str(settings_response.get("silent_screening") or "")
    if status == "enabled_for_current_group_policy":
        return f"开启，当前群策略已启用；allowlist={allowlist}"
    if status == "enabled_for_allowlist_groups":
        return f"开启，仅限 allowlist 群；allowlist={allowlist}"
    if status == "enabled_for_wildcard_groups":
        return f"开启，当前允许 wildcard 群；allowlist={allowlist}"
    return f"allowlist 未配置，当前进程不会限制 chat；生产前必须配置 allowlist。allowlist={allowlist}"


def _conflict_summary(conflict: dict[str, Any]) -> str:
    if not isinstance(conflict, dict) or not conflict.get("has_conflict"):
        return "无冲突"
    old_value = conflict.get("old_value")
    if old_value:
        return f"将覆盖现有 active 记忆：{old_value}"
    return "存在 active 记忆冲突，需要 reviewer 判断"


def _rank_reason(item: dict[str, Any]) -> str:
    matched = item.get("matched_via") if isinstance(item.get("matched_via"), list) else []
    why = item.get("why_ranked") if isinstance(item.get("why_ranked"), dict) else {}
    if matched:
        return "；".join(_matched_reason_label(value) for value in matched[:3])
    if why.get("reason"):
        return _why_ranked_label(str(why["reason"]))
    if item.get("score") is not None:
        return f"综合相关度 {item.get('score')}"
    return "按当前 active 记忆相关度排序"


def _matched_reason_label(value: Any) -> str:
    labels = {
        "active": "命中当前 active 记忆",
        "evidence": "证据内容与问题相关",
        "semantic": "语义相似",
        "keyword": "关键词匹配",
        "keyword_index": "关键词匹配",
        "subject": "主题匹配",
        "vector": "语义相似",
        "superseded_filtered": "旧版本已过滤",
    }
    key = str(value)
    return labels.get(key, f"匹配线索：{key}")


def _why_ranked_label(reason: str) -> str:
    labels = {
        "active": "命中当前 active 记忆",
        "evidence": "证据内容与问题相关",
        "superseded_filtered": "旧版本已过滤",
        "default_search_excludes_non_active_memory": "默认搜索只返回当前 active 版本，旧值已过滤",
    }
    return labels.get(reason, reason)


def _search_result_explanation(item: dict[str, Any], evidence: dict[str, Any]) -> str:
    status = item.get("status") or "active"
    source = _source_summary(evidence)
    parts = [f"这条记忆当前是 {status} 状态"]
    if source:
        parts.append(f"证据来自 {source}")
    parts.append("默认结果已过滤 superseded 旧值")
    return "；".join(parts) + "。"


def _version_user_explanation_fallback(
    active: dict[str, Any], old_versions: list[dict[str, Any]], response: dict[str, Any]
) -> dict[str, Any]:
    current = _version_summary_for_user(active) if active else None
    old = [_version_summary_for_user(item) for item in old_versions]
    return {
        "kind": "memory_version_chain",
        "current_version": current,
        "old_versions": old,
        "override_reason": response.get("explanation") or "当前采用已确认的 active 版本。",
        "evidence_summary": _version_card_evidence_summary(active, old_versions),
        "search_boundary": "默认搜索只返回当前 active 版本；旧版本不会作为当前答案返回。",
    }


def _version_summary_for_user(item: dict[str, Any]) -> dict[str, Any]:
    evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    return {
        "version_id": item.get("version_id"),
        "version": item.get("version") or item.get("version_no"),
        "status": item.get("status"),
        "value": item.get("value"),
        "reason": item.get("reason"),
        "evidence": evidence,
        "inactive_reason": item.get("inactive_reason"),
    }


def _version_card_evidence_summary(active: dict[str, Any], old_versions: list[dict[str, Any]]) -> str:
    evidence = active.get("evidence") if isinstance(active.get("evidence"), dict) else {}
    quote = evidence.get("quote")
    if quote:
        return f"当前版本证据：{quote}"
    if old_versions:
        return "旧版本证据仍保留在版本链里，当前答案只采用 active 版本。"
    return "当前版本没有可展示的证据摘要。"


def _version_timeline_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": item.get("version") or item.get("version_no"),
        "status": item.get("status"),
        "value": item.get("value"),
        "inactive_reason": item.get("inactive_reason"),
        "is_active": bool(item.get("is_active")),
    }


def _compact_context_item(item: dict[str, Any]) -> dict[str, Any]:
    evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
    first_evidence = evidence[0] if evidence and isinstance(evidence[0], dict) else {}
    return {
        "memory_id": item.get("memory_id"),
        "subject": item.get("subject"),
        "current_value": item.get("current_value"),
        "status": item.get("status"),
        "version": item.get("version"),
        "evidence_quote": first_evidence.get("quote"),
    }


def _context_lines(items: list[dict[str, Any]]) -> str:
    lines = []
    for item in items:
        subject = item.get("subject") or "记忆"
        value = item.get("current_value") or ""
        lines.append(f"- {subject}: {value}")
    return "\n".join(lines)


def _audit_block(details: dict[str, Any]) -> dict[str, Any]:
    decision = details.get("permission_decision") if isinstance(details.get("permission_decision"), dict) else {}
    lines = [
        f"request_id: {details.get('request_id') or '-'}",
        f"trace_id: {details.get('trace_id') or '-'}",
        f"permission: {decision.get('decision') or '-'} / {details.get('permission_reason') or decision.get('reason_code') or '-'}",
    ]
    return {
        "tag": "div",
        "text": {"tag": "lark_md", "content": "**审计详情**\n" + "\n".join(lines)},
    }


def _fields_from_text(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if "：" not in stripped:
            continue
        label, value = stripped.split("：", 1)
        label = label.strip()
        if label:
            fields[label] = value.strip()
    return fields


def _detail_lines(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("v", "mem_")) or "旧规则 -> 新规则" in stripped or "建议动作：" in stripped:
            lines.append(stripped)
    return lines


def _actions_from_text(text: str) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    candidates: list[tuple[int, str]] = []
    for line in text.splitlines():
        if "[candidate]" not in line:
            continue
        candidate_id = _last_match(r"/confirm\s+(mem_[A-Za-z0-9_]+)", line)
        candidate_index = _candidate_index_from_line(line)
        if candidate_id and candidate_id not in {candidate[1] for candidate in candidates}:
            candidates.append((candidate_index or len(candidates) + 1, candidate_id))
    for index, candidate_id in candidates[:3]:
        for action, label, button_type in (
            ("confirm", f"确认候选 {index}", "primary"),
            ("reject", f"拒绝候选 {index}", "danger"),
        ):
            key = (action, candidate_id)
            if key in seen:
                continue
            seen.add(key)
            actions.append(
                _button(
                    label,
                    button_type,
                    {
                        CARD_ACTION_KEY: action,
                        "candidate_id": candidate_id,
                        "candidate_index": str(index),
                        "candidate_label": f"候选 {index}",
                    },
                )
            )

    memory_id = _last_match(r"memory_id：\s*(mem_[A-Za-z0-9_]+)", text)
    if memory_id:
        actions.append(_button("查看版本链", "default", {CARD_ACTION_KEY: "versions", "memory_id": memory_id}))
    return actions


def _button(label: str, button_type: str, value: dict[str, str], *, disabled: bool = False) -> dict[str, Any]:
    button = {
        "tag": "button",
        "text": {"tag": "plain_text", "content": label},
        "type": button_type,
        "value": value,
    }
    if disabled:
        button["disabled"] = True
    return button


def _candidate_review_buttons(
    *,
    candidate_id: str,
    review_status: str,
    action: str,
    has_conflict: bool = False,
) -> list[dict[str, Any]]:
    selected = _selected_review_action(review_status, action)
    if selected is not None:
        return [{"action": "undo", "label": "撤销这次处理", "required_for_mvp": True, "candidate_id": candidate_id}]
    buttons = [
        {"action": "confirm", "label": "确认保存", "required_for_mvp": True, "candidate_id": candidate_id},
        {"action": "reject", "label": "拒绝候选", "required_for_mvp": True, "candidate_id": candidate_id},
        {"action": "needs_evidence", "label": "要求补证据", "required_for_mvp": True, "candidate_id": candidate_id},
        {"action": "expire", "label": "标记过期", "required_for_mvp": True, "candidate_id": candidate_id},
    ]
    if has_conflict:
        buttons.insert(0, {"action": "merge", "label": "确认合并", "required_for_mvp": True, "candidate_id": candidate_id})
    return buttons


def _candidate_review_card_title_and_template(payload: dict[str, Any]) -> tuple[str, str]:
    review_status = str(payload.get("review_status") or "")
    if review_status == "confirmed":
        return "已确认记忆", "green"
    if review_status == "rejected":
        return "已拒绝候选", "red"
    if review_status == "needs_evidence":
        return "待补充证据", "yellow"
    if review_status == "expired":
        return "已标记过期", "grey"
    conflict = payload.get("conflict") if isinstance(payload.get("conflict"), dict) else {}
    return "待确认记忆", "orange" if conflict.get("has_conflict") else "turquoise"


def _candidate_review_status_label(payload: dict[str, Any]) -> str:
    review_status = str(payload.get("review_status") or "")
    status = str(payload.get("status") or "")
    return {
        "pending": "待确认",
        "confirmed": "已确认",
        "rejected": "已拒绝",
        "needs_evidence": "待补充证据",
        "expired": "已过期",
    }.get(review_status, status or review_status)


def _compact_audit_block(audit: dict[str, Any]) -> dict[str, Any]:
    permission_decision = audit.get("permission_decision") if isinstance(audit.get("permission_decision"), dict) else {}
    decision = str(permission_decision.get("decision") or audit.get("decision") or "")
    reason = str(permission_decision.get("reason_code") or audit.get("permission_reason") or audit.get("reason_code") or "")
    summary = "已记录"
    if decision:
        summary = f"已记录；权限：{decision}"
        if reason:
            summary += f" / {reason}"
    return {"tag": "div", "text": {"tag": "lark_md", "content": f"**审计**\n{summary}"}}


def _selected_review_action(review_status: str, action: str) -> str | None:
    if action in {"confirmed", "auto_confirmed"} or review_status == "confirmed":
        return "confirm"
    if action == "rejected" or review_status == "rejected":
        return "reject"
    if action == "needs_evidence" or review_status == "needs_evidence":
        return "needs_evidence"
    if action == "expired" or review_status == "expired":
        return "expire"
    return None


def _review_state_mutation(candidate_response: dict[str, Any]) -> str:
    action = candidate_response.get("action")
    if isinstance(action, str) and action in {"confirmed", "rejected", "needs_evidence", "expired", "auto_confirmed"}:
        return "confirmed" if action == "auto_confirmed" else action
    return "none"


def _review_button_type(action: str, *, selected_action: Any) -> str:
    if action == "reject":
        return "danger" if selected_action == action else "default"
    if selected_action == action:
        return "primary"
    return "default"


def _format_json(value: Any) -> str:
    if not value:
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _bridge_payload(response: dict[str, Any]) -> dict[str, Any]:
    bridge = response.get("bridge") if isinstance(response.get("bridge"), dict) else {}
    decision = bridge.get("permission_decision") if isinstance(bridge.get("permission_decision"), dict) else {}
    error = response.get("error") if isinstance(response.get("error"), dict) else {}
    details = error.get("details") if isinstance(error.get("details"), dict) else {}
    request_id = bridge.get("request_id") or details.get("request_id")
    trace_id = bridge.get("trace_id") or details.get("trace_id")
    reason_code = decision.get("reason_code") or details.get("reason_code")
    permission_decision = dict(decision)
    if not permission_decision and error.get("code") == "permission_denied":
        permission_decision = {"decision": "deny", "reason_code": reason_code or "permission_denied"}
    result: dict[str, Any] = {
        "permission_decision": permission_decision,
    }
    if isinstance(request_id, str) and request_id:
        result["request_id"] = request_id
    if isinstance(trace_id, str) and trace_id:
        result["trace_id"] = trace_id
    if isinstance(reason_code, str) and reason_code:
        result["permission_reason"] = reason_code
    return result


def _is_permission_denied(response: dict[str, Any], bridge: dict[str, Any]) -> bool:
    error = response.get("error") if isinstance(response.get("error"), dict) else {}
    decision = bridge.get("permission_decision") if isinstance(bridge.get("permission_decision"), dict) else {}
    return error.get("code") == "permission_denied" or decision.get("decision") == "deny"


def _denied_surface_payload(
    surface: str, title: str, response: dict[str, Any], bridge: dict[str, Any]
) -> dict[str, Any]:
    error = response.get("error") if isinstance(response.get("error"), dict) else {}
    details = error.get("details") if isinstance(error.get("details"), dict) else {}
    reason_code = bridge.get("permission_reason") or details.get("reason_code") or "permission_denied"
    return {
        "surface": surface,
        "title": title,
        "status": "permission_denied",
        "candidate_id": details.get("candidate_id"),
        "memory_id": details.get("memory_id"),
        "version_id": details.get("version_id"),
        "type": None,
        "subject": None,
        "new_value": None,
        "summary": None,
        "evidence": {},
        "risk_flags": [],
        "recommended_action": "permission_denied",
        "conflict": {
            "has_conflict": False,
            "old_memory_id": None,
            "old_value": None,
            "old_status": None,
            "reason": None,
        },
        "buttons": [],
        "state_mutation": "none",
        "error": {
            "code": error.get("code") or "permission_denied",
            "message": "当前操作者没有权限执行这个审核动作。",
            "reason_code": reason_code,
        },
        **bridge,
    }


def _permission_denied_card(title: str, payload: dict[str, Any]) -> dict[str, Any]:
    fields = [
        ("状态", "permission_denied"),
        ("拒绝原因", str(payload.get("permission_reason") or "permission_denied")),
    ]
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "red",
            "title": {"tag": "plain_text", "content": title},
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": label not in {"拒绝原因"},
                        "text": {"tag": "lark_md", "content": f"**{label}**\n{value}"},
                    }
                    for label, value in fields
                ],
            },
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "权限不足，已安全拒绝；本卡片不会展示未授权的记忆内容或证据。"},
            },
        ],
    }


def _last_match(pattern: str, text: str) -> str | None:
    matches = re.findall(pattern, text)
    return matches[-1] if matches else None


def _candidate_index_from_line(line: str) -> int | None:
    match = re.match(r"\s*候选\s+(\d+)[：:]", line)
    return int(match.group(1)) if match else None


def _template_for(card_name: str, status: str | None) -> str:
    if "矛盾" in card_name or status == "superseded":
        return "orange"
    if "候选" in card_name or status == "candidate":
        return "turquoise"
    if "unknown" in (status or "") or "not_found" in (status or ""):
        return "grey"
    if "版本链" in card_name:
        return "blue"
    return "blue"
