from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

SUPPORTED_COMMANDS = frozenset({"remember", "recall", "versions", "help", "health", "ingest_doc", "confirm", "reject"})


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
    if name not in SUPPORTED_COMMANDS:
        return FeishuCommand(name="unknown", argument=argument, raw_name=name or head)
    if name in {"help", "health"}:
        return FeishuCommand(name=name, argument=argument, raw_name=name)
    if name in {"remember", "recall", "versions", "ingest_doc", "confirm", "reject"} and not argument:
        return FeishuCommand(name="help", argument=name, raw_name=name)
    return FeishuCommand(name=name, argument=argument, raw_name=name)


def format_remember_reply(result: dict[str, Any]) -> str:
    action = result.get("action")
    memory = result.get("memory") or {}
    subject = memory.get("subject")
    memory_type = memory.get("type")
    reason = _reason(memory.get("reason"))
    if action == "superseded":
        old_rule = _redact_sensitive_text(result.get("superseded_value") or "-")
        new_rule = _redact_sensitive_text(memory.get("current_value") or "-")
        return _reply(
            "矛盾更新卡片：旧规则已被新规则覆盖。",
            [
                "类型：记忆更新",
                "卡片：矛盾更新卡片",
                f"结论：{new_rule}",
                f"理由：{reason}",
                f"主题：{subject}",
                "状态：active",
                f"版本：v{result.get('version')}",
                "来源：当前飞书消息",
                "是否被覆盖：否（这是当前有效版本）",
                f"旧规则 -> 新规则：{old_rule} -> {new_rule}",
                f"旧版本状态：{result.get('superseded_status')}",
                f"记忆类型：{memory_type}",
                "处理结果：旧版本已标记为 superseded，新版本已生效。",
                f"memory_id：{result.get('memory_id')}",
            ],
        )
    if action == "needs_manual_review":
        return _reply(
            "待确认记忆卡片：同一主题出现不同说法，需要人工确认。",
            [
                "类型：待确认记忆",
                "卡片：人工确认提示",
                f"结论：{_redact_sensitive_text(memory.get('current_value') or '-')}",
                f"理由：{reason}",
                f"主题：{subject}",
                "状态：needs_manual_review",
                f"版本：v{result.get('version')}",
                "来源：当前飞书消息",
                "是否被覆盖：否（尚未确认覆盖）",
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
        "记忆确认卡片：已保存为当前有效企业记忆。",
        [
            f"类型：{prefix}",
            "卡片：记忆确认卡片",
            f"结论：{_redact_sensitive_text(memory.get('current_value') or '-')}",
            f"理由：{reason}",
            f"主题：{subject}",
            "状态：active",
            f"版本：v{result.get('version')}",
            "来源：当前飞书消息",
            "是否被覆盖：否",
            f"记忆类型：{memory_type}",
            f"memory_id：{result.get('memory_id')}",
        ],
    )


def format_recall_reply(result: dict[str, Any] | None) -> str:
    if result is None:
        return _reply(
            "历史决策卡片：暂时没找到当前有效记忆。",
            [
                "类型：记忆召回",
                "卡片：历史决策卡片",
                "结论：未命中",
                "理由：当前 scope 内没有匹配的 active 记忆",
                "主题：未命中",
                "状态：not_found",
                "版本：-",
                "来源：Memory Engine",
                "是否被覆盖：-",
                "处理结果：未找到相关 active 记忆。",
                "下一步：可以用 /remember 先写入一条。",
            ],
        )
    source = result.get("source") or {}
    source_label = _source_label(source)
    answer = _redact_sensitive_text(result.get("answer") or "-")
    quote = _redact_sensitive_text(source.get("quote") or "-")
    return _reply(
        f"历史决策卡片：当前有效结论是 {answer}",
        [
            "类型：记忆召回",
            "卡片：历史决策卡片",
            f"结论：{answer}",
            "理由：按主题匹配 active 记忆，并返回最新有效版本",
            f"主题：{result.get('subject')}",
            f"状态：{result.get('status')}",
            f"版本：v{result.get('version')}",
            f"来源：{source_label}",
            "是否被覆盖：否（当前 active 版本）",
            f"记忆类型：{result.get('type')}",
            f"当前有效规则：{answer}",
            f"memory_id：{result.get('memory_id')}",
            f"证据：{quote}",
        ],
    )


def format_versions_reply(memory_id: str, versions: list[dict[str, Any]]) -> str:
    if not versions:
        return _reply(
            "版本链卡片：没有找到这条记忆的版本链。",
            [
                "类型：版本链",
                "卡片：版本链卡片",
                "结论：未命中",
                "理由：当前 memory_id 没有对应版本记录",
                f"主题：{memory_id}",
                "状态：not_found",
                "版本：-",
                "来源：Memory Engine",
                "是否被覆盖：-",
                "处理结果：未找到版本链。",
            ],
        )
    active = next((version for version in versions if version.get("status") == "active"), versions[-1])
    active_value = _redact_sensitive_text(active.get("value") or "-")
    lines = [
        "类型：版本链",
        "卡片：版本链卡片",
        f"结论：{active_value}",
        "理由：展示同一 memory_id 的 active/superseded/rejected 版本链",
        f"主题：{memory_id}",
        f"状态：{active.get('status')}",
        f"版本：v{active.get('version_no')}",
        "来源：Memory Engine",
        f"是否被覆盖：{_overwritten_label(active.get('status'))}",
        f"版本数量：{len(versions)}",
        "历史版本：",
    ]
    for version in versions:
        status = version.get("status")
        value = _redact_sensitive_text(version.get("value") or "-")
        lines.append(f"v{version.get('version_no')} [{status}] 是否被覆盖：{_overwritten_label(status)}｜{value}")
    return _reply("版本链卡片：active 版本是当前有效企业记忆。", lines)


def format_ingest_doc_reply(result: dict[str, Any]) -> str:
    document = result.get("document") or {}
    candidates = result.get("candidates") or []
    source_label = f"文档《{document.get('title') or '-'}》/ {_mask_identifier(str(document.get('token') or '-'))}"
    lines = [
        "类型：文档 ingestion",
        "卡片：人工确认队列",
        "结论：已抽取候选记忆，等待人工确认",
        "理由：文档 ingestion 先进入 candidate 状态，确认后才成为 active 企业记忆",
        f"主题：{document.get('title') or '-'}",
        "状态：candidate",
        "版本：Day 5",
        f"来源：{source_label}",
        "是否被覆盖：否（candidate 尚未进入 active 版本链）",
        f"候选数量：{result.get('candidate_count', 0)}",
        f"重复数量：{result.get('duplicate_count', 0)}",
        "候选列表：",
    ]
    candidate_index = 0
    for candidate in candidates[:8]:
        memory = candidate.get("memory") or {}
        confidence = float(memory.get("confidence") or 0)
        review_hint = "，需人工确认" if confidence < 0.7 else ""
        candidate_text = _redact_sensitive_text(candidate.get("quote") or memory.get("current_value") or "")
        candidate_id = candidate.get("memory_id")
        prefix = "已生效"
        action_hint = ""
        if candidate.get("status") == "candidate":
            candidate_index += 1
            prefix = f"候选 {candidate_index}"
            action_hint = f"；建议动作：/confirm {candidate_id} 或 /reject {candidate_id}"
        lines.append(
            f"{prefix}：{candidate_id} [{candidate.get('status')}] {memory.get('subject')}："
            f"{candidate_text}（confidence={confidence:.2f}{review_hint}{action_hint}）"
        )
    lines.append("下一步：用 /confirm <candidate_id> 激活，或 /reject <candidate_id> 拒绝。")
    low_confidence_count = sum(
        1 for candidate in candidates if float((candidate.get("memory") or {}).get("confidence") or 0) < 0.7
    )
    if low_confidence_count:
        lines.append(f"人工确认提示：{low_confidence_count} 条候选置信度低于 0.70，Demo 时建议先确认再召回。")
    return _reply("已从文档抽取候选记忆，等待人工确认。", lines)


def format_candidate_action_reply(
    result: dict[str, Any] | None,
    *,
    action: str,
    candidate_id: str,
    candidate_label: str | None = None,
) -> str:
    label_line = f"候选序号：{candidate_label}" if candidate_label else None
    if result is None:
        lines = [
            f"类型：候选记忆{action}",
            "卡片：候选确认卡片",
            "结论：未命中",
            "理由：candidate_id 不存在",
            f"主题：{candidate_id}",
            "状态：not_found",
            "版本：-",
            "来源：Memory Engine",
            "是否被覆盖：-",
        ]
        if label_line:
            lines.insert(5, label_line)
        return _reply(f"候选记忆{action}卡片：没有找到这条候选记忆。", lines)
    value = _redact_sensitive_text(result.get("current_value") or "-")
    lines = [
        f"类型：候选记忆{action}",
        "卡片：候选确认卡片",
        f"结论：{value}",
        f"理由：人工执行 /{_candidate_action_command(action)} 后更新 candidate 状态",
        f"主题：{result.get('subject') or result.get('memory_id')}",
        f"状态：{result.get('status')}",
        "版本：Day 5",
        "来源：Memory Engine",
        f"是否被覆盖：{_overwritten_label(result.get('status'))}",
        f"memory_id：{result.get('memory_id')}",
        f"处理结果：{result.get('action')}",
    ]
    if label_line:
        lines.insert(5, label_line)
    return _reply(
        f"候选记忆{action}卡片：{candidate_label + ' ' if candidate_label else ''}候选状态已更新。",
        lines,
    )


def format_help(command_name: str) -> str:
    examples = {
        "remember": "缺少要记住的内容。\n示例：/remember 生产部署必须加 --canary --region cn-shanghai",
        "recall": "缺少召回查询。\n示例：/recall 生产部署参数",
        "versions": "缺少 memory_id。\n示例：/versions mem_xxx",
        "ingest_doc": "缺少文档 URL、token 或本地 Markdown 路径。\n示例：/ingest_doc docs/day5-doc-ingestion-fixture.md",
        "confirm": "缺少 candidate_id。\n示例：/confirm mem_xxx",
        "reject": "缺少 candidate_id。\n示例：/reject mem_xxx",
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
            "/ingest_doc <url_or_token>  从飞书文档或 Markdown 抽取候选记忆",
            "/confirm <candidate_id>  确认候选记忆为 active",
            "/reject <candidate_id>   拒绝候选记忆",
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
            f"命令白名单：{', '.join(f'/{name}' for name in sorted(SUPPORTED_COMMANDS))}",
            "处理结果：暂不支持这个命令，已按白名单拦截。",
            "下一步：发送 /help 查看可用命令和 Demo 推荐输入。",
        ],
    )


