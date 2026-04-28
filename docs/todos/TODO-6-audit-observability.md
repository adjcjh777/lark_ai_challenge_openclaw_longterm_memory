# TODO-6：补充审计可观测性

日期：2026-04-28
负责人：程俊豪
优先级：P1
状态：已完成

---

## 1. 目标

把 `memory_audit_events` 从 smoke test 表升级为可查询、可告警、可复盘的运维面。上线后必须能回答：谁创建、确认、拒绝了记忆？哪些越权请求被拦截？提醒生成和 ingestion 失败的频率是多少？

---

## 2. 当前状态分析

### 已完成

- `memory_audit_events` 表已存在（`memory_engine/db.py`），包含 `audit_id`、`event_type`、`action`、`tool_name`、`target_type`、`target_id`、`memory_id`、`candidate_id`、`actor_id`、`actor_roles`、`tenant_id`、`organization_id`、`scope`、`permission_decision`、`reason_code`、`request_id`、`trace_id`、`visible_fields`、`redacted_fields`、`source_context`、`created_at`。
- `memory.confirm`、`memory.reject`、permission denied、limited ingestion candidate、heartbeat candidate 已写审计记录。
- healthcheck `audit_smoke` 已验证五种事件类型：`candidate_confirmed`、`candidate_rejected`、`permission_denied`、`limited_ingestion_candidate`、`heartbeat_candidate_generated`。
- healthcheck `storage_schema.audit_status` 已报告 `event_count`、`recent_failure_count`、`permission_deny_count`、`redaction_count`。

### 未完成

- 无审计查询/导出入口（当前只能直接查 SQLite）。
- 无告警规则（连续 deny、ingestion 失败等）。
- 无日志脱敏验证。
- 无回滚/停机流程文档。
- `memory.search` allow、`memory.explain_versions` allow/deny/redact、`memory.prefetch` allow/deny/redact、Feishu review card action、source revoked/deleted handling 的审计覆盖未验证。

---

## 3. 子任务清单

### 3.1 审计覆盖补全

| 子任务 | 说明 | 文件 | 验收标准 |
|---|---|---|---|
| 6.1.1 验证 `memory.search` 审计覆盖 | 确认 allow/deny/redact 三种决策都写入 `memory_audit_events` | `memory_engine/copilot/service.py`、`memory_engine/copilot/tools.py` | healthcheck audit_smoke 新增 search_allow 和 search_deny 事件类型 |
| 6.1.2 验证 `memory.explain_versions` 审计覆盖 | 确认 allow/deny/redact 都有记录 | `memory_engine/copilot/service.py` | healthcheck 或单测能读到 explain_versions 事件 |
| 6.1.3 验证 `memory.prefetch` 审计覆盖 | 确认 allow/deny/redact 都有记录 | `memory_engine/copilot/service.py` | healthcheck 或单测能读到 prefetch 事件 |
| 6.1.4 验证 Feishu review card action 审计覆盖 | confirm/reject card action 也要写审计 | `memory_engine/copilot/feishu_live.py`、`memory_engine/feishu_cards.py` | card action 触发的 confirm/reject 也有 audit_id |
| 6.1.5 验证 source revoked/deleted 审计覆盖 | `mark_feishu_source_revoked` 写审计 | `memory_engine/document_ingestion.py` | 已有 `source_permission_revoked` 事件，验证完整性 |

### 3.2 审计查询/导出入口

| 子任务 | 说明 | 文件 | 验收标准 |
|---|---|---|---|
| 6.2.1 新增审计查询脚本 | 支持按时间范围、event_type、actor_id、tenant_id 查询 | 新增 `scripts/query_audit_events.py` | `--json` 输出可被 jq 处理 |
| 6.2.2 新增审计导出功能 | 支持导出 CSV/JSON，用于人工复盘 | `scripts/query_audit_events.py` | `--format csv` 和 `--format json` 可用 |
| 6.2.3 新增审计计数摘要 | 按 event_type、permission_decision、tenant_id 聚合 | `scripts/query_audit_events.py --summary` | 输出计数表 |

