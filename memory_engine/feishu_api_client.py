"""统一的飞书 API 客户端，封装 lark-cli 调用。

提供统一的错误处理、重试机制和结果解析。
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeishuApiResult:
    """飞书 API 调用结果。"""

    ok: bool
    data: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    raw_stdout: str = ""
    raw_stderr: str = ""
    returncode: int = 0

    @property
    def is_permission_denied(self) -> bool:
        return self.error_code == "permission_denied"

    @property
    def is_resource_not_found(self) -> bool:
        return self.error_code == "resource_not_found"

    @property
    def is_api_error(self) -> bool:
        return self.error_code == "api_error"

    @property
    def is_parse_error(self) -> bool:
        return self.error_code == "parse_error"


def run_lark_cli(
    argv: list[str],
    *,
    retries: int = 2,
    timeout_seconds: int = 30,
) -> FeishuApiResult:
    """统一的 lark-cli 调用入口，带重试和错误分类。

    Args:
        argv: lark-cli 命令参数列表（不包含 "lark-cli" 本身）
        retries: 重试次数（默认 2 次）
        timeout_seconds: 超时时间（默认 30 秒）

    Returns:
        FeishuApiResult: 包含成功数据或错误信息的结果对象
    """
    last_error: FeishuApiResult | None = None

    for attempt in range(retries + 1):
        try:
            result = _execute_lark_cli(argv, timeout_seconds)
            if result.ok:
                return result

            # 权限错误和资源不存在不重试
            if result.is_permission_denied or result.is_resource_not_found:
                return result

            # 其他错误可以重试
            last_error = result
            if attempt < retries:
                # 指数退避
                time.sleep(min(2 ** attempt, 4))
                continue

            return result

        except subprocess.TimeoutExpired:
            last_error = FeishuApiResult(
                ok=False,
                error_code="api_error",
                error_message=f"lark-cli 命令超时（{timeout_seconds} 秒）",
                returncode=-1,
            )
            if attempt < retries:
                time.sleep(min(2 ** attempt, 4))
                continue

        except FileNotFoundError:
            return FeishuApiResult(
                ok=False,
                error_code="api_error",
                error_message="lark-cli 未安装或不在 PATH 中",
                returncode=-1,
            )

        except Exception as e:
            last_error = FeishuApiResult(
                ok=False,
                error_code="api_error",
                error_message=f"执行 lark-cli 时发生异常: {e}",
                returncode=-1,
            )
            if attempt < retries:
                time.sleep(min(2 ** attempt, 4))
                continue

    # 所有重试都失败
    return last_error or FeishuApiResult(
        ok=False,
        error_code="api_error",
        error_message="未知错误",
        returncode=-1,
    )


def _execute_lark_cli(argv: list[str], timeout_seconds: int) -> FeishuApiResult:
    """执行单次 lark-cli 命令。"""
    command = ["lark-cli"] + argv

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        raise

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    returncode = completed.returncode

    # 命令执行失败
    if returncode != 0:
        error_code, error_message = _classify_error(returncode, stdout, stderr)
        return FeishuApiResult(
            ok=False,
            error_code=error_code,
            error_message=error_message,
            raw_stdout=stdout,
            raw_stderr=stderr,
            returncode=returncode,
        )

    # 尝试解析 JSON
    try:
        data = json.loads(stdout) if stdout else {}
        return FeishuApiResult(
            ok=True,
            data=data,
            raw_stdout=stdout,
            raw_stderr=stderr,
            returncode=returncode,
        )
    except json.JSONDecodeError:
        # JSON 解析失败，尝试作为纯文本处理
        if stdout:
            return FeishuApiResult(
                ok=True,
                data={"text": stdout},
                raw_stdout=stdout,
                raw_stderr=stderr,
                returncode=returncode,
            )
        return FeishuApiResult(
            ok=False,
            error_code="parse_error",
            error_message="无法解析 lark-cli 输出为 JSON",
            raw_stdout=stdout,
            raw_stderr=stderr,
            returncode=returncode,
        )


def _classify_error(returncode: int, stdout: str, stderr: str) -> tuple[str, str]:
    """根据返回码和输出分类错误。"""
    combined_output = f"{stdout} {stderr}".lower()

    # 权限错误
    if any(keyword in combined_output for keyword in [
        "permission denied",
        "access denied",
        "forbidden",
        "403",
        "no permission",
        "权限",
    ]):
        return "permission_denied", f"权限不足: {stderr or stdout}"

    # 资源不存在
    if any(keyword in combined_output for keyword in [
        "not found",
        "404",
        "resource not found",
        "不存在",
        "找不到",
    ]):
        return "resource_not_found", f"资源不存在: {stderr or stdout}"

    # 网络/限流错误
    if any(keyword in combined_output for keyword in [
        "rate limit",
        "too many requests",
        "429",
        "timeout",
        "network",
        "限流",
        "超时",
    ]):
        return "api_error", f"API 调用失败（网络/限流）: {stderr or stdout}"

    # 其他错误
    return "api_error", f"lark-cli 执行失败 (returncode={returncode}): {stderr or stdout}"


def extract_text_from_result(result: FeishuApiResult) -> str:
    """从 API 结果中提取文本内容。

    用于处理 lark-cli 返回的 JSON 结构，提取实际的文本内容。
    """
    if not result.ok or result.data is None:
        return ""

    data = result.data

    # 处理 {"text": "..."} 格式（纯文本降级）
    if "text" in data and isinstance(data["text"], str):
        return data["text"]

    # 处理 {"data": {"document": {"content": "..."}}} 格式
    if "data" in data:
        inner = data["data"]
        if isinstance(inner, dict):
            # 文档格式
            document = inner.get("document")
            if isinstance(document, dict):
                content = document.get("content")
                if isinstance(content, str):
                    return content

            # 任务格式
            task = inner.get("task")
            if isinstance(task, dict):
                return _extract_task_text(task)

            # 会议格式
            minute = inner.get("minute")
            if isinstance(minute, dict):
                return _extract_meeting_text(minute)

            # Bitable 记录格式
            record = inner.get("record")
            if isinstance(record, dict):
                return _extract_bitable_record_text(record)

    # 无法识别的格式，返回原始 JSON
    return json.dumps(data, ensure_ascii=False, indent=2)


def _extract_task_text(task: dict[str, Any]) -> str:
    """从任务数据中提取文本。"""
    parts = []

    # 任务标题
    title = task.get("title")
    if title:
        parts.append(f"# {title}")

    # 任务描述
    summary = task.get("summary")
    if summary:
        parts.append(f"\n## 描述\n{summary}")

    # 子任务
    subtasks = task.get("subtasks")
    if isinstance(subtasks, list) and subtasks:
        parts.append("\n## 子任务")
        for subtask in subtasks:
            if isinstance(subtask, dict):
                subtask_title = subtask.get("title", "")
                subtask_status = subtask.get("status", "")
                parts.append(f"- [{subtask_status}] {subtask_title}")

    # 截止时间
    due = task.get("due")
    if isinstance(due, dict):
        timestamp = due.get("timestamp")
        if timestamp:
            parts.append(f"\n## 截止时间\n{timestamp}")

    # 负责人
    creator = task.get("creator")
    if isinstance(creator, dict):
        creator_id = creator.get("id")
        if creator_id:
            parts.append(f"\n## 创建者\n{creator_id}")

    return "\n".join(parts)


def _extract_meeting_text(minute: dict[str, Any]) -> str:
    """从会议数据中提取文本。"""
    parts = []

    # 会议标题
    title = minute.get("title")
    if title:
        parts.append(f"# {title}")

    # AI 总结
    summary = minute.get("summary")
    if summary:
        parts.append(f"\n## AI 总结\n{summary}")

    # 待办事项
    todos = minute.get("todos")
    if isinstance(todos, list) and todos:
        parts.append("\n## 待办事项")
        for todo in todos:
            if isinstance(todo, dict):
                todo_text = todo.get("text", "")
                parts.append(f"- {todo_text}")

    # 章节
    chapters = minute.get("chapters")
    if isinstance(chapters, list) and chapters:
        parts.append("\n## 章节")
        for chapter in chapters:
            if isinstance(chapter, dict):
                chapter_title = chapter.get("title", "")
                parts.append(f"- {chapter_title}")

    # 如果没有 AI 产物，尝试使用逐字稿
    if not summary and not todos:
        transcript = minute.get("transcript")
        if isinstance(transcript, list) and transcript:
            parts.append("\n## 逐字稿（前 10 段）")
            for i, segment in enumerate(transcript[:10]):
                if isinstance(segment, dict):
                    speaker = segment.get("speaker", "")
                    text = segment.get("text", "")
                    parts.append(f"**{speaker}**: {text}")

    return "\n".join(parts)


def _extract_bitable_record_text(record: dict[str, Any]) -> str:
    """从 Bitable 记录中提取文本。"""
    parts = []

    # 遍历所有字段
    fields = record.get("fields", record)
    if isinstance(fields, dict):
        for field_name, field_value in fields.items():
            # 跳过系统字段
            if field_name in {"created_by", "created_at", "updated_by", "updated_at", "record_id"}:
                continue

            # 提取文本值
            text_value = _extract_field_value(field_value)
            if text_value:
                parts.append(f"**{field_name}**: {text_value}")

    return "\n".join(parts)


def _extract_field_value(value: Any) -> str:
    """从字段值中提取文本。"""
    if value is None:
        return ""

    if isinstance(value, str):
        return value

    if isinstance(value, (int, float)):
        return str(value)

    if isinstance(value, bool):
        return "是" if value else "否"

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
                    texts.append(json.dumps(item, ensure_ascii=False))
            else:
                texts.append(str(item))
        return ", ".join(texts)

    if isinstance(value, dict):
        # 处理单选、URL 等对象字段
        text = value.get("text") or value.get("name") or value.get("link")
        if text:
            return str(text)
        return json.dumps(value, ensure_ascii=False)

    return str(value)
