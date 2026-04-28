"""飞书会议/妙记 API 拉取模块。

从飞书妙记 API 拉取会议纪要，提取文本进入 candidate pipeline。
"""

from __future__ import annotations

from typing import Any

from .document_ingestion import FeishuIngestionSource
from .feishu_api_client import FeishuApiResult, run_lark_cli


def fetch_feishu_meeting_text(
    minute_token: str,
    *,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> FeishuIngestionSource:
    """从飞书妙记 API 拉取会议纪要，构造 FeishuIngestionSource。

    Args:
        minute_token: 飞书妙记 token
        lark_cli: lark-cli 命令路径（默认 "lark-cli"）
        profile: lark-cli profile 名称
        as_identity: 身份切换（user/bot）

    Returns:
        FeishuIngestionSource: 包含会议纪要文本和元数据的源对象

    Raises:
        ValueError: 当妙记不存在、权限不足或未结束时
    """
    # 先获取妙记基本信息
    detail_result = _fetch_minute_detail(minute_token, lark_cli=lark_cli, profile=profile, as_identity=as_identity)

    if not detail_result.ok:
        raise ValueError(f"获取妙记详情失败: {detail_result.error_message} (error_code={detail_result.error_code})")

    detail_data = detail_result.data
    if not detail_data or "data" not in detail_data:
        raise ValueError("获取妙记详情失败: 返回数据为空")

    minute_data = detail_data["data"]
    minute = minute_data.get("minute")
    if not minute:
        raise ValueError("获取妙记详情失败: 妙记数据为空")

    # 提取基本信息
    title = minute.get("title", f"会议 {minute_token}")
    creator = minute.get("creator", {})
    creator_id = creator.get("id", "unknown")
    duration = minute.get("duration", 0)
    participant_count = minute.get("participant_count", 0)
    meeting_date = minute.get("meeting_date", "")
    status = minute.get("status", "")

    # 检查妙记状态
    if status == "in_progress":
        raise ValueError("妙记尚未结束，无法拉取")

    # 获取 AI 产物
    ai_content_result = _fetch_minute_ai_content(
        minute_token, lark_cli=lark_cli, profile=profile, as_identity=as_identity
    )

    text_parts = []
    has_ai_content = False

    if ai_content_result.ok and ai_content_result.data:
        ai_data = ai_content_result.data.get("data", {})
        ai_content = ai_data.get("ai_content", {})

        # AI 总结
        summary = ai_content.get("summary")
        if summary:
            has_ai_content = True
            text_parts.append(f"# {title}\n\n## AI 总结\n{summary}")

        # 待办事项
        todos = ai_content.get("todos")
        if isinstance(todos, list) and todos:
            has_ai_content = True
            todo_lines = []
            for todo in todos:
                if isinstance(todo, dict):
                    todo_text = todo.get("text", "")
                    if todo_text:
                        todo_lines.append(f"- {todo_text}")
            if todo_lines:
                text_parts.append("\n## 待办事项\n" + "\n".join(todo_lines))

        # 章节
        chapters = ai_content.get("chapters")
        if isinstance(chapters, list) and chapters:
            has_ai_content = True
            chapter_lines = []
            for chapter in chapters:
                if isinstance(chapter, dict):
                    chapter_title = chapter.get("title", "")
                    if chapter_title:
                        chapter_lines.append(f"- {chapter_title}")
            if chapter_lines:
                text_parts.append("\n## 章节\n" + "\n".join(chapter_lines))

    # 如果没有 AI 产物，降级使用逐字稿
    if not has_ai_content:
        transcript_result = _fetch_minute_transcript(
            minute_token, lark_cli=lark_cli, profile=profile, as_identity=as_identity
        )

        if transcript_result.ok and transcript_result.data:
            transcript_data = transcript_result.data.get("data", {})
            transcript = transcript_data.get("transcript", [])

            if isinstance(transcript, list) and transcript:
                text_parts.append(f"# {title}\n\n## 逐字稿（前 10 段）")
                for i, segment in enumerate(transcript[:10]):
                    if isinstance(segment, dict):
                        speaker = segment.get("speaker", "")
                        segment_text = segment.get("text", "")
                        if segment_text:
                            text_parts.append(f"**{speaker}**: {segment_text}")

    combined_text = "\n".join(text_parts)
    if not combined_text.strip():
        raise ValueError("获取妙记失败: 无法提取有效内容")

    # 构造 source metadata
    metadata: dict[str, Any] = {
        "duration_seconds": duration,
        "participant_count": participant_count,
        "meeting_date": meeting_date,
        "has_ai_content": has_ai_content,
    }

    return FeishuIngestionSource(
        source_type="feishu_meeting",
        source_id=minute_token,
        title=title,
        text=combined_text,
        actor_id=creator_id,
        source_url=f"https://feishu.cn/minutes/{minute_token}",
        metadata=metadata,
    )


def list_feishu_meetings(
    *,
    start_time: str | None = None,
    end_time: str | None = None,
    page_size: int = 50,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> list[dict[str, Any]]:
    """列出妙记列表，用于批量拉取。

    Args:
        start_time: 开始时间（Unix 时间戳字符串）
        end_time: 结束时间（Unix 时间戳字符串）
        page_size: 每页数量（默认 50）
        lark_cli: lark-cli 命令路径
        profile: lark-cli profile 名称
        as_identity: 身份切换

    Returns:
        list[dict[str, Any]]: 妙记列表，每个妙记包含 minute_token、title 等基本信息

    Raises:
        ValueError: 当 API 调用失败时
    """
    result = _list_minutes(
        start_time=start_time,
        end_time=end_time,
        page_size=page_size,
        lark_cli=lark_cli,
        profile=profile,
        as_identity=as_identity,
    )

    if not result.ok:
        raise ValueError(f"获取妙记列表失败: {result.error_message} (error_code={result.error_code})")

    data = result.data
    if not data or "data" not in data:
        return []

    items = data["data"].get("items", [])
    meetings = []

    for item in items:
        minute_token = item.get("minute_token", "")
        title = item.get("title", "")
        status = item.get("status", "")
        creator = item.get("creator", {})
        creator_id = creator.get("id", "")
        duration = item.get("duration", 0)
        meeting_date = item.get("meeting_date", "")

        meetings.append(
            {
                "minute_token": minute_token,
                "title": title,
                "status": status,
                "creator_id": creator_id,
                "duration": duration,
                "meeting_date": meeting_date,
            }
        )

    return meetings


def _fetch_minute_detail(
    minute_token: str,
    *,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> FeishuApiResult:
    """获取妙记详情。"""
    argv = _build_argv(["minutes", "+get", "--minute-token", minute_token], profile=profile, as_identity=as_identity)
    return run_lark_cli(argv)


def _fetch_minute_ai_content(
    minute_token: str,
    *,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> FeishuApiResult:
    """获取妙记 AI 产物。"""
    argv = _build_argv(
        ["minutes", "+get-ai-content", "--minute-token", minute_token],
        profile=profile,
        as_identity=as_identity,
    )
    return run_lark_cli(argv)


def _fetch_minute_transcript(
    minute_token: str,
    *,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> FeishuApiResult:
    """获取妙记逐字稿。"""
    argv = _build_argv(
        ["minutes", "+get-transcript", "--minute-token", minute_token],
        profile=profile,
        as_identity=as_identity,
    )
    return run_lark_cli(argv)


def _list_minutes(
    *,
    start_time: str | None = None,
    end_time: str | None = None,
    page_size: int = 50,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> FeishuApiResult:
    """获取妙记列表。"""
    command = ["minutes", "+list", "--page-size", str(page_size)]
    if start_time:
        command.extend(["--start-time", start_time])
    if end_time:
        command.extend(["--end-time", end_time])

    argv = _build_argv(command, profile=profile, as_identity=as_identity)
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
