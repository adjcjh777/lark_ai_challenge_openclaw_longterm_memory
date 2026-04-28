"""飞书任务 API 拉取模块。

从飞书任务 OpenAPI 拉取任务详情，提取文本进入 candidate pipeline。
"""

from __future__ import annotations

from typing import Any

from .document_ingestion import FeishuIngestionSource
from .feishu_api_client import FeishuApiResult, run_lark_cli


def fetch_feishu_task_text(
    task_id: str,
    *,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> FeishuIngestionSource:
    """从飞书任务 API 拉取任务详情，构造 FeishuIngestionSource。

    Args:
        task_id: 飞书任务 ID
        lark_cli: lark-cli 命令路径（默认 "lark-cli"）
        profile: lark-cli profile 名称
        as_identity: 身份切换（user/bot）

    Returns:
        FeishuIngestionSource: 包含任务文本和元数据的源对象

    Raises:
        ValueError: 当任务不存在或权限不足时
    """
    result = _fetch_task_detail(task_id, lark_cli=lark_cli, profile=profile, as_identity=as_identity)

    if not result.ok:
        raise ValueError(f"获取任务失败: {result.error_message} (error_code={result.error_code})")

    data = result.data
    if not data or "data" not in data:
        raise ValueError("获取任务失败: 返回数据为空")

    task_data = data["data"]
    task = task_data.get("task")
    if not task:
        raise ValueError("获取任务失败: 任务数据为空")

    # 提取任务信息
    title = task.get("title", f"任务 {task_id}")
    summary = task.get("summary", "")
    creator = task.get("creator", {})
    creator_id = creator.get("id", "unknown")
    due = task.get("due", {})
    due_timestamp = due.get("timestamp")
    status = task.get("status", "unknown")

    # 提取子任务信息
    subtasks = task.get("subtasks", [])
    subtask_text = ""
    if subtasks:
        subtask_lines = []
        for subtask in subtasks:
            subtask_title = subtask.get("title", "")
            subtask_status = subtask.get("status", "")
            if subtask_title:
                subtask_lines.append(f"- [{subtask_status}] {subtask_title}")
        if subtask_lines:
            subtask_text = "\n\n## 子任务\n" + "\n".join(subtask_lines)

    # 组合文本
    text_parts = []
    if title:
        text_parts.append(f"# {title}")
    if summary:
        text_parts.append(f"\n## 描述\n{summary}")
    if subtask_text:
        text_parts.append(subtask_text)

    combined_text = "\n".join(text_parts)
    if not combined_text.strip():
        raise ValueError("获取任务失败: 任务内容为空")

    # 构造 source metadata
    metadata: dict[str, Any] = {
        "task_status": status,
    }
    if due_timestamp:
        metadata["due_at"] = due_timestamp

    return FeishuIngestionSource(
        source_type="feishu_task",
        source_id=task_id,
        title=title,
        text=combined_text,
        actor_id=creator_id,
        source_url=f"https://feishu.cn/tasks/{task_id}",
        metadata=metadata,
    )


def list_feishu_tasks(
    *,
    page_size: int = 50,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> list[dict[str, Any]]:
    """列出当前用户的任务列表，用于批量拉取。

    Args:
        page_size: 每页任务数量（默认 50）
        lark_cli: lark-cli 命令路径
        profile: lark-cli profile 名称
        as_identity: 身份切换

    Returns:
        list[dict[str, Any]]: 任务列表，每个任务包含 task_id、title 等基本信息

    Raises:
        ValueError: 当 API 调用失败时
    """
    result = _list_tasks(page_size=page_size, lark_cli=lark_cli, profile=profile, as_identity=as_identity)

    if not result.ok:
        raise ValueError(f"获取任务列表失败: {result.error_message} (error_code={result.error_code})")

    data = result.data
    if not data or "data" not in data:
        return []

    items = data["data"].get("items", [])
    tasks = []

    for item in items:
        task_id = item.get("task_id", "")
        title = item.get("title", "")
        status = item.get("status", "")
        creator = item.get("creator", {})
        creator_id = creator.get("id", "")
        due = item.get("due", {})
        due_timestamp = due.get("timestamp")

        tasks.append(
            {
                "task_id": task_id,
                "title": title,
                "status": status,
                "creator_id": creator_id,
                "due_timestamp": due_timestamp,
            }
        )

    return tasks


def _fetch_task_detail(
    task_id: str,
    *,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> FeishuApiResult:
    """获取任务详情。"""
    argv = _build_argv(["task", "+get-task", "--task-id", task_id], profile=profile, as_identity=as_identity)
    return run_lark_cli(argv)


def _list_tasks(
    *,
    page_size: int = 50,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> FeishuApiResult:
    """获取任务列表。"""
    argv = _build_argv(
        ["task", "+get-my-tasks", "--page-size", str(page_size)],
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
