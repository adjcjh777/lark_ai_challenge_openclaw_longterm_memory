# Audit & Observability Contract：Feishu Memory Copilot Phase 1

日期：2026-04-28
状态：Phase A + Phase 6 审计可观测性补充完成。本地 SQLite audit table + healthcheck audit smoke + 审计查询/导出/告警 + ingestion failure 显式审计 + websocket 运维入口 + embedding fallback 可观测字段 + 日志脱敏验证。仍不是生产级 Prometheus/Grafana 监控。
适用范围：Copilot service、permission decisions、Feishu review surface、OpenClaw tool trace、healthcheck、审计查询脚本、告警检查脚本。

## 1. 目标

让完整产品能解释每次记忆读写和提醒为什么发生、谁触发、谁能看、哪些字段被遮挡。审计覆盖所有 5 种工具（search、explain_versions、prefetch、confirm、reject），以及 heartbeat、source revoked 等场景。

上线后必须能回答：
- 谁创建、确认、拒绝了记忆？
- 哪些越权请求被拦截？
- 提醒生成和 ingestion 失败的频率是多少？

### 1.1 Phase 6 新增能力

- 审计查询脚本 `scripts/query_audit_events.py`：支持按时间范围、event_type、actor_id、tenant_id 查询，支持 CSV/JSON 导出，支持 summary 聚合
- 审计告警检查 `scripts/check_audit_alerts.py`：连续 deny、ingestion 失败率、deny 比率、审计间隔告警
- `ingestion_failed` 显式审计事件：permission/source mismatch、Feishu fetch 失败、候选提取为空都会写入脱敏审计，便于查询和告警
- Healthcheck `openclaw_websocket`：默认不主动跑 live 检查，只给 staging checker 命令；显式开启时纳入 running/probe/log/health consistency
- Healthcheck `embedding_provider`：输出 `runtime_fallback_available`、`unavailable_reason`、`monitoring_status`，避免把 deterministic fallback 写成长期 embedding 服务
- 日志脱敏测试 `tests/test_audit_log_sanitization.py`：验证审计日志不含 token/secret、deny 日志不含 raw private memory、redacted_fields 只记录字段名
- Healthcheck audit_smoke 增强：验证所有 5 种工具和 search allow/deny 都写入审计
- 停机和回滚流程文档 `docs/productization/feishu-staging-runbook.md`

## 2. Audit Events

每个审计事件必须包含：

| 字段 | 说明 |
|---|---|
| `audit_id` | 审计 ID。 |
| `request_id` | OpenClaw/Feishu/service 请求 ID。 |
| `trace_id` | 跨工具链路 ID。 |
| `actor_id` | 操作者 user/open id。 |
| `actor_roles` | 角色列表。 |
| `tenant_id` | 请求租户。 |
| `organization_id` | 请求组织。 |
| `action` | `memory.search` / `memory.confirm` 等。 |
| `target_type` | memory/candidate/evidence/reminder/source。 |
| `target_id` | 目标 ID，可空。 |
| `permission_decision` | allow/deny/redact/withhold。 |
| `reason_code` | 机器可读原因。 |
| `visible_fields` | 允许输出字段。 |
| `redacted_fields` | 被遮挡字段名。 |
| `source_context` | entrypoint/chat/doc/workspace。 |
| `created_at` | 审计时间。 |

## 3. Required Audit Points

| Event | Required |
|---|---|
| `memory.search` allow/deny/redact | 是 |
| `memory.create_candidate` allow/deny | 是 |
| `memory.confirm` allow/deny | 是 |
| `memory.reject` allow/deny | 是 |
| `memory.explain_versions` allow/deny/redact | 是 |
| `memory.prefetch` allow/deny/redact | 是 |
| heartbeat reminder generated/suppressed | 是 |
| Feishu review card approve/reject click | 是 |
| limited ingestion source -> candidate | 是 |
| limited ingestion failure / fetch failure / no candidate extracted | 是 |
| source revoked/deleted handling | 是 |
| embedding provider unavailable fallback | 是 |

