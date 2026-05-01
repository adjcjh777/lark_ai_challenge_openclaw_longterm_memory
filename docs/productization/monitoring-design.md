# Feishu Memory Copilot - 监控方案设计

日期：2026-04-28
状态：方案设计（未完成生产上线）
适用范围：监控指标、采集方案、告警通道、Dashboard、SLA 定义

> 2026-05-01 校准：本文是 Prometheus/Grafana 生产监控设计，不是已实现的生产监控。当前已实现的是 `check_copilot_health.py`、`query_audit_events.py`、`check_audit_alerts.py`、OpenClaw websocket staging checker、admin `/metrics` endpoint，以及 `deploy/monitoring/copilot-admin-alerts.yml` staging alert-rule artifact / `scripts/check_prometheus_alert_rules.py` verifier。进入 L2 前仍需要把生产 Prometheus/Grafana、Alertmanager 投递和 on-call 流程落地验证。

---

## 1. 监控目标

### 1.1 核心目标

1. **可用性监控**：确保服务持续可用
2. **性能监控**：跟踪延迟、吞吐量、资源使用
3. **业务监控**：跟踪核心业务指标
4. **安全监控**：跟踪权限拒绝、异常行为
5. **审计监控**：确保审计日志完整

### 1.2 监控原则

- 指标可量化、可告警、可追溯
- 不记录敏感信息（token、secret、raw memory）
- 告警分级（info/warning/critical）
- 监控不影响业务性能

---

## 2. 监控指标定义

### 2.1 系统指标

| 指标 | 类型 | 说明 | 告警阈值 |
|------|------|------|----------|
| `system_cpu_usage` | gauge | CPU 使用率 | > 80% |
| `system_memory_usage` | gauge | 内存使用率 | > 85% |
| `system_disk_usage` | gauge | 磁盘使用率 | > 90% |
| `system_network_io` | counter | 网络 I/O | 基线偏离 > 50% |

### 2.2 应用指标

| 指标 | 类型 | 说明 | 告警阈值 |
|------|------|------|----------|
| `app_requests_total` | counter | 总请求数 | - |
| `app_request_duration_seconds` | histogram | 请求延迟 | P99 > 2s |
| `app_errors_total` | counter | 错误总数 | 错误率 > 5% |
| `app_uptime_seconds` | gauge | 服务运行时间 | - |

### 2.3 业务指标（Copilot）

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

### 2.4 基础设施指标

| 指标 | 类型 | 说明 | 告警阈值 |
|------|------|------|----------|
| `postgresql_connections_active` | gauge | 活跃连接数 | > 80% pool |
| `postgresql_query_duration_seconds` | histogram | 查询延迟 | P99 > 1s |
| `postgresql_locks_waiting` | gauge | 等待锁数 | > 5 |
| `ollama_requests_total` | counter | Ollama 请求数 | - |
| `ollama_request_duration_seconds` | histogram | Ollama 延迟 | P99 > 5s |
| `cognee_sync_success_total` | counter | Cognee 同步成功 | - |
| `cognee_sync_failure_total` | counter | Cognee 同步失败 | failure 率 > 10% |

### 2.5 OpenClaw 指标

| 指标 | 类型 | 说明 | 告警阈值 |
|------|------|------|----------|
| `openclaw_gateway_connections` | gauge | Gateway 连接数 | > 1000 |
| `openclaw_tool_invocations_total` | counter | 工具调用总数 | - |
| `openclaw_tool_duration_seconds` | histogram | 工具调用延迟 | P99 > 3s |
| `openclaw_websocket_status` | gauge | WebSocket 状态 | 0 = disconnected |

---

## 3. 监控采集方案

### 3.1 方案选型

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **Prometheus + Grafana** | 成熟、生态丰富、查询灵活 | 部署复杂、存储成本 | 生产环境 |
| **日志解析** | 简单、无需额外组件 | 实时性差、查询困难 | 开发/测试 |
| **自建脚本** | 灵活、定制化 | 维护成本高 | 轻量级监控 |

### 3.2 推荐方案

**生产环境**：Prometheus + Grafana + 自定义 Exporter

**开发/测试**：日志解析 + 自定义脚本

