# Phase A Storage Migration + Audit Table Handoff

日期：2026-04-28
状态：已完成本地闭环，下一阶段从 Phase B 真实 OpenClaw Agent Runtime 验收开始。

## 先看这个

1. 今天完成的是 Phase A：把本地 SQLite 事实源补到 schema version `2`，并加上审计表。
2. 下一轮从 Phase B 开始，不要重复做 Phase A，也不要回到旧 Bot-first / CLI-first 主线。
3. 本阶段交付的是本地产品化存储和审计闭环，不是生产部署、长期运行监控或完整多租户后台。
4. 判断做对的入口是 `python3 scripts/check_copilot_health.py --json`：`storage_schema.status=pass` 且 `audit_smoke.status=pass`。
5. 如果后续遇到旧数据库初始化失败，优先检查 `memory_engine/db.py` 里的兼容迁移顺序：先补列，再建依赖新列的索引。

## 本阶段做了什么

- `memory_engine/db.py`：新增 `tenant_id`、`organization_id`、`visibility_policy` 兼容字段；新增 `memory_audit_events`；用 `PRAGMA user_version = 2` 标记本地 schema；旧库通过 `ALTER TABLE ... ADD COLUMN` 兼容迁移。
- `memory_engine/repository.py`：新增 `record_audit_event()`，统一写审计事件，不记录 token 或 secret。
- `memory_engine/copilot/service.py`：在 `CopilotService` 层记录权限 allow/deny、confirm、reject、limited ingestion candidate 和 heartbeat candidate 审计，保持入口仍走 `handle_tool_request()` / `CopilotService`。
- `memory_engine/copilot/governance.py`：新 candidate 写入会带 created/updated actor，evidence 写入会带 ingested time。
- `memory_engine/copilot/healthcheck.py`：storage schema 不再是 warning；新增 audit smoke，覆盖 confirm/reject/deny/limited ingestion/heartbeat。
- `tests/test_copilot_permissions.py`、`tests/test_copilot_healthcheck.py`：补审计断言，确认 deny 不会改 candidate 状态且会留下 audit record。

## 验收证据

已运行：

```bash
python3 -m unittest tests.test_copilot_permissions tests.test_copilot_healthcheck
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools
python3 scripts/check_copilot_health.py --json
```

已确认：

- `storage_schema.status=pass`
- `storage_schema.schema_version=2`
- `storage_schema.audit_table_available=true`
- `audit_smoke.status=pass`
- `audit_smoke.event_types` 包含 `candidate_confirmed`、`candidate_rejected`、`permission_denied`、`limited_ingestion_candidate`、`heartbeat_candidate_generated`

## 下一步从哪里开始

下一轮执行 Phase B：真实 OpenClaw Agent Runtime 验收。

直接入口：

- [full-copilot-next-execution-doc.md](full-copilot-next-execution-doc.md)
- [README.md](../../README.md)
- [OpenClaw tool schema](../../agent_adapters/openclaw/memory_tools.schema.json)
- [demo-runbook.md](../demo-runbook.md)

Phase B 要交付：

- 新增 `docs/productization/openclaw-runtime-evidence.md`。
- 至少 3 条真实 OpenClaw Agent runtime flow：历史决策召回、candidate 创建后确认或拒绝、任务前 `memory.prefetch`。
- 每条记录 input、output、tool、request_id、trace_id、permission_decision 和失败回退。

## 仍未实现或仍有风险

- 还没有真实 OpenClaw Agent runtime 独立验收记录。
- Feishu staging runbook 还没整理成可交接流程。
- live Cognee / Ollama embedding gate 已由后续 Phase D 补齐；healthcheck 仍保留 configuration-only，不把它写成长期 embedding 服务。
- 当前 storage migration 是本地 SQLite 兼容迁移，不是生产级多租户后台或长期运行监控。