## 4. Healthcheck Fields

Phase 6 healthcheck 必须能输出：

```json
{
  "ok": true,
  "openclaw_version": "2026.4.24",
  "copilot_service_import": "ok",
  "storage": {
    "available": true,
    "schema_version": 2,
    "tenant_visibility_columns": true,
    "audit_available": true
  },
  "permission_contract": {
    "loaded": true,
    "fail_closed": true,
    "payload_shape": "current_context.permission"
  },
  "cognee_adapter": {
    "configured": true,
    "fallback_available": true
  },
  "embedding_provider": {
    "provider": "ollama",
    "model": "qwen3-embedding:0.6b-fp16",
    "available": true,
    "runtime_fallback_available": true,
    "monitoring_status": "configuration_only"
  },
  "openclaw_websocket": {
    "status": "skipped",
    "live_check_run": false,
    "command": "python3 scripts/check_openclaw_feishu_websocket.py --json"
  }
}
```

## 5. Metrics / Counters

最小计数：

- `memory_search_success_total`
- `memory_search_denied_total`
- `permission_allow_total`
- `permission_deny_total`
- `permission_redact_total`
- `candidate_created_total`
- `candidate_confirmed_total`
- `candidate_rejected_total`
- `reminder_generated_total`
- `reminder_suppressed_total`
- `ingestion_candidate_only_total`
- `ingestion_failed_total`
- `embedding_unavailable_total`
- `sensitive_redaction_total`

## 6. Safe Logging Rules

- 不记录 token、app secret、OpenAI/RightCode key、Bearer token。
- deny 日志不记录 raw private memory、完整 evidence quote 或真实飞书私密内容。
- `redacted_fields` 只记录字段名，不记录被遮挡明文。
- 飞书 chat_id/user_id 可以记录内部 ID，但提交仓库前必须确保日志不进入 git。

## 7. Alert Thresholds

告警规则定义（可通过 `scripts/check_audit_alerts.py` 参数调整）：

| 告警类型 | 默认阈值 | 严重级别 | 说明 |
|---|---|---|---|
| `consecutive_permission_deny` | >= 5 次 | warning (5-9), critical (>=10) | 连续 permission deny 事件 |
| `high_deny_rate` | > 30% | warning (30-60%), critical (>60%) | 时间窗口内 deny 比率 |
| `ingestion_failure_rate` | > 10% | warning (10-20%), critical (>20%) | ingestion 失败比率 |
| `audit_gap` | > 30 分钟 | warning (30-90min), critical (>90min) | 审计事件间隔过长 |

默认时间窗口：60 分钟。

告警输出格式：
```json
{
  "ok": false,
  "alert_count": 2,
  "alerts": [
    {
      "alert_type": "consecutive_permission_deny",
      "severity": "warning",
      "count": 7,
      "threshold": 5,
      "window_minutes": 60,
      "message": "Detected 7 consecutive permission deny events (threshold: 5)"
    }
  ],
  "thresholds": {
    "consecutive_deny": 5,
    "deny_rate": 0.3,
    "ingestion_failure_rate": 0.1,
    "window_minutes": 60,
    "audit_gap_minutes": 30
  }
}
```

## 8. Acceptance Criteria

- 每个 permission decision 有 audit 事件或结构化日志。
- 每个 review action 有 actor、role、reason 和 source_context。
- Healthcheck 能显示 schema version 和 permission contract loaded 状态。
- Product QA 能按 audit/trace 查出一次 search 或 confirm 的完整链路。
- `python3 scripts/query_audit_events.py --json --limit 10` 可正常输出。
- `python3 scripts/query_audit_events.py --summary --json` 可正常输出聚合统计。
- `python3 scripts/check_audit_alerts.py --json` 可正常输出告警检查结果。
- `python3 scripts/check_copilot_health.py --json` 默认包含 skipped 的 `openclaw_websocket` 运维入口；需要 live staging 时使用 `--openclaw-websocket-check`。
- `python3 -m unittest tests.test_audit_log_sanitization` 测试全部通过。
- `python3 -m unittest tests.test_audit_ops_scripts tests.test_document_ingestion tests.test_copilot_healthcheck` 覆盖审计查询、显式 ingestion failure、websocket health 注入和 embedding fallback 字段。