### 3.3 采集架构

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Prometheus Server                            │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │  Pull       │  │  Pull       │  │  Pull       │           │
│  │  Copilot    │  │  PostgreSQL │  │  Ollama     │           │
│  │  Exporter   │  │  Exporter   │  │  Exporter   │           │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘           │
│         │                │                │                    │
│         ▼                ▼                ▼                    │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                 Time Series DB                          │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Grafana Dashboard                            │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │  System     │  │  Application│  │  Business   │           │
│  │  Dashboard  │  │  Dashboard  │  │  Dashboard  │           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Alert Manager                                │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │  飞书通知    │  │  邮件       │  │  短信       │           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 告警通道设计

### 4.1 告警级别

| 级别 | 说明 | 响应时间 | 通知方式 |
|------|------|----------|----------|
| **Info** | 信息性通知 | 无 | 日志 |
| **Warning** | 需要关注 | 4 小时 | 飞书群 |
| **Critical** | 需要立即处理 | 15 分钟 | 飞书 + 邮件 + 短信 |

### 4.2 告警规则

#### 系统告警

| 规则 | 级别 | 阈值 | 说明 |
|------|------|------|------|
| HighCPUUsage | Warning | > 80% 持续 5 分钟 | CPU 使用率过高 |
| HighMemoryUsage | Warning | > 85% 持续 5 分钟 | 内存使用率过高 |
| HighDiskUsage | Critical | > 90% | 磁盘空间不足 |
| ServiceDown | Critical | 服务不可用 | 服务宕机 |

#### 应用告警

| 规则 | 级别 | 阈值 | 说明 |
|------|------|------|------|
| HighErrorRate | Critical | > 5% 持续 5 分钟 | 错误率过高 |
| HighLatency | Warning | P99 > 2s 持续 5 分钟 | 延迟过高 |
| RequestSpike | Warning | > 200% 基线 | 请求量激增 |

#### 业务告警

| 规则 | 级别 | 阈值 | 说明 |
|------|------|------|------|
| HighDenyRate | Warning | > 30% 持续 10 分钟 | 权限拒绝率过高 |
| ConsecutiveDeny | Warning | >= 5 次连续 | 连续权限拒绝 |
| IngestionFailure | Critical | > 10% 持续 10 分钟 | 摄取失败率过高 |
| AuditGap | Warning | > 30 分钟无审计 | 审计间隔过长 |
| CandidateStuck | Warning | > 24 小时未处理 | 候选卡住 |

#### 基础设施告警

| 规则 | 级别 | 阈值 | 说明 |
|------|------|------|------|
| PostgreSQLConnectionPoolExhausted | Critical | > 80% | 连接池耗尽 |
| PostgreSQLQuerySlow | Warning | P99 > 1s | 查询过慢 |
| OllamaUnavailable | Critical | 服务不可用 | Ollama 宕机 |
| OllamaHighLatency | Warning | P99 > 5s | Ollama 延迟高 |
| CogneeSyncFailure | Warning | > 10% | Cognee 同步失败 |

### 4.3 告警通道配置

#### 飞书群通知

```json
{
  "channel": "feishu",
  "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxx",
  "notify_levels": ["warning", "critical"],
  "mention_users": ["@ops-team"]
}
```

#### 邮件通知

```json
{
  "channel": "email",
  "smtp_host": "smtp.example.com",
  "smtp_port": 587,
  "from": "alerts@example.com",
  "to": ["ops-team@example.com"],
  "notify_levels": ["critical"]
}
```

#### 短信通知

```json
{
  "channel": "sms",
  "provider": "twilio",
  "to": ["+86138xxxx0000"],
  "notify_levels": ["critical"]
}
```

---

## 5. Dashboard 设计

### 5.1 System Dashboard

