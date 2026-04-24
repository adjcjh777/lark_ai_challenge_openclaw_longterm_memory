from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeishuCommand:
    name: str
    argument: str
    raw_name: str | None = None


def parse_command(text: str) -> FeishuCommand | None:
    stripped = text.strip()
    if not stripped:
        return FeishuCommand(name="empty", argument="")
    if not stripped.startswith("/"):
        return FeishuCommand(name="unknown", argument=stripped, raw_name=stripped.split()[0])
    head, _, tail = stripped.partition(" ")
    name = head[1:].strip().lower()
    argument = tail.strip()
    if name not in {"remember", "recall", "versions", "help", "health"}:
        return FeishuCommand(name="unknown", argument=argument, raw_name=name or head)
    if name in {"help", "health"}:
        return FeishuCommand(name=name, argument=argument, raw_name=name)
    if name in {"remember", "recall", "versions"} and not argument:
        return FeishuCommand(name="help", argument=name, raw_name=name)
    return FeishuCommand(name=name, argument=argument, raw_name=name)


def format_remember_reply(result: dict[str, Any]) -> str:
    action = result.get("action")
    memory = result.get("memory") or {}
    subject = memory.get("subject")
    memory_type = memory.get("type")
    if action == "superseded":
        return _reply(
            "已更新这条记忆，后续召回会优先使用新版本。",
            [
                "类型：记忆更新",
                f"主题：{subject}",
                "状态：active",
                f"版本：v{result.get('version')}",
                "来源：当前飞书消息",
                f"记忆类型：{memory_type}",
                "处理结果：旧版本已标记为 superseded，新版本已生效。",
                f"memory_id：{result.get('memory_id')}",
            ],
        )
    if action == "needs_manual_review":
        return _reply(
            "我发现同一主题出现了不同说法，需要你明确是否覆盖旧记忆。",
            [
                "类型：待确认记忆",
                f"主题：{subject}",
                "状态：needs_manual_review",
                f"版本：v{result.get('version')}",
                "来源：当前飞书消息",
                f"记忆类型：{memory_type}",
                "处理结果：检测到同主题不同内容，但没有明确覆盖意图。",
                "下一步：请用“不对/改成/以后统一”等表达确认覆盖。",
                f"memory_id：{result.get('memory_id')}",
            ],
        )
    if action == "duplicate":
        prefix = "这条记忆已经存在，已补充证据"
    else:
        prefix = "已记住"
    return _reply(
        "已保存为当前有效记忆，后续可以直接召回。",
        [
            f"类型：{prefix}",
            f"主题：{subject}",
            "状态：active",
            f"版本：v{result.get('version')}",
            "来源：当前飞书消息",
            f"记忆类型：{memory_type}",
            f"memory_id：{result.get('memory_id')}",
        ],
    )


def format_recall_reply(result: dict[str, Any] | None) -> str:
    if result is None:
        return _reply(
            "暂时没找到当前有效记忆。",
            [
                "类型：记忆召回",
                "主题：未命中",
                "状态：not_found",
                "版本：-",
                "来源：Memory Engine",
                "处理结果：未找到相关 active 记忆。",
                "下一步：可以用 /remember 先写入一条。",
            ],
        )
    source = result.get("source") or {}
    return _reply(
        f"当前有效结论：{result.get('answer')}",
        [
            "类型：记忆召回",
            f"主题：{result.get('subject')}",
            f"状态：{result.get('status')}",
            f"版本：v{result.get('version')}",
            f"来源：{source.get('source_type') or 'unknown'} / {source.get('source_id') or '-'}",
            f"记忆类型：{result.get('type')}",
            f"当前有效规则：{result.get('answer')}",
            f"memory_id：{result.get('memory_id')}",
            f"证据：{source.get('quote')}",
        ],
    )


