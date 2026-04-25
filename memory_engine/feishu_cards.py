from __future__ import annotations

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


def build_card_from_text(text: str) -> dict[str, Any]:
    fields = _fields_from_text(text)
    card_name = fields.get("卡片") or fields.get("类型") or "企业记忆卡片"
    title = _headline(text) or card_name
    template = _template_for(card_name, fields.get("状态"))
    core_labels = ("结论", "理由", "状态", "版本", "来源", "是否被覆盖")
    display_fields = [(label, fields[label]) for label in core_labels if fields.get(label)]
    for label in ("主题", "候选序号", "记忆类型", "memory_id", "版本数量", "处理结果"):
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
