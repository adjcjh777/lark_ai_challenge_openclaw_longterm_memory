"""飞书 fetcher 模块单元测试。

测试 feishu_task_fetcher、feishu_meeting_fetcher、feishu_bitable_fetcher
的 API 调用、结果解析和错误处理。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from memory_engine.db import connect, init_db
from memory_engine.document_ingestion import ingest_feishu_source
from memory_engine.feishu_api_client import FeishuApiResult
from memory_engine.feishu_bitable_fetcher import (
    fetch_bitable_record_text,
    list_bitable_records,
    list_bitable_tables,
)
from memory_engine.feishu_meeting_fetcher import (
    fetch_feishu_meeting_text,
    list_feishu_meetings,
)
from memory_engine.feishu_task_fetcher import (
    fetch_feishu_task_text,
    list_feishu_tasks,
)
from memory_engine.repository import MemoryRepository

SCOPE = "project:feishu_ai_challenge"


def _ok_result(data: dict) -> FeishuApiResult:
    return FeishuApiResult(ok=True, data=data, returncode=0)


def _error_result(error_code: str, message: str) -> FeishuApiResult:
    return FeishuApiResult(ok=False, error_code=error_code, error_message=message, returncode=1)


def _permission_context(**source_context_extra: str) -> dict[str, object]:
    source_context = {
        "entrypoint": "feishu_test_group",
        "workspace_id": SCOPE,
        "chat_id": "chat_test",
    }
    source_context.update(source_context_extra)
    return {
        "scope": SCOPE,
        "permission": {
            "request_id": "req_fetcher_test",
            "trace_id": "trace_fetcher_test",
            "actor": {
                "open_id": "ou_fetcher_tester",
                "tenant_id": "tenant:demo",
                "organization_id": "org:demo",
                "roles": ["member", "reviewer"],
            },
            "source_context": source_context,
            "requested_action": "memory.create_candidate",
            "requested_visibility": "team",
            "timestamp": "2026-04-28T00:00:00+08:00",
        },
    }


# ---------------------------------------------------------------------------
# Task Fetcher Tests
# ---------------------------------------------------------------------------


class TaskFetcherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "memory.sqlite"
        self.conn = connect(self.db_path)
        init_db(self.conn)
        self.repo = MemoryRepository(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    @patch("memory_engine.feishu_task_fetcher.run_lark_cli")
    def test_fetch_feishu_task_text_success(self, mock_run: Mock) -> None:
        mock_run.return_value = _ok_result(
            {
                "data": {
                    "task": {
                        "title": "生产部署任务",
                        "summary": "生产部署必须加 --canary --region cn-shanghai",
                        "creator": {"id": "ou_creator_1"},
                        "due": {"timestamp": "1714500000"},
                        "status": "open",
                        "subtasks": [
                            {"title": "配置灰度", "status": "completed"},
                            {"title": "监控告警", "status": "pending"},
                        ],
                    },
                },
            }
        )

        source = fetch_feishu_task_text("task_123")

        self.assertEqual(source.source_type, "feishu_task")
        self.assertEqual(source.source_id, "task_123")
        self.assertEqual(source.title, "生产部署任务")
        self.assertIn("生产部署必须加 --canary", source.text)
        self.assertIn("配置灰度", source.text)
        self.assertIn("监控告警", source.text)
        self.assertEqual(source.actor_id, "ou_creator_1")
        self.assertEqual(source.metadata["task_status"], "open")
        self.assertEqual(source.metadata["due_at"], "1714500000")
        self.assertEqual(
            [
                "--as",
                "user",
                "task",
                "tasks",
                "get",
                "--params",
                '{"task_guid": "task_123", "user_id_type": "open_id"}',
            ],
            mock_run.call_args.args[0],
        )

    @patch("memory_engine.feishu_task_fetcher.run_lark_cli")
    def test_fetch_feishu_task_text_supports_task_v2_shape(self, mock_run: Mock) -> None:
        mock_run.return_value = _ok_result(
            {
                "data": {
                    "task": {
                        "summary": "Task v2 标题",
                        "description": "Task v2 描述里记录上线前必须检查审计。",
                        "creator": {"id": "ou_creator_2"},
                        "status": "todo",
                        "url": "https://applink.feishu.cn/client/todo/detail?guid=task_v2",
                    },
                },
            }
        )

        source = fetch_feishu_task_text("task_v2")

        self.assertEqual("Task v2 标题", source.title)
        self.assertIn("Task v2 描述", source.text)
        self.assertEqual("https://applink.feishu.cn/client/todo/detail?guid=task_v2", source.source_url)

    @patch("memory_engine.feishu_task_fetcher.run_lark_cli")
    def test_fetch_feishu_task_text_api_error(self, mock_run: Mock) -> None:
        mock_run.return_value = _error_result("permission_denied", "权限不足")

        with self.assertRaises(ValueError) as ctx:
            fetch_feishu_task_text("task_bad")
        self.assertIn("权限不足", str(ctx.exception))

    @patch("memory_engine.feishu_task_fetcher.run_lark_cli")
    def test_fetch_feishu_task_text_empty_task(self, mock_run: Mock) -> None:
        mock_run.return_value = _ok_result({"data": {"task": None}})

        with self.assertRaises(ValueError) as ctx:
            fetch_feishu_task_text("task_empty")
        self.assertIn("任务数据为空", str(ctx.exception))

    @patch("memory_engine.feishu_task_fetcher.run_lark_cli")
    def test_list_feishu_tasks_success(self, mock_run: Mock) -> None:
        mock_run.return_value = _ok_result(
            {
                "data": {
                    "items": [
                        {"task_id": "t1", "title": "任务一", "status": "open", "creator": {"id": "ou1"}, "due": {}},
                        {
                            "task_id": "t2",
                            "title": "任务二",
                            "status": "done",
                            "creator": {"id": "ou2"},
                            "due": {"timestamp": "1714600000"},
                        },
                    ],
                },
            }
        )

        tasks = list_feishu_tasks(page_size=10)

        self.assertEqual(2, len(tasks))
        self.assertEqual("t1", tasks[0]["task_id"])
        self.assertEqual("任务一", tasks[0]["title"])
        self.assertEqual("t2", tasks[1]["task_id"])

    @patch("memory_engine.feishu_task_fetcher.run_lark_cli")
    def test_list_feishu_tasks_api_error(self, mock_run: Mock) -> None:
        mock_run.return_value = _error_result("api_error", "网络超时")

        with self.assertRaises(ValueError):
            list_feishu_tasks()

    @patch("memory_engine.feishu_task_fetcher.run_lark_cli")
    def test_fetch_feishu_task_text_ingests_candidate(self, mock_run: Mock) -> None:
        """验证 fetch_feishu_task_text 返回的 source 可正确进入 candidate pipeline。"""
        mock_run.return_value = _ok_result(
            {
                "data": {
                    "task": {
                        "title": "上线任务",
                        "summary": "决定：上线负责人是程俊豪，截止 2026-04-30。",
                        "creator": {"id": "ou_owner"},
                        "status": "open",
                    },
                },
            }
        )

        source = fetch_feishu_task_text("task_ingest")
        result = ingest_feishu_source(
            self.repo,
            source,
            current_context=_permission_context(task_id="task_ingest"),
            limit=3,
        )

        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["candidate_count"], 1)
        self.assertEqual(
            0, self.conn.execute("SELECT COUNT(*) AS count FROM memories WHERE status = 'active'").fetchone()["count"]
        )
        candidate = result["candidates"][0]
        self.assertEqual("feishu_task", candidate["evidence"]["source_type"])
        self.assertEqual("task_ingest", candidate["evidence"]["source_task_id"])

    @patch("memory_engine.feishu_task_fetcher.run_lark_cli")
    def test_task_with_no_subtasks(self, mock_run: Mock) -> None:
        """无子任务时不应生成子任务文本段。"""
        mock_run.return_value = _ok_result(
            {
                "data": {
                    "task": {
                        "title": "简单任务",
                        "summary": "只做一件事。",
                        "creator": {"id": "ou1"},
                    },
                },
            }
        )

        source = fetch_feishu_task_text("task_no_sub")
        self.assertNotIn("子任务", source.text)
        self.assertIn("简单任务", source.text)


# ---------------------------------------------------------------------------
# Meeting Fetcher Tests
# ---------------------------------------------------------------------------


class MeetingFetcherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "memory.sqlite"
        self.conn = connect(self.db_path)
        init_db(self.conn)
        self.repo = MemoryRepository(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    @patch("memory_engine.feishu_meeting_fetcher.run_lark_cli")
    def test_fetch_meeting_with_ai_content(self, mock_run: Mock) -> None:
        def side_effect(argv, **kwargs):
            # 注意：必须先检查更具体的模式，因为 "+get" 是 "+get-ai-content" 的子串
            if any("get-ai-content" in arg for arg in argv):
                return _ok_result(
                    {
                        "data": {
                            "ai_content": {
                                "summary": "会议决定：生产部署 region 统一用 ap-shanghai。",
                                "todos": [
                                    {"text": "更新部署文档"},
                                    {"text": "通知运维团队"},
                                ],
                                "chapters": [
                                    {"title": "部署方案讨论"},
                                    {"title": "遗留问题"},
                                ],
                            },
                        },
                    }
                )
            if any("get-transcript" in arg for arg in argv):
                return _ok_result({"data": {"transcript": []}})
            # minute detail
            return _ok_result(
                {
                    "data": {
                        "minute": {
                            "title": "发布复盘会",
                            "creator": {"id": "ou_host"},
                            "duration": 3600,
                            "participant_count": 8,
                            "meeting_date": "2026-04-28",
                            "status": "ended",
                        },
                    },
                }
            )

        mock_run.side_effect = side_effect

        source = fetch_feishu_meeting_text("minute_abc")

        self.assertEqual(source.source_type, "feishu_meeting")
        self.assertEqual(source.source_id, "minute_abc")
        self.assertEqual(source.title, "发布复盘会")
        self.assertIn("ap-shanghai", source.text)
        self.assertIn("更新部署文档", source.text)
        self.assertIn("部署方案讨论", source.text)
        self.assertTrue(source.metadata["has_ai_content"])

    @patch("memory_engine.feishu_meeting_fetcher.run_lark_cli")
    def test_fetch_meeting_fallback_to_transcript(self, mock_run: Mock) -> None:
        """AI 产物为空时降级使用逐字稿。"""

        def side_effect(argv, **kwargs):
            if any("get-ai-content" in arg for arg in argv):
                return _ok_result({"data": {"ai_content": {}}})
            if any("get-transcript" in arg for arg in argv):
                return _ok_result(
                    {
                        "data": {
                            "transcript": [
                                {"speaker": "Alice", "text": "今天讨论部署 region 问题。"},
                                {"speaker": "Bob", "text": "决定用 ap-shanghai。"},
                            ],
                        },
                    }
                )
            return _ok_result(
                {
                    "data": {
                        "minute": {
                            "title": "技术讨论",
                            "creator": {"id": "ou_host"},
                            "duration": 1800,
                            "participant_count": 3,
                            "meeting_date": "2026-04-28",
                            "status": "ended",
                        },
                    },
                }
            )

        mock_run.side_effect = side_effect

        source = fetch_feishu_meeting_text("minute_transcript")

        self.assertIn("Alice", source.text)
        self.assertIn("ap-shanghai", source.text)
        self.assertFalse(source.metadata["has_ai_content"])

    @patch("memory_engine.feishu_meeting_fetcher.run_lark_cli")
    def test_fetch_meeting_in_progress_raises(self, mock_run: Mock) -> None:
        mock_run.return_value = _ok_result(
            {
                "data": {
                    "minute": {
                        "title": "进行中会议",
                        "creator": {"id": "ou_host"},
                        "status": "in_progress",
                    },
                },
            }
        )

        with self.assertRaises(ValueError) as ctx:
            fetch_feishu_meeting_text("minute_live")
        self.assertIn("尚未结束", str(ctx.exception))

    @patch("memory_engine.feishu_meeting_fetcher.run_lark_cli")
    def test_fetch_meeting_api_error(self, mock_run: Mock) -> None:
        mock_run.return_value = _error_result("permission_denied", "无权限")

        with self.assertRaises(ValueError) as ctx:
            fetch_feishu_meeting_text("minute_bad")
        self.assertIn("无权限", str(ctx.exception))

    @patch("memory_engine.feishu_meeting_fetcher.run_lark_cli")
    def test_list_feishu_meetings_success(self, mock_run: Mock) -> None:
        mock_run.return_value = _ok_result(
            {
                "data": {
                    "items": [
                        {
                            "minute_token": "m1",
                            "title": "会议一",
                            "status": "ended",
                            "creator": {"id": "ou1"},
                            "duration": 3600,
                            "meeting_date": "2026-04-28",
                        },
                    ],
                },
            }
        )

        meetings = list_feishu_meetings(page_size=10)

        self.assertEqual(1, len(meetings))
        self.assertEqual("m1", meetings[0]["minute_token"])

    @patch("memory_engine.feishu_meeting_fetcher.run_lark_cli")
    def test_meeting_ingests_candidate(self, mock_run: Mock) -> None:
        """验证会议 fetcher 返回的 source 可进入 candidate pipeline。"""

        def side_effect(argv, **kwargs):
            if any("get-ai-content" in arg for arg in argv):
                return _ok_result(
                    {
                        "data": {
                            "ai_content": {
                                "summary": "风险：灰度期间不能关闭审计日志。",
                                "todos": [{"text": "确认审计配置"}],
                            },
                        },
                    }
                )
            if any("get-transcript" in arg for arg in argv):
                return _ok_result({"data": {"transcript": []}})
            return _ok_result(
                {
                    "data": {
                        "minute": {
                            "title": "安全复盘会",
                            "creator": {"id": "ou_host"},
                            "status": "ended",
                        },
                    },
                }
            )

        mock_run.side_effect = side_effect

        source = fetch_feishu_meeting_text("minute_ingest")
        result = ingest_feishu_source(
            self.repo,
            source,
            current_context=_permission_context(meeting_id="minute_ingest"),
            limit=3,
        )

        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["candidate_count"], 1)
        candidate = result["candidates"][0]
        self.assertEqual("feishu_meeting", candidate["evidence"]["source_type"])


# ---------------------------------------------------------------------------
# Bitable Fetcher Tests
# ---------------------------------------------------------------------------


class BitableFetcherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "memory.sqlite"
        self.conn = connect(self.db_path)
        init_db(self.conn)
        self.repo = MemoryRepository(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.temp_dir.cleanup()

    @patch("memory_engine.feishu_bitable_fetcher.run_lark_cli")
    def test_fetch_bitable_record_text_success(self, mock_run: Mock) -> None:
        mock_run.return_value = _ok_result(
            {
                "data": {
                    "record": {
                        "record_id": "rec_001",
                        "fields": {
                            "项目名称": "生产部署",
                            "负责人": "程俊豪",
                            "截止日期": "2026-04-30",
                            "优先级": "P1",
                            "created_at": "2026-04-28",
                        },
                    },
                },
            }
        )

        source = fetch_bitable_record_text("app_token", "tbl_1", "rec_001")

        self.assertEqual(source.source_type, "lark_bitable")
        self.assertEqual(source.source_id, "rec_001")
        self.assertIn("生产部署", source.text)
        self.assertIn("程俊豪", source.text)
        self.assertIn("P1", source.text)
        self.assertEqual(source.metadata["app_token"], "app_token")
        self.assertEqual(source.metadata["table_id"], "tbl_1")
        self.assertEqual(source.metadata["record_id"], "rec_001")

    @patch("memory_engine.feishu_bitable_fetcher.run_lark_cli")
    def test_fetch_bitable_record_api_error(self, mock_run: Mock) -> None:
        mock_run.return_value = _error_result("resource_not_found", "记录不存在")

        with self.assertRaises(ValueError) as ctx:
            fetch_bitable_record_text("app", "tbl", "rec_bad")
        self.assertIn("记录不存在", str(ctx.exception))

    @patch("memory_engine.feishu_bitable_fetcher.run_lark_cli")
    def test_fetch_bitable_record_empty_fields(self, mock_run: Mock) -> None:
        mock_run.return_value = _ok_result(
            {
                "data": {
                    "record": {
                        "record_id": "rec_empty",
                        "fields": {},
                    },
                },
            }
        )

        with self.assertRaises(ValueError) as ctx:
            fetch_bitable_record_text("app", "tbl", "rec_empty")
        self.assertIn("字段为空", str(ctx.exception))

    @patch("memory_engine.feishu_bitable_fetcher.run_lark_cli")
    def test_list_bitable_records_success(self, mock_run: Mock) -> None:
        mock_run.return_value = _ok_result(
            {
                "data": {
                    "items": [
                        {
                            "record_id": "rec_1",
                            "fields": {"名称": "记录一", "状态": "进行中"},
                        },
                        {
                            "record_id": "rec_2",
                            "fields": {"名称": "记录二", "状态": "已完成"},
                        },
                    ],
                },
            }
        )

        records = list_bitable_records("app", "tbl", limit=10)

        self.assertEqual(2, len(records))
        self.assertEqual("rec_1", records[0]["record_id"])
        self.assertIn("记录一", records[0]["summary"])

    @patch("memory_engine.feishu_bitable_fetcher.run_lark_cli")
    def test_list_bitable_tables_success(self, mock_run: Mock) -> None:
        mock_run.return_value = _ok_result(
            {
                "data": {
                    "items": [
                        {"table_id": "tbl_a", "name": "任务表", "revision": 3},
                        {"table_id": "tbl_b", "name": "人员表", "revision": 1},
                    ],
                },
            }
        )

        tables = list_bitable_tables("app_token")

        self.assertEqual(2, len(tables))
        self.assertEqual("tbl_a", tables[0]["table_id"])
        self.assertEqual("任务表", tables[0]["name"])

    @patch("memory_engine.feishu_bitable_fetcher.run_lark_cli")
    def test_bitable_ingests_candidate(self, mock_run: Mock) -> None:
        """验证 bitable fetcher 返回的 source 可进入 candidate pipeline。"""
        mock_run.return_value = _ok_result(
            {
                "data": {
                    "record": {
                        "record_id": "rec_ingest",
                        "fields": {
                            "规则": "生产部署 region 使用 ap-shanghai。",
                            "负责人": "程俊豪",
                        },
                    },
                },
            }
        )

        source = fetch_bitable_record_text("app", "tbl", "rec_ingest")
        result = ingest_feishu_source(
            self.repo,
            source,
            current_context=_permission_context(bitable_record_id="rec_ingest"),
            limit=3,
        )

        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["candidate_count"], 1)
        candidate = result["candidates"][0]
        self.assertEqual("lark_bitable", candidate["evidence"]["source_type"])

    @patch("memory_engine.feishu_bitable_fetcher.run_lark_cli")
    def test_bitable_field_value_extraction(self, mock_run: Mock) -> None:
        """验证各种字段值类型都能正确提取。"""
        mock_run.return_value = _ok_result(
            {
                "data": {
                    "record": {
                        "record_id": "rec_types",
                        "fields": {
                            "文本字段": "hello",
                            "数字字段": 42,
                            "布尔字段": True,
                            "数组字段": ["选项A", "选项B"],
                            "人员字段": [{"name": "张三"}, {"en_name": "Alice"}],
                            "URL字段": {"text": "https://example.com", "link": "https://example.com"},
                            "空值字段": None,
                        },
                    },
                },
            }
        )

        source = fetch_bitable_record_text("app", "tbl", "rec_types")

        self.assertIn("hello", source.text)
        self.assertIn("42", source.text)
        self.assertIn("是", source.text)  # True -> "是"
        self.assertIn("选项A", source.text)
        self.assertIn("张三", source.text)
        self.assertIn("https://example.com", source.text)


# ---------------------------------------------------------------------------
# Fallback Tests
# ---------------------------------------------------------------------------


class ApiFallbackTest(unittest.TestCase):
    """验证 API 失败时的统一 fallback 行为。"""

    @patch("memory_engine.feishu_task_fetcher.run_lark_cli")
    def test_task_fetcher_returns_empty_on_network_error(self, mock_run: Mock) -> None:
        mock_run.return_value = _error_result("api_error", "网络超时")

        with self.assertRaises(ValueError):
            fetch_feishu_task_text("task_network_error")

    @patch("memory_engine.feishu_meeting_fetcher.run_lark_cli")
    def test_meeting_fetcher_returns_empty_on_network_error(self, mock_run: Mock) -> None:
        mock_run.return_value = _error_result("api_error", "网络超时")

        with self.assertRaises(ValueError):
            fetch_feishu_meeting_text("minute_network_error")

    @patch("memory_engine.feishu_bitable_fetcher.run_lark_cli")
    def test_bitable_fetcher_returns_empty_on_network_error(self, mock_run: Mock) -> None:
        mock_run.return_value = _error_result("api_error", "网络超时")

        with self.assertRaises(ValueError):
            fetch_bitable_record_text("app", "tbl", "rec_network_error")


if __name__ == "__main__":
    unittest.main()