def _reply(headline: str, fields: list[str]) -> str:
    return "\n".join([headline, "", *fields])


def _reason(value: Any) -> str:
    text = str(value or "").strip()
    return text or "来自当前指令和证据链"


def _source_label(source: dict[str, Any]) -> str:
    source_type = source.get("source_type") or "unknown"
    if source.get("document_title"):
        token = source.get("document_token") or source.get("source_id") or "-"
        return f"文档《{source.get('document_title')}》/ {_mask_identifier(str(token))}"
    source_id = source.get("source_id") or "-"
    return f"{source_type} / {_mask_identifier(str(source_id))}"


def _mask_identifier(value: str) -> str:
    value = value.strip()
    if not value or value == "-":
        return "-"
    if "/" in value:
        value = value.rsplit("/", 1)[-1] or value
    if len(value) <= 10:
        return value
    return f"{value[:4]}...{value[-4:]}"


def _redact_sensitive_text(value: str) -> str:
    text = str(value)
    text = _SECRET_ASSIGNMENT_RE.sub(r"\1=[REDACTED]", text)
    text = _TOKEN_LIKE_RE.sub("[REDACTED_TOKEN]", text)
    text = _INTERNAL_URL_RE.sub("[REDACTED_URL]", text)
    return text


def _overwritten_label(status: Any) -> str:
    if status == "active":
        return "否（当前 active 版本）"
    if status == "candidate":
        return "否（等待人工确认）"
    if status in {"superseded", "rejected"}:
        return "是"
    return "-"


def _candidate_action_command(action: str) -> str:
    return "confirm" if action == "确认" else "reject"


_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|CREDENTIAL|API_KEY)[A-Z0-9_]*)\s*=\s*[^\s，。；;]+"
)
_TOKEN_LIKE_RE = re.compile(r"\b(?:lark|feishu|sk|pat|ghp)_[A-Za-z0-9_=-]{12,}\b")
_INTERNAL_URL_RE = re.compile(r"https?://(?:[^\s/]+\.)?(?:internal|corp|bytedance)\.[^\s，。；;]+")
