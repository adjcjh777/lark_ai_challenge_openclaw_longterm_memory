from __future__ import annotations

from typing import Any


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
