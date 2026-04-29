# Feishu Group Graph Node Handoff

日期：2026-04-29
阶段：后期打磨 P1：Feishu 群/用户/消息作为企业图谱拓扑

## 本轮完成了什么

本轮修复“机器人被拉到新群后 Memory Copilot 没有任何记录”的设计缺口，并补齐底层存储模型：

- 新增 `knowledge_graph_nodes` / `knowledge_graph_edges` 本地 SQLite 表，`SCHEMA_VERSION` 升为 `3`。
- 新增 `memory_engine/copilot/graph_context.py`，把同一 tenant/org 下的 Feishu 群登记为 `feishu_chat` 节点，并建立 `organization -> feishu_chat` 边。
- `memory_engine/copilot/feishu_live.py` 在 allowlist 判断前先登记群节点。
- 未在 `COPILOT_FEISHU_ALLOWED_CHAT_IDS` 的新群只登记最小群元数据，状态为 `discovered`；不会记录消息正文、不会写 `raw_events`、不会创建 candidate，也不会回复群消息。
- allowlist 通过的群节点状态为 `active`；消息内容仍只通过 `handle_tool_request()` / `CopilotService` 进入 candidate-only 路径。
- allowlist 通过且消息可处理后，会登记：
  - `feishu_user`：同一 tenant/org 下按 sender open_id/user_id 去重，跨群共用同一个用户节点。
  - `feishu_message`：按 message_id 记录消息事件节点，metadata 只存 chat/message/sender 类型和内容策略，不存正文。
  - `member_of_feishu_chat`：表达用户在某个群的上下文。
  - `sent_feishu_message`：表达用户发送了某条消息事件。
  - `contains_feishu_message`：表达群包含某条消息事件。

## 关键问题回答

1. 知识图谱放在 Cognee 里吗？

   当前不是。当前权威图谱账本在本项目 SQLite：`knowledge_graph_nodes` / `knowledge_graph_edges`。Cognee 是已选 memory / knowledge engine 方向，但当前只作为 confirmed curated memory 的同步与召回通道，必须通过 `memory_engine/copilot/cognee_adapter.py` 窄 adapter 接入。Cognee 返回的内容仍要匹配本地 ledger 后才能进入正式答案。

2. 群聊里的对话怎么存？

   分层存：
   - 未授权群：只存 organization + `feishu_chat` 发现节点；不存用户节点、不存消息节点、不存正文、不创建 candidate。
   - 授权群：每条可处理消息会有 `feishu_message` 事件节点和关系边；消息正文仍只在 allowlist、permission、candidate gate 通过后写入 `raw_events.content`，并作为 candidate/evidence 的来源。
   - 不是每条消息都会成为 memory。只有被识别为长期有效信息的内容才进入 candidate；只有 reviewer 确认后才成为 active memory。

3. 用户在不同群聊中怎么存？

   同一 tenant/org 下，同一个 Feishu actor ID 只存一个 `feishu_user` 节点。群聊差异不复制用户节点，而是通过多条 `member_of_feishu_chat` 边表达“这个用户在哪些群出现过”，通过 `sent_feishu_message` / `contains_feishu_message` 表达消息事件上下文。

## 边界

- 这不是全量 Feishu workspace ingestion。
- 这不是生产级长期图谱服务。
- 群节点发现只保存必要上下文元数据；真实消息正文仍受 allowlist、permission 和 candidate-only gate 控制。
- 消息正文不写入图谱节点 metadata，也不会被默认整体向量化到 Cognee。
- 真实飞书来源仍不能自动 active，确认/拒绝仍必须走 reviewer 和 CopilotService。

## 关键文件

| 文件 | 说明 |
|---|---|
| `memory_engine/db.py` | 新增图谱节点/边表和索引，schema version 升为 3。 |
| `memory_engine/storage_migration.py` | dry-run / apply 检查纳入图谱表和索引。 |
| `memory_engine/copilot/graph_context.py` | Feishu 群、用户、消息节点和关系边的窄写入模块。 |
| `memory_engine/copilot/feishu_live.py` | allowlist 判断前登记群节点；授权可处理消息登记 user/message 拓扑；后续消息处理仍走 CopilotService。 |
| `tests/test_copilot_feishu_live.py` | 覆盖未授权新群只发现 org/chat 节点、授权新群 candidate 关联群节点、授权消息登记 user/message 边、同一用户跨群只保留一个用户节点。 |

## 验证

已新增目标测试：

```bash
python3 -m unittest tests.test_copilot_feishu_live.CopilotFeishuLiveTest.test_new_disallowed_group_is_discovered_as_graph_node_without_ingesting_content tests.test_copilot_feishu_live.CopilotFeishuLiveTest.test_allowed_group_candidate_links_to_discovered_chat_graph_node
python3 -m unittest tests.test_copilot_feishu_live.CopilotFeishuLiveTest.test_disallowed_group_does_not_create_user_or_message_graph_nodes tests.test_copilot_feishu_live.CopilotFeishuLiveTest.test_allowed_group_records_user_message_and_relationship_edges tests.test_copilot_feishu_live.CopilotFeishuLiveTest.test_same_user_across_groups_is_one_node_with_group_specific_membership_edges
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
