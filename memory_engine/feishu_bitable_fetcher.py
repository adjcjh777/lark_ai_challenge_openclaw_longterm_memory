"""飞书多维表格（Bitable）记录读取模块。

从飞书多维表格 API 拉取记录内容，提取文本进入 candidate pipeline。
"""

from __future__ import annotations

from typing import Any

from .document_ingestion import FeishuIngestionSource
from .feishu_api_client import FeishuApiResult, run_lark_cli


def fetch_bitable_record_text(
    app_token: str,
    table_id: str,
    record_id: str,
    *,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> FeishuIngestionSource:
    """从 Bitable API 拉取单条记录，构造 FeishuIngestionSource。

    Args:
        app_token: Bitable 应用 token
        table_id: 表格 ID
        record_id: 记录 ID
        lark_cli: lark-cli 命令路径（默认 "lark-cli"）
        profile: lark-cli profile 名称
        as_identity: 身份切换（user/bot）

    Returns:
        FeishuIngestionSource: 包含记录文本和元数据的源对象

    Raises:
        ValueError: 当记录不存在或权限不足时
    """
    result = _fetch_record(app_token, table_id, record_id, lark_cli=lark_cli, profile=profile, as_identity=as_identity)

    if not result.ok:
        raise ValueError(f"获取 Bitable 记录失败: {result.error_message} (error_code={result.error_code})")

    data = result.data
    if not data or "data" not in data:
        raise ValueError("获取 Bitable 记录失败: 返回数据为空")

    record_data = data["data"]
    record = record_data.get("record")
    if not record:
        raise ValueError("获取 Bitable 记录失败: 记录数据为空")

    # 提取字段文本
    fields = record.get("fields", record)
    if not fields:
        raise ValueError("获取 Bitable 记录失败: 记录字段为空")

    # 提取文本
    text_parts = []
    field_names = []

    for field_name, field_value in fields.items():
        # 跳过系统字段
        if field_name in {"created_by", "created_at", "updated_by", "updated_at", "record_id"}:
            continue

        # 提取文本值
        text_value = _extract_field_value(field_value)
        if text_value:
            text_parts.append(f"**{field_name}**: {text_value}")
            field_names.append(field_name)

    combined_text = "\n".join(text_parts)
    if not combined_text.strip():
        raise ValueError("获取 Bitable 记录失败: 无法提取有效文本")

    return FeishuIngestionSource(
        source_type="lark_bitable",
        source_id=record_id,
        title=f"Bitable Record {record_id}",
        text=combined_text,
        actor_id="bitable_fetch",
        metadata={
            "app_token": app_token,
            "table_id": table_id,
            "record_id": record_id,
            "field_names": field_names,
        },
    )


def list_bitable_records(
    app_token: str,
    table_id: str,
    *,
    limit: int = 100,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> list[dict[str, Any]]:
    """列出 Bitable 表格记录，用于批量拉取。

    Args:
        app_token: Bitable 应用 token
        table_id: 表格 ID
        limit: 最大返回记录数（默认 100）
        lark_cli: lark-cli 命令路径
        profile: lark-cli profile 名称
        as_identity: 身份切换

    Returns:
        list[dict[str, Any]]: 记录列表，每个记录包含 record_id 和字段摘要

    Raises:
        ValueError: 当 API 调用失败时
    """
    result = _list_records(
        app_token, table_id, limit=limit, lark_cli=lark_cli, profile=profile, as_identity=as_identity
    )

    if not result.ok:
        raise ValueError(f"获取 Bitable 记录列表失败: {result.error_message} (error_code={result.error_code})")

    data = result.data
    if not data or "data" not in data:
        return []

    payload = data["data"]
    items = payload.get("items", [])
    records = []

    if not items and isinstance(payload.get("data"), list):
        field_names = [str(item) for item in payload.get("fields", [])]
        record_ids = [str(item) for item in payload.get("record_id_list", [])]
        for index, row in enumerate(payload.get("data", [])):
            values = row if isinstance(row, list) else []
            items.append(
                {
                    "record_id": record_ids[index] if index < len(record_ids) else "",
                    "fields": dict(zip(field_names, values)),
                }
            )

    for item in items:
        record_id = item.get("record_id", "")
        fields = item.get("fields", {})

        # 提取字段摘要
        summary_parts = []
        for field_name, field_value in fields.items():
            if field_name in {"created_by", "created_at", "updated_by", "updated_at"}:
                continue
            text_value = _extract_field_value(field_value)
            if text_value:
                # 截断过长的值
                if len(text_value) > 100:
                    text_value = text_value[:100] + "..."
                summary_parts.append(f"{field_name}: {text_value}")

        summary = "; ".join(summary_parts[:5])  # 最多显示 5 个字段
        if len(summary_parts) > 5:
            summary += f" ... (共 {len(summary_parts)} 个字段)"

        records.append(
            {
                "record_id": record_id,
                "field_count": len(fields),
                "summary": summary,
            }
        )

    return records


def list_bitable_tables(
    app_token: str,
    *,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> list[dict[str, Any]]:
    """列出 Bitable 应用中的表格列表。

    Args:
        app_token: Bitable 应用 token
        lark_cli: lark-cli 命令路径
        profile: lark-cli profile 名称
        as_identity: 身份切换

    Returns:
        list[dict[str, Any]]: 表格列表，每个表格包含 table_id 和名称

    Raises:
        ValueError: 当 API 调用失败时
    """
    result = _list_tables(app_token, lark_cli=lark_cli, profile=profile, as_identity=as_identity)

    if not result.ok:
        raise ValueError(f"获取 Bitable 表格列表失败: {result.error_message} (error_code={result.error_code})")

    data = result.data
    if not data or "data" not in data:
        return []

    payload = data["data"]
    items = payload.get("items") or payload.get("tables") or []
    tables = []

    for item in items:
        table_id = item.get("table_id") or item.get("id") or ""
        name = item.get("name", "")
        revision = item.get("revision", 0)

        tables.append(
            {
                "table_id": table_id,
                "name": name,
                "revision": revision,
            }
        )

    return tables


def _fetch_record(
    app_token: str,
    table_id: str,
    record_id: str,
    *,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> FeishuApiResult:
    """获取单条记录。"""
    argv = _build_argv(
        [
            "base",
            "+record-get",
            "--base-token",
            app_token,
            "--table-id",
            table_id,
            "--record-id",
            record_id,
        ],
        profile=profile,
        as_identity=as_identity,
    )
    return run_lark_cli(argv)


def _list_records(
    app_token: str,
    table_id: str,
    *,
    limit: int = 100,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> FeishuApiResult:
    """获取记录列表。"""
    argv = _build_argv(
        [
            "base",
            "+record-list",
            "--base-token",
            app_token,
            "--table-id",
            table_id,
            "--limit",
            str(limit),
        ],
        profile=profile,
        as_identity=as_identity,
    )
    return run_lark_cli(argv)


def _list_tables(
    app_token: str,
    *,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> FeishuApiResult:
    """获取表格列表。"""
    argv = _build_argv(
        ["base", "+table-list", "--base-token", app_token],
        profile=profile,
        as_identity=as_identity,
    )
    return run_lark_cli(argv)


def _build_argv(
    command: list[str],
    *,
    profile: str | None = None,
    as_identity: str | None = None,
) -> list[str]:
    """构建 lark-cli 命令参数。"""
    argv = []
    if profile:
        argv.extend(["--profile", profile])
    if as_identity:
        argv.extend(["--as", as_identity])
    argv.extend(command)
    return argv


def _extract_field_value(value: Any) -> str:
    """从字段值中提取文本。"""
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, bool):
        return "是" if value else "否"

    if isinstance(value, (int, float)):
        return str(value)

    if isinstance(value, list):
        # 处理多选、人员等数组字段
        texts = []
        for item in value:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict):
                # 人员字段
                name = item.get("name") or item.get("en_name")
                if name:
                    texts.append(name)
                else:
                    texts.append(str(item))
            else:
                texts.append(str(item))
        return ", ".join(texts)

    if isinstance(value, dict):
        # 处理单选、URL 等对象字段
        text = value.get("text") or value.get("name") or value.get("link")
        if text:
            return str(text)
        return str(value)

    return str(value)
