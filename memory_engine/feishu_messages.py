from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeishuCommand:
    name: str
    argument: str


def parse_command(text: str) -> FeishuCommand | None:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    head, _, tail = stripped.partition(" ")
    name = head[1:].strip().lower()
    argument = tail.strip()
    if name not in {"remember", "recall", "versions"}:
        return None
    if name in {"remember", "recall", "versions"} and not argument:
        return FeishuCommand(name="help", argument=name)
    return FeishuCommand(name=name, argument=argument)


def format_remember_reply(result: dict[str, Any]) -> str:
    action = result.get("action")
    memory = result.get("memory") or {}
    subject = memory.get("subject")
    memory_type = memory.get("type")
    if action == "superseded":
        return "\n".join(
            [
                "已更新记忆",
                f"主题：{subject}",
                f"类型：{memory_type}",
                f"新版本：{result.get('version')}",
                "旧版本已标记为 superseded",
                f"memory_id：{result.get('memory_id')}",
            ]
        )
    if action == "needs_manual_review":
        return "\n".join(
            [
                "检测到同主题不同内容，但没有明确覆盖意图。",
                "请用“不对/改成/以后统一”等表达确认覆盖。",
                f"主题：{subject}",
                f"memory_id：{result.get('memory_id')}",
            ]
        )
    if action == "duplicate":
        prefix = "这条记忆已经存在，已补充证据"
    else:
        prefix = "已记住"
    return "\n".join(
        [
            prefix,
            f"主题：{subject}",
            f"类型：{memory_type}",
            "状态：active",
            f"版本：{result.get('version')}",
            f"memory_id：{result.get('memory_id')}",
            "来源：当前消息",
        ]
    )


def format_recall_reply(result: dict[str, Any] | None) -> str:
    if result is None:
        return "未找到相关 active 记忆。\n可以用 /remember 先写入一条。"
    source = result.get("source") or {}
    return "\n".join(
        [
            f"命中记忆：{result.get('subject')}",
            f"当前有效规则：{result.get('answer')}",
            f"版本：{result.get('version')}",
            f"memory_id：{result.get('memory_id')}",
            f"证据：{source.get('quote')}",
        ]
    )


def format_versions_reply(memory_id: str, versions: list[dict[str, Any]]) -> str:
    if not versions:
        return f"未找到版本链：{memory_id}"
    lines = [f"版本链：{memory_id}"]
    for version in versions:
        lines.append(f"v{version.get('version_no')} [{version.get('status')}] {version.get('value')}")
    return "\n".join(lines)


def format_help(command_name: str) -> str:
    examples = {
        "remember": "/remember 生产部署必须加 --canary --region cn-shanghai",
        "recall": "/recall 生产部署参数",
        "versions": "/versions mem_xxx",
    }
    return f"命令缺少内容。\n示例：{examples.get(command_name, '/recall 生产部署参数')}"