## 9. Audit Data Rollback

审计表 `memory_audit_events` 设计为 append-only（只追加不删除）。

### 9.1 为什么不能随意删除审计数据

- 审计数据用于合规和复盘，删除可能违反审计要求
- SQLite 不支持事务回滚到特定时间点
- 自动 DROP columns 风险高，可能破坏已写入审计证据

### 9.2 安全的审计数据操作

```bash
# 备份当前审计数据
cp data/memory.sqlite data/memory.sqlite.backup.$(date +%Y%m%d)

# 查看审计数据量
python3 scripts/query_audit_events.py --summary --json

# 清理 90 天前的审计数据（谨慎操作）
sqlite3 data/memory.sqlite "
DELETE FROM memory_audit_events
WHERE created_at < strftime('%s', 'now', '-90 days') * 1000;
VACUUM;
"
```

### 9.3 数据库整体回滚

```bash
# 1. 停止所有服务
pkill -f "copilot\|lark-cli\|openclaw"

# 2. 从备份恢复
cp data/memory.sqlite.backup.20260428 data/memory.sqlite

# 3. 重启服务
python3 -m memory_engine.copilot.feishu_live
```

### 9.4 保留结构，只清理数据

```bash
# 只清理审计数据，保留表结构
sqlite3 data/memory.sqlite "DELETE FROM memory_audit_events;"

# 重新初始化 schema（安全，不会删除数据）
python3 -c "from memory_engine.db import connect, init_db; conn = connect(); init_db(conn)"
```

---

## 10. 生产级监控指标定义

日期：2026-04-28
状态：方案设计（未完成生产上线）
适用范围：生产环境监控指标、采集方案、告警规则

### 10.1 指标分类

#### 系统指标

| 指标 | 类型 | 说明 | 告警阈值 |
|------|------|------|----------|
| `system_cpu_usage` | gauge | CPU 使用率 | > 80% |
| `system_memory_usage` | gauge | 内存使用率 | > 85% |
| `system_disk_usage` | gauge | 磁盘使用率 | > 90% |
| `system_network_io` | counter | 网络 I/O | 基线偏离 > 50% |

#### 应用指标

| 指标 | 类型 | 说明 | 告警阈值 |
|------|------|------|----------|
| `app_requests_total` | counter | 总请求数 | - |
| `app_request_duration_seconds` | histogram | 请求延迟 | P99 > 2s |
| `app_errors_total` | counter | 错误总数 | 错误率 > 5% |
| `app_uptime_seconds` | gauge | 服务运行时间 | - |

#### 业务指标

| 指标 | 类型 | 说明 | 告警阈值 |
|------|------|------|----------|
| `memory_search_success_total` | counter | 搜索成功数 | - |
| `memory_search_denied_total` | counter | 搜索拒绝数 | deny 率 > 30% |
| `permission_allow_total` | counter | 权限允许数 | - |
| `permission_deny_total` | counter | 权限拒绝数 | - |
| `permission_redact_total` | counter | 权限脱敏数 | - |
| `candidate_created_total` | counter | 候选创建数 | - |
| `candidate_confirmed_total` | counter | 候选确认数 | - |
| `candidate_rejected_total` | counter | 候选拒绝数 | - |
| `reminder_generated_total` | counter | 提醒生成数 | - |
| `reminder_suppressed_total` | counter | 提醒抑制数 | - |
| `ingestion_candidate_only_total` | counter | 候选摄取数 | - |
| `sensitive_redaction_total` | counter | 敏感脱敏数 | - |

#### 基础设施指标