```text
┌─────────────────────────────────────────────────────────────────┐
│                     System Overview                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  CPU Usage: [████████████░░░░] 75%                              │
│  Memory:    [██████████░░░░░░] 65%                              │
│  Disk:      [████████░░░░░░░░] 45%                              │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Requests/s: 150    Errors/s: 2    Avg Latency: 120ms          │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  CPU History (24h)                                              │
│  100%|                                                          │
│   80%|      *                                                   │
│   60%|  *   *   *                                               │
│   40%|  *   *   *   *                                           │
│   20%|  *   *   *   *   *                                       │
│     0|__*___*___*___*___*___*___*___*___*___*___*___*___*___*__│
│       00  02  04  06  08  10  12  14  16  18  20  22           │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Application Dashboard

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Copilot Application                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Tool Invocations (1h)                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  memory.search        ████████████████████  450         │   │
│  │  memory.confirm       ████████████         280         │   │
│  │  memory.reject        ████████             180         │   │
│  │  memory.prefetch      ██████               120         │   │
│  │  memory.explain       ████                  80         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Permission Decisions (1h)                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Allow    [████████████████████████████████████]  85%  │   │
│  │  Deny     [██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]  12%  │   │
│  │  Redact   [█░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]   3%  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Request Latency Distribution (1h)                              │
│                                                                 │
│  Count                                                           │
│  5000|              *                                            │
│  4000|          *   *   *                                        │
│  3000|      *   *   *   *                                        │
│  2000|  *   *   *   *   *   *                                    │
│  1000|  *   *   *   *   *   *   *                                │
│     0|__*___*___*___*___*___*___*___*___*___*___*___*___*___*__│
│       0   50  100 150 200 250 300 350 400 450 500  (ms)        │
└─────────────────────────────────────────────────────────────────┘
```

### 5.3 Business Dashboard

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Business Metrics                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Candidate Lifecycle (7d)                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Created     ████████████████████████████  2,450       │   │
│  │  Confirmed   ████████████                  1,200       │   │
│  │  Rejected    ██████████                    980         │   │
│  │  Pending     ████                          270         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Ingestion Sources (7d)                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Message     ████████████████████████████  1,800       │   │
│  │  Document    ████████████                  850         │   │
│  │  Task        ████████                      620         │   │
│  │  Meeting     ████                          280         │   │
│  │  Bitable     ██                            120         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Audit Events (24h)                                             │
│                                                                 │
│  Events/hour                                                    │
│  2000|                                                          │
│  1500|  *   *   *   *   *   *   *   *                           │
│  1000|  *   *   *   *   *   *   *   *   *   *   *   *           │
│   500|  *   *   *   *   *   *   *   *   *   *   *   *           │
│     0|__*___*___*___*___*___*___*___*___*___*___*___*___*___*__│
│       00  02  04  06  08  10  12  14  16  18  20  22           │
└─────────────────────────────────────────────────────────────────┘
```

### 5.4 Infrastructure Dashboard

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Infrastructure                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  PostgreSQL                                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Connections: 25/100  [████████████░░░░░░░░] 25%        │   │
│  │  Query Latency P99: 45ms                                │   │
│  │  Locks Waiting: 0                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Ollama                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Model: qwen3-embedding:0.6b-fp16                       │   │
│  │  Requests/s: 120                                         │   │
│  │  Latency P99: 85ms                                       │   │
│  │  Status: Running                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  Cognee                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Status: Available (Optional)                           │   │
│  │  Sync Success: 98.5%                                    │   │
│  │  Sync Failure: 1.5%                                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  OpenClaw                                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Version: 2026.4.24                                     │   │
│  │  Gateway Status: Running                                │   │
│  │  WebSocket Connections: 45                               │   │
│  │  Agent Status: Running                                  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. SLA 定义

### 6.1 可用性 SLA

| 服务 | SLA 目标 | 计算方式 | 说明 |
|------|----------|----------|------|
| OpenClaw Gateway | 99.9% | 月度可用时间 / 总时间 | 不含计划维护 |
| CopilotService | 99.9% | 月度可用时间 / 总时间 | 核心服务 |
| PostgreSQL | 99.95% | 月度可用时间 / 总时间 | 托管服务 |
| Ollama | 99.5% | 月度可用时间 / 总时间 | 可降级 |

### 6.2 性能 SLA

| 指标 | SLA 目标 | 计算方式 | 说明 |
|------|----------|----------|------|
| memory.search P50 | < 200ms | 月度中位数 | 搜索延迟 |
| memory.search P99 | < 2000ms | 月度 99 分位 | 搜索延迟 |
| memory.confirm P50 | < 500ms | 月度中位数 | 确认延迟 |
| memory.confirm P99 | < 3000ms | 月度 99 分位 | 确认延迟 |
| 所有工具 P99 | < 5000ms | 月度 99 分位 | 总体延迟 |

### 6.3 错误率 SLA

| 指标 | SLA 目标 | 计算方式 | 说明 |
|------|----------|----------|------|
| 5xx 错误率 | < 0.1% | 月度 5xx / 总请求 | 服务端错误 |
| Permission 错误率 | < 5% | 月度 deny / 总请求 | 权限拒绝 |
| Ingestion 失败率 | < 1% | 月度失败 / 总摄取 | 摄取失败 |

### 6.4 数据 SLA

| 指标 | SLA 目标 | 计算方式 | 说明 |
|------|----------|----------|------|
| 数据持久性 | 99.999% | 月度数据丢失 / 总数据 | 数据不丢失 |
| 备份成功率 | 100% | 月度成功备份 / 计划备份 | 备份可靠 |
| RPO | < 1 小时 | 最近备份到故障时间 | 恢复点目标 |
| RTO | < 4 小时 | 故障到恢复时间 | 恢复时间目标 |

---

## 7. 监控采集配置

### 7.1 Prometheus 配置

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'copilot'
    static_configs:
      - targets: ['localhost:8080']
    metrics_path: '/metrics'

  - job_name: 'postgresql'
    static_configs:
      - targets: ['localhost:9187']

  - job_name: 'ollama'
    static_configs:
      - targets: ['localhost:11434']
    metrics_path: '/metrics'

  - job_name: 'openclaw'
    static_configs:
      - targets: ['localhost:9090']
    metrics_path: '/metrics'
```