### 3.3 告警规则设计

| 子任务 | 说明 | 文件 | 验收标准 |
|---|---|---|---|
| 6.3.1 定义告警阈值 | 连续 permission deny >= N、ingestion 失败率 > X%、websocket down > T 分钟 | `docs/productization/contracts/audit-observability-contract.md` 更新 | 阈值写入文档 |
| 6.3.2 实现告警检查入口 | healthcheck 或独立脚本检查告警条件 | `memory_engine/copilot/healthcheck.py` 或新增 `scripts/check_audit_alerts.py` | 超阈值时 exit code != 0 |
| 6.3.3 告警输出格式 | 结构化 JSON，包含 alert_type、severity、count、window | 同上 | 可被监控系统消费 |

### 3.4 日志脱敏验证

| 子任务 | 说明 | 文件 | 验收标准 |
|---|---|---|---|
| 6.4.1 验证 audit 日志不含 token/secret | 扫描审计记录，确认不包含 API key、Bearer token、app secret | 新增 `tests/test_audit_log_sanitization.py` | 测试通过 |
| 6.4.2 验证 deny 日志不含 raw private memory | deny 事件不记录 `current_value`、`summary`、完整 evidence quote | 同上 | 测试通过 |
| 6.4.3 验证 `redacted_fields` 只记录字段名 | 不记录被遮挡明文 | 同上 | 测试通过 |

### 3.5 回滚和停机流程

| 子任务 | 说明 | 文件 | 验收标准 |
|---|---|---|---|
| 6.5.1 编写停机流程文档 | 如何停止 listener、清理 Ollama 模型、关闭 DB 连接 | `docs/productization/feishu-staging-runbook.md` 更新 | 新机器可按文档停机 |
| 6.5.2 编写审计数据回滚说明 | 审计表只追加不删除；如需清理如何操作 | `docs/productization/contracts/audit-observability-contract.md` 更新 | 操作步骤清晰 |
| 6.5.3 编写紧急降级流程 | embedding 不可用、Cognee 不可用、OpenClaw websocket 断开时的 fallback | `docs/productization/feishu-staging-runbook.md` 更新 | 每种场景有明确 fallback |

---

## 4. 依赖关系

| 依赖项 | 说明 |
|---|---|
| `memory_audit_events` 表 | 已完成（Phase A） |
| `memory_engine/copilot/service.py` 审计写入 | 已完成基础，需验证全覆盖 |
| `memory_engine/copilot/healthcheck.py` audit_status | 已完成基础，需扩展 |
| `memory_engine/document_ingestion.py` source revoked 审计 | 已完成，需验证 |

---

## 5. 风险和注意事项

1. **审计表膨胀**：本地 SQLite 无自动清理；长期运行需考虑 retention 策略。
2. **日志脱敏不完整**：新增 source_type 可能引入新的敏感字段，需持续验证。
3. **告警误报**：阈值过低会导致告警疲劳，需在真实数据上校准。
4. **不冒称生产监控**：当前只是本地 SQLite 审计查询，不是 Prometheus/Grafana 级别的生产监控。

---

## 6. 验证命令

```bash
# 基础检查
python3 scripts/check_openclaw_version.py
python3 scripts/check_copilot_health.py --json

# 审计覆盖验证
python3 -m unittest tests.test_copilot_healthcheck
python3 -m unittest tests.test_audit_log_sanitization  # 新增

# 审计查询验证
python3 scripts/query_audit_events.py --json --limit 10
python3 scripts/query_audit_events.py --summary --json

# 告警检查
python3 scripts/check_audit_alerts.py --json  # 新增

# 日志脱敏
python3 -m unittest tests.test_audit_log_sanitization  # 新增

# 编译检查
python3 -m compileall memory_engine scripts

# Git 检查
git diff --check
```