| 指标 | 类型 | 说明 | 告警阈值 |
|------|------|------|----------|
| `postgresql_connections_active` | gauge | 活跃连接数 | > 80% pool |
| `postgresql_query_duration_seconds` | histogram | 查询延迟 | P99 > 1s |
| `postgresql_locks_waiting` | gauge | 等待锁数 | > 5 |
| `ollama_requests_total` | counter | Ollama 请求数 | - |
| `ollama_request_duration_seconds` | histogram | Ollama 延迟 | P99 > 5s |
| `cognee_sync_success_total` | counter | Cognee 同步成功 | - |
| `cognee_sync_failure_total` | counter | Cognee 同步失败 | failure 率 > 10% |

#### OpenClaw 指标

| 指标 | 类型 | 说明 | 告警阈值 |
|------|------|------|----------|
| `openclaw_gateway_connections` | gauge | Gateway 连接数 | > 1000 |
| `openclaw_tool_invocations_total` | counter | 工具调用总数 | - |
| `openclaw_tool_duration_seconds` | histogram | 工具调用延迟 | P99 > 3s |
| `openclaw_websocket_status` | gauge | WebSocket 状态 | 0 = disconnected |

### 10.2 SLA 定义

#### 可用性 SLA

| 服务 | SLA 目标 | 计算方式 | 说明 |
|------|----------|----------|------|
| OpenClaw Gateway | 99.9% | 月度可用时间 / 总时间 | 不含计划维护 |
| CopilotService | 99.9% | 月度可用时间 / 总时间 | 核心服务 |
| PostgreSQL | 99.95% | 月度可用时间 / 总时间 | 托管服务 |
| Ollama | 99.5% | 月度可用时间 / 总时间 | 可降级 |

#### 性能 SLA

| 指标 | SLA 目标 | 计算方式 | 说明 |
|------|----------|----------|------|
| memory.search P50 | < 200ms | 月度中位数 | 搜索延迟 |
| memory.search P99 | < 2000ms | 月度 99 分位 | 搜索延迟 |
| memory.confirm P50 | < 500ms | 月度中位数 | 确认延迟 |
| memory.confirm P99 | < 3000ms | 月度 99 分位 | 确认延迟 |
| 所有工具 P99 | < 5000ms | 月度 99 分位 | 总体延迟 |

#### 错误率 SLA

| 指标 | SLA 目标 | 计算方式 | 说明 |
|------|----------|----------|------|
| 5xx 错误率 | < 0.1% | 月度 5xx / 总请求 | 服务端错误 |
| Permission 错误率 | < 5% | 月度 deny / 总请求 | 权限拒绝 |
| Ingestion 失败率 | < 1% | 月度失败 / 总摄取 | 摄取失败 |

### 10.3 告警规则

#### 系统告警

| 规则 | 级别 | 阈值 | 说明 |
|------|------|------|------|
| HighCPUUsage | Warning | > 80% 持续 5 分钟 | CPU 使用率过高 |
| HighMemoryUsage | Warning | > 85% 持续 5 分钟 | 内存使用率过高 |
| HighDiskUsage | Critical | > 90% | 磁盘空间不足 |
| ServiceDown | Critical | 服务不可用 | 服务宕机 |

#### 业务告警

| 规则 | 级别 | 阈值 | 说明 |
|------|------|------|------|
| HighDenyRate | Warning | > 30% 持续 10 分钟 | 权限拒绝率过高 |
| ConsecutiveDeny | Warning | >= 5 次连续 | 连续权限拒绝 |
| IngestionFailure | Critical | > 10% 持续 10 分钟 | 摄取失败率过高 |
| AuditGap | Warning | > 30 分钟无审计 | 审计间隔过长 |
| CandidateStuck | Warning | > 24 小时未处理 | 候选卡住 |

### 10.4 参考文档

- `docs/productization/monitoring-design.md` - 监控方案
- `docs/productization/ops-runbook.md` - 运维流程
- `docs/productization/productized-live-architecture.md` - 架构图