### 7.2 Grafana Dashboard Import

```bash
# 导入预配置 Dashboard
grafana-cli plugins import /path/to/dashboard.json

# 或通过 API
curl -X POST -H "Content-Type: application/json" -d @dashboard.json \
  http://admin:admin@localhost:3000/api/dashboards/import
```

### 7.3 自定义 Exporter

```python
# scripts/prometheus_exporter.py
from prometheus_client import start_http_server, Counter, Gauge, Histogram
import time

# 定义指标
MEMORY_SEARCH_SUCCESS = Counter('memory_search_success_total', 'Memory search successes')
MEMORY_SEARCH_DENIED = Counter('memory_search_denied_total', 'Memory search denials')
PERMISSION_ALLOW = Counter('permission_allow_total', 'Permission allows')
PERMISSION_DENY = Counter('permission_deny_total', 'Permission denials')

REQUEST_LATENCY = Histogram('app_request_duration_seconds', 'Request latency',
                           buckets=[0.1, 0.2, 0.5, 1.0, 2.0, 5.0])

# 启动 exporter
start_http_server(8080)

# 更新指标
while True:
    # 从数据库或日志读取指标
    update_metrics()
    time.sleep(15)
```

---

## 8. 告警脚本

### 8.1 审计告警检查

```bash
#!/bin/bash
# scripts/check_audit_alerts.sh

python3 scripts/check_audit_alerts.py --json | jq '.alerts[] | select(.severity == "critical")' | \
while read alert; do
  # 发送飞书通知
  curl -X POST -H "Content-Type: application/json" \
    -d "{\"msg_type\":\"text\",\"content\":{\"text\":\"[CRITICAL] $alert\"}}" \
    $FEISHU_WEBHOOK_URL
done
```

### 8.2 健康检查脚本

```bash
#!/bin/bash
# scripts/health_check.sh

HEALTH=$(python3 scripts/check_copilot_health.py --json)

if echo $HEALTH | jq -e '.ok == false' > /dev/null; then
  echo "CRITICAL: Health check failed"
  # 发送告警
  exit 2
fi

if echo $HEALTH | jq -e '.checks.storage_schema.status == "warning"' > /dev/null; then
  echo "WARNING: Storage schema warning"
  exit 1
fi

echo "OK: All checks passed"
exit 0
```

---

## 9. 监控运维

### 9.1 监控数据保留

| 数据类型 | 保留周期 | 说明 |
|----------|----------|------|
| 指标数据 | 30 天 | Prometheus TSDB |
| 告警历史 | 90 天 | Alert Manager |
| Dashboard 快照 | 7 天 | Grafana |
| 审计日志 | 90 天 | PostgreSQL |

### 9.2 监控维护

```bash
# 清理旧数据
prometheus-cleanup --retention 30d

# 备份 Grafana Dashboard
grafana-cli backup /path/to/backup

# 更新监控配置
prometheus-config-reload
```

---

## 10. 参考文档

- `docs/productization/contracts/audit-observability-contract.md` - 审计契约
- `docs/productization/productized-live-architecture.md` - 架构图
- `docs/productization/deployment-runbook.md` - 部署步骤
- `docs/productization/ops-runbook.md` - 运维流程
