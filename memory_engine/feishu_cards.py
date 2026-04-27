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
    conflict = candidate_response.get("conflict") or candidate.get("conflict") or {}
    evidence = candidate_response.get("evidence") or candidate.get("evidence") or {}
    return {
        "surface": "copilot_candidate_review",
        "title": "待确认记忆",
        "candidate_id": candidate_response.get("candidate_id") or candidate.get("candidate_id"),
        "memory_id": candidate_response.get("memory_id") or candidate.get("memory_id"),
        "version_id": candidate_response.get("version_id") or candidate.get("version_id"),
        "status": candidate_response.get("status") or candidate.get("status"),
        "type": candidate.get("type"),
        "subject": candidate.get("subject"),
        "new_value": candidate.get("current_value"),
        "summary": candidate.get("summary"),
        "evidence": evidence,
        "risk_flags": list(candidate_response.get("risk_flags") or candidate.get("risk_flags") or []),
        "recommended_action": candidate_response.get("recommended_action") or candidate.get("recommended_action"),
        "conflict": {
            "has_conflict": bool(conflict.get("has_conflict")),
            "old_memory_id": conflict.get("old_memory_id"),
            "old_value": conflict.get("old_value"),
            "old_status": conflict.get("old_status"),
            "reason": conflict.get("reason"),
        },
        "buttons": [
            {"action": "confirm", "label": "确认保存", "required_for_mvp": True},
            {"action": "reject", "label": "拒绝候选", "required_for_mvp": True},
            {"action": "versions", "label": "查看版本链", "required_for_mvp": False, "mode": "dry_run"},
            {"action": "source", "label": "查看来源", "required_for_mvp": False, "mode": "dry_run"},
            {"action": "needs_review", "label": "标记需要复核", "required_for_mvp": False, "mode": "dry_run"},
        ],
        "state_mutation": "none",
        **bridge,
    }


def version_chain_payload(explain_versions_response: dict[str, Any]) -> dict[str, Any]:
    """Build a typed version-chain payload without mutating memory state."""

    bridge = _bridge_payload(explain_versions_response)
    if _is_permission_denied(explain_versions_response, bridge):
        return _denied_surface_payload("copilot_version_chain", "记忆版本链不可用", explain_versions_response, bridge)

    versions = explain_versions_response.get("versions") or []
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
        "buttons": [
            {"action": "source", "label": "查看来源", "required_for_mvp": False, "mode": "dry_run"},
            {"action": "needs_review", "label": "标记需要复核", "required_for_mvp": False, "mode": "dry_run"},
        ],
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
        "buttons": [
            {"action": "confirm_reminder", "label": "确认提醒", "required_for_mvp": False, "mode": "dry_run"},
            {"action": "dismiss_reminder", "label": "暂不提醒", "required_for_mvp": False, "mode": "dry_run"},
            {"action": "source", "label": "查看来源", "required_for_mvp": False, "mode": "dry_run"},
        ],
        "state_mutation": "none",
    }


def build_candidate_review_card(candidate_response: dict[str, Any]) -> dict[str, Any]:
    payload = candidate_review_payload(candidate_response)
    if payload.get("status") == "permission_denied":
        return _permission_denied_card("待确认记忆", payload)

    conflict = payload["conflict"]
    fields = [
        ("状态", str(payload.get("status") or "")),
        ("主题", str(payload.get("subject") or "")),
        ("新值", str(payload.get("new_value") or "")),
        ("证据", str((payload.get("evidence") or {}).get("quote") or "")),
        ("风险", ", ".join(payload.get("risk_flags") or []) or "无"),
        ("操作建议", str(payload.get("recommended_action") or "")),
    ]
    if conflict["has_conflict"]:
        fields.append(("覆盖旧值", str(conflict.get("old_value") or "")))

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "orange" if conflict["has_conflict"] else "turquoise",
            "title": {"tag": "plain_text", "content": "待确认记忆"},
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": label not in {"新值", "证据", "覆盖旧值"},
                        "text": {"tag": "lark_md", "content": f"**{label}**\n{value}"},
                    }
                    for label, value in fields
                ],
            },
            {
                "tag": "action",
                "actions": [
                    _button(
                        "确认保存",
                        "primary",
                        {CARD_ACTION_KEY: "confirm", "candidate_id": str(payload.get("candidate_id") or "")},
                    ),
                    _button(
                        "拒绝候选",
                        "danger",
                        {CARD_ACTION_KEY: "reject", "candidate_id": str(payload.get("candidate_id") or "")},
                    ),
                ],
            },
        ],
    }


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

    return {
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


def build_version_chain_card(explain_versions_response: dict[str, Any]) -> dict[str, Any]:
    payload = version_chain_payload(explain_versions_response)
    if payload.get("status") == "permission_denied":
        return _permission_denied_card("记忆版本链", payload)

    version_lines = []
    for item in payload["versions"]:
        marker = "当前" if item.get("is_active") else "旧值"
        inactive = f"；{item['inactive_reason']}" if item.get("inactive_reason") else ""
        version_lines.append(f"v{item['version']} [{item['status']}] {marker}：{item['value']}{inactive}")

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
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**主题**\n{payload.get('subject') or ''}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": f"**状态**\n{payload.get('status') or ''}"}},
                ],
            },
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "\n".join(version_lines)},
            },
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": str(payload.get("explanation") or "")},
            },
        ],
    }


def build_card_from_text(text: str) -> dict[str, Any]:
    fields = _fields_from_text(text)
    card_name = fields.get("卡片") or fields.get("类型") or "企业记忆卡片"
    title = _headline(text) or card_name
    template = _template_for(card_name, fields.get("状态"))
    core_labels = ("结论", "理由", "状态", "版本", "来源", "是否被覆盖")
    display_fields = [(label, fields[label]) for label in core_labels if fields.get(label)]
    for label in ("主题", "候选序号", "记忆类型", "memory_id", "版本数量", "request_id", "trace_id", "处理结果"):
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


def _button(label: str, button_type: str, value: dict[str, str]) -> dict[str, Any]:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": label},
        "type": button_type,
        "value": value,
    }


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


def _denied_surface_payload(surface: str, title: str, response: dict[str, Any], bridge: dict[str, Any]) -> dict[str, Any]:
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
        "conflict": {"has_conflict": False, "old_memory_id": None, "old_value": None, "old_status": None, "reason": None},
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
    if payload.get("request_id"):
        fields.append(("request_id", str(payload["request_id"])))
    if payload.get("trace_id"):
        fields.append(("trace_id", str(payload["trace_id"])))
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
