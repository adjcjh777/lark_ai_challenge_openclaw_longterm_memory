# Feishu Group Graph Node Handoff

日期：2026-04-29
阶段：后期打磨 P1：Feishu 群作为企业图谱节点

## 本轮完成了什么

本轮修复“机器人被拉到新群后 Memory Copilot 没有任何记录”的设计缺口：

- 新增 `knowledge_graph_nodes` / `knowledge_graph_edges` 本地 SQLite 表，`SCHEMA_VERSION` 升为 `3`。
- 新增 `memory_engine/copilot/graph_context.py`，把同一 tenant/org 下的 Feishu 群登记为 `feishu_chat` 节点，并建立 `organization -> feishu_chat` 边。
- `memory_engine/copilot/feishu_live.py` 在 allowlist 判断前先登记群节点。
- 未在 `COPILOT_FEISHU_ALLOWED_CHAT_IDS` 的新群只登记最小群元数据，状态为 `discovered`；不会记录消息正文、不会写 `raw_events`、不会创建 candidate，也不会回复群消息。
- allowlist 通过的群节点状态为 `active`；消息内容仍只通过 `handle_tool_request()` / `CopilotService` 进入 candidate-only 路径。

## 边界

- 这不是全量 Feishu workspace ingestion。
- 这不是生产级长期图谱服务。
- 群节点发现只保存必要上下文元数据；真实消息正文仍受 allowlist、permission 和 candidate-only gate 控制。
- 真实飞书来源仍不能自动 active，确认/拒绝仍必须走 reviewer 和 CopilotService。

## 关键文件

| 文件 | 说明 |
|---|---|
| `memory_engine/db.py` | 新增图谱节点/边表和索引，schema version 升为 3。 |
| `memory_engine/storage_migration.py` | dry-run / apply 检查纳入图谱表和索引。 |
| `memory_engine/copilot/graph_context.py` | Feishu 群节点和 organization 边的窄写入模块。 |
| `memory_engine/copilot/feishu_live.py` | allowlist 判断前登记群节点；后续消息处理仍走 CopilotService。 |
| `tests/test_copilot_feishu_live.py` | 覆盖未授权新群只发现节点、授权新群 candidate 关联群节点。 |

## 验证

已新增目标测试：

```bash
python3 -m unittest tests.test_copilot_feishu_live.CopilotFeishuLiveTest.test_new_disallowed_group_is_discovered_as_graph_node_without_ingesting_content tests.test_copilot_feishu_live.CopilotFeishuLiveTest.test_allowed_group_candidate_links_to_discovered_chat_graph_node
```

当前目标测试通过。完整验证见本轮最终执行记录。

## 飞书看板同步

已同步飞书共享任务看板，并读回确认：

- 任务描述：`2026-04-29 程俊豪：Feishu 群企业图谱节点发现`
- 状态：`已完成`
- 优先级：`P1`
- 指派给：`程俊豪`
- 任务截止日期：`2026-04-29`
- 记录 ID：`recviaEcAACgnd`
