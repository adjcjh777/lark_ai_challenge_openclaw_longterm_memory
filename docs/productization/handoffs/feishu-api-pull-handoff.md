# Feishu API Pull Handoff

日期：2026-04-29
阶段：Task 3：真实 Feishu API 拉取扩样 candidate-only 路径

## 本轮完成了什么

本轮确认仓库已经存在任务、会议、Bitable 读取 fetcher，并补齐真实拉取前的权限门控和飞书 live payload 对齐：

- `memory_engine/feishu_task_fetcher.py` 可通过 `lark-cli task +get-task` / `+get-my-tasks` 拉取任务详情和列表，构造 `FeishuIngestionSource(source_type="feishu_task")`。
- `memory_engine/feishu_meeting_fetcher.py` 可通过 `lark-cli minutes +get` / `+get-ai-content` / `+get-transcript` 拉取妙记详情、AI 产物或逐字稿，构造 `FeishuIngestionSource(source_type="feishu_meeting")`。
- `memory_engine/feishu_bitable_fetcher.py` 可通过 `lark-cli base +record-get` / `+record-list` / `+table-list` 拉取 Bitable 记录和表结构，构造 `FeishuIngestionSource(source_type="lark_bitable")`。
- 新增 `preflight_feishu_source_access()`，在任何真实 task / meeting / Bitable fetch 前先检查 `current_context.permission`、scope、tenant / organization 和 source context。
- `handle_tool_request("feishu.fetch_*")` 现在会先 fail closed，再调用 fetcher；权限缺失、畸形或 source_context mismatch 时不会触发 lark-cli。
- Feishu live `/task`、`/meeting`、`/bitable` 会把 `task_id`、`meeting_id`、`bitable_record_id` 写入 `permission.source_context`，并把 `requested_action` 固定为 `memory.create_candidate`，保证最终仍进入 candidate-only pipeline。

## 仍然坚持的边界

- 真实飞书来源只进入 candidate，不自动 active。
- `feishu.fetch_*` 的目的不是绕过 Copilot Core；成功拉取后仍通过 `ingest_feishu_source()` -> `CopilotService.create_candidate()`。
- 权限缺失、畸形、scope mismatch、tenant / organization mismatch、source_context mismatch 必须在真实 API fetch 前 fail closed。
- API 失败只返回受控错误，不创建 candidate，不把 raw content、真实 ID、token 或 secret 写入仓库。
- 本轮不是全量 Feishu workspace ingestion，不是生产部署，不是 productized live 长期运行。
- 本轮没有把 `feishu.fetch_*` 暴露成 OpenClaw first-class schema 工具；当前 first-class OpenClaw memory 工具仍是 `fmc_memory_*` 和 `fmc_heartbeat_review_due`。

## 关键文件

| 文件 | 说明 |
|---|---|
| `memory_engine/document_ingestion.py` | 新增 fetch 前 preflight；继续承载 candidate-only ingestion。 |
| `memory_engine/copilot/tools.py` | `feishu.fetch_task` / `feishu.fetch_meeting` / `feishu.fetch_bitable` 先权限门控再拉取。 |
| `memory_engine/copilot/feishu_live.py` | `/task`、`/meeting`、`/bitable` payload 对齐 `permission.source_context`。 |
| `memory_engine/feishu_task_fetcher.py` | 飞书任务读取 fetcher。 |
| `memory_engine/feishu_meeting_fetcher.py` | 飞书妙记 / 会议读取 fetcher。 |
| `memory_engine/feishu_bitable_fetcher.py` | Bitable 记录读取 fetcher。 |
| `tests/test_copilot_tools.py` | 覆盖 fetch 前 fail-closed 且不调用 fetcher。 |
| `tests/test_copilot_feishu_live.py` | 覆盖 live 命令 payload 的 source context。 |
| `tests/test_feishu_fetchers.py` | 覆盖 task / meeting / Bitable fetcher 解析、错误和 candidate pipeline。 |

## 验证结果

已运行：

```bash
python3 -m unittest tests.test_copilot_tools tests.test_copilot_feishu_live tests.test_document_ingestion tests.test_feishu_fetchers -v
```

结果：

- 77 tests OK。
- 覆盖 task / meeting / Bitable candidate-only、fetch 前 fail-closed、live source_context 和 API fallback。

## 后续风险

- 还可以用受控真实资源 ID 做现场 smoke，但不能把 smoke 写成全量 workspace ingestion。
- 真实样本人工复核集仍可继续扩充；失败样例应保留用于能力改进，不应删除。
- 如果后续要把 `feishu.fetch_*` 暴露给 OpenClaw Agent first-class 工具，需要再改 `agent_adapters/openclaw/memory_tools.schema.json`、plugin 和 registry，并补 schema / registry 测试。
