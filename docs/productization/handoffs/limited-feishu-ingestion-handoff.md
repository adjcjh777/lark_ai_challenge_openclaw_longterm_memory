# Limited Feishu Ingestion Handoff

日期：2026-04-28
阶段：后期打磨 P1：扩大真实 Feishu ingestion 范围

## 本轮完成了什么

本轮补齐了 limited ingestion 的本地产品化底座：

- 新增 `FeishuIngestionSource`，支持把已授权上游拿到的飞书来源文本送入 candidate pipeline。
- 新增 `ingest_feishu_source()`，覆盖 `feishu_message`、`document_feishu` / `lark_doc`、`feishu_task`、`feishu_meeting`、`lark_bitable`。
- 每类来源都会保留 source metadata、evidence quote、request_id、trace_id 和 permission decision trace。
- 新增 `mark_feishu_source_revoked()`，source 删除或权限撤销后会把对应 active memory 标记为 `stale`，默认 recall 不再返回。
- 扩展 OpenClaw/Copilot candidate source schema，保留 task、meeting、Bitable 的稳定 metadata 字段。

## 仍然坚持的边界

- 真实飞书来源仍只进入 candidate，不自动 active。
- confirm / reject 仍必须经过 `CopilotService` / `handle_tool_request()`。
- 缺失或不匹配的 permission source context 会 fail closed，不会先创建 candidate。
- 本轮不是生产部署，不是全量 Feishu workspace ingestion。
- 本轮没有直接调用飞书任务、会议、Bitable OpenAPI；它提供的是已授权文本进入 candidate pipeline 的统一入口。后续如果接真实 API，需要在调用前先完成对应 source permission gate 和失败 fallback。

## 关键文件

| 文件 | 说明 |
|---|---|
| `memory_engine/document_ingestion.py` | 新增通用 limited Feishu source ingestion 和 source revocation 处理。 |
| `memory_engine/copilot/schemas.py` | 扩展 candidate source / evidence metadata 字段。 |
| `tests/test_document_ingestion.py` | 覆盖 task、meeting、Bitable candidate-only、source context mismatch、source revoked -> stale。 |

## 验证结果

已运行：

```bash
python3 -m unittest tests.test_document_ingestion
python3 -m unittest tests.test_copilot_schemas tests.test_document_ingestion tests.test_copilot_feishu_live tests.test_bitable_sync tests.test_feishu_interactive_cards
python3 -m compileall memory_engine scripts
```

结果：

- `tests.test_document_ingestion`：13 tests OK。
- 相关 Copilot / Feishu / Bitable 测试：62 tests OK。
- `compileall` 通过。

## 后续风险

- 真实 Feishu DM 到本项目 first-class `fmc_*` / `memory.*` tool routing 的 live E2E 仍未完成。
- 飞书任务、会议、Bitable 的真实 API 拉取和失败回退还需要后续单独接入。
- 真实样本人工复核集还需要继续扩充；本轮只补本地测试覆盖。