def format_versions_reply(memory_id: str, versions: list[dict[str, Any]]) -> str:
    if not versions:
        return _reply(
            "没有找到这条记忆的版本链。",
            [
                "类型：版本链",
                f"主题：{memory_id}",
                "状态：not_found",
                "版本：-",
                "来源：Memory Engine",
                "处理结果：未找到版本链。",
            ],
        )
    active = next((version for version in versions if version.get("status") == "active"), versions[-1])
    lines = [
        "类型：版本链",
        f"主题：{memory_id}",
        f"状态：{active.get('status')}",
        f"版本：v{active.get('version_no')}",
        "来源：Memory Engine",
        f"版本数量：{len(versions)}",
    ]
    for version in versions:
        lines.append(f"v{version.get('version_no')} [{version.get('status')}] {version.get('value')}")
    return _reply("这是这条记忆的版本链，active 版本是当前有效结论。", lines)


def format_help(command_name: str) -> str:
    examples = {
        "remember": "缺少要记住的内容。\n示例：/remember 生产部署必须加 --canary --region cn-shanghai",
        "recall": "缺少召回查询。\n示例：/recall 生产部署参数",
        "versions": "缺少 memory_id。\n示例：/versions mem_xxx",
    }
    if command_name in examples:
        return _reply(
            "这条命令还缺少必要内容。",
            [
                "类型：命令帮助",
                f"主题：/{command_name}",
                "状态：invalid_args",
                "版本：-",
                "来源：Memory Engine",
                examples[command_name],
            ],
        )
    return _reply(
        "我可以帮你记住、召回和查看团队决策的版本链。",
        [
            "类型：命令帮助",
            "主题：Feishu Memory Engine",
            "状态：ok",
            "版本：-",
            "来源：Memory Engine",
            "可用命令：",
            "/remember <内容>  记住一条决策、流程或偏好",
            "/recall <问题>    召回当前有效记忆",
            "/versions <memory_id>  查看版本链",
            "/health           查看运行状态",
            "/help             查看本帮助",
            "Demo 推荐输入：",
            "/remember 生产部署必须加 --canary --region cn-shanghai",
            "/recall 生产部署参数",
            "/remember 不对，生产部署 region 改成 ap-shanghai",
            "/recall 生产部署 region",
        ],
    )


def format_health(*, db_path: str, default_scope: str, dry_run: bool, bot_mode: str) -> str:
    return _reply(
        "Bot 当前可用，下面是本次运行状态。",
        [
            "类型：健康检查",
            "主题：Feishu Memory Engine Bot",
            "状态：ok",
            "版本：Day 3",
            "来源：Memory Engine",
            f"数据库：{db_path}",
            f"默认 scope：{default_scope}",
            f"dry-run：{str(dry_run).lower()}",
            f"回复模式：{bot_mode}",
        ],
    )


def format_ignored_reply(reason: str) -> str:
    reason_text = {
        "empty text message": "收到空消息，未写入记忆。",
    }.get(reason, reason)
    if reason.startswith("non-text message:"):
        reason_text = "暂时只支持文本消息，请用 /help 查看可用命令。"
    return _reply(
        "这条消息没有进入记忆处理流程。",
        [
            "类型：消息处理",
            "主题：输入消息",
            "状态：ignored",
            "版本：-",
            "来源：当前飞书消息",
            f"处理结果：{reason_text}",
        ],
    )


def format_duplicate_reply() -> str:
    return _reply(
        "这条消息之前已经处理过，不会重复写入。",
        [
            "类型：消息处理",
            "主题：重复投递",
            "状态：duplicate",
            "版本：-",
            "来源：当前飞书消息",
            "处理结果：这条飞书消息已处理过，已跳过重复写入。",
        ],
    )


def format_unknown_command_reply(raw_name: str | None) -> str:
    command = f"/{raw_name}" if raw_name and not raw_name.startswith("/") else (raw_name or "当前输入")
    return _reply(
        "我还不支持这个命令，可以发送 /help 查看可用入口。",
        [
            "类型：命令处理",
            f"主题：{command}",
            "状态：unknown_command",
            "版本：-",
            "来源：当前飞书消息",
            "处理结果：暂不支持这个命令。",
            "下一步：发送 /help 查看可用命令和 Demo 推荐输入。",
        ],
    )


def _reply(headline: str, fields: list[str]) -> str:
    return "\n".join([headline, "", *fields])
