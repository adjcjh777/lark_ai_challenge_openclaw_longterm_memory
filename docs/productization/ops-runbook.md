# Feishu Memory Copilot - 运维流程设计

日期：2026-04-28
状态：方案设计（未完成生产上线）
适用范围：日常运维 checklist、故障排查、扩缩容、版本升级

> 2026-04-29 校准：本文是生产运维草案，不是当前可直接执行的上线 runbook。部分命令依赖未部署的 PostgreSQL、systemd、Prometheus/Grafana 或未实现脚本；当前可执行运维入口以 [audit-ops-observability-handoff.md](handoffs/audit-ops-observability-handoff.md) 和 [productized-live-long-run-plan.md](productized-live-long-run-plan.md) 为准。

---

## 1. 日常运维 Checklist

### 1.1 每日运维（Daily）

| 时间 | 检查项 | 命令 | 预期结果 | 处理方式 |
|------|--------|------|----------|----------|
| 09:00 | 服务健康检查 | `python3 scripts/check_copilot_health.py --json` | ok=true | 通知告警 |
| 09:00 | OpenClaw 状态 | `openclaw health --json` | status=running | 重启服务 |
| 09:00 | PostgreSQL 状态 | `pg_isready -h localhost -p 5432` | accepting connections | 检查日志 |
| 09:00 | Ollama 状态 | `ollama ps` | 模型运行中 | 重启服务 |
| 09:00 | 磁盘空间 | `df -h /var/lib/postgresql` | < 80% | 清理日志 |
| 10:00 | 审计告警检查 | `python3 scripts/check_audit_alerts.py --json` | ok=true | 处理告警 |
| 10:00 | 候选队列检查 | `python3 scripts/check_pending_candidates.py --json` | count < 100 | 审核候选 |
| 18:00 | 服务健康检查 | `python3 scripts/check_copilot_health.py --json` | ok=true | 通知告警 |
| 18:00 | 日志检查 | `tail -100 logs/feishu_live_*.log` | 无 ERROR | 排查问题 |

### 1.2 每周运维（Weekly）

| 时间 | 检查项 | 命令 | 预期结果 | 处理方式 |
|------|--------|------|----------|----------|
| 周一 09:00 | 数据库备份验证 | `pg_restore --list /path/to/backup.dump` | 列出表 | 重新备份 |
| 周一 09:00 | 慢查询检查 | `SELECT * FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;` | 无异常 | 优化查询 |
| 周一 09:00 | 连接池检查 | `SELECT count(*) FROM pg_stat_activity;` | < 80% pool | 调整配置 |
| 周一 09:00 | 审计数据量 | `python3 scripts/query_audit_events.py --summary --json` | 正常增长 | 归档旧数据 |
| 周一 09:00 | 错误日志分析 | `grep -c ERROR logs/*.log` | < 10 | 排查问题 |

### 1.3 每月运维（Monthly）

| 时间 | 检查项 | 命令 | 预期结果 | 处理方式 |
|------|--------|------|----------|----------|
| 每月 1 日 | 数据库维护 | `VACUUM ANALYZE;` | 完成 | 无 |
| 每月 1 日 | 索引重建 | `REINDEX DATABASE memory_copilot;` | 完成 | 无 |
| 每月 1 日 | 旧数据清理 | `DELETE FROM memory_audit_events WHERE created_at < ...` | 完成 | 备份后清理 |
| 每月 1 日 | 安全审计 | 审查权限变更和敏感操作 | 无异常 | 报告 |
| 每月 1 日 | 容量评估 | 评估存储和性能增长 | 趋势正常 | 扩容规划 |

---

## 2. 故障排查流程

### 2.1 故障分级

| 级别 | 说明 | 响应时间 | 通知方式 |
|------|------|----------|----------|
| P0 | 服务完全不可用 | 15 分钟 | 飞书 + 邮件 + 短信 |
| P1 | 核心功能受损 | 30 分钟 | 飞书 + 邮件 |
| P2 | 非核心功能受损 | 4 小时 | 飞书 |
| P3 | 轻微问题 | 24 小时 | 日志 |

### 2.2 常见故障排查

#### 故障 1：OpenClaw Gateway 不可用

**症状**：飞书消息不触发处理

**排查步骤**：
```bash
# 1. 检查 Gateway 状态
openclaw health --json

# 2. 检查 WebSocket 连接
openclaw channels status --probe --json

# 3. 检查 Gateway 日志
openclaw gateway logs --tail 100

# 4. 检查网络连通性
curl -I https://open.feishu.cn

# 5. 检查飞书应用配置
openclaw config show
```

**处理方式**：
```bash
# 重启 Gateway
openclaw gateway restart

# 如果重启失败，重新初始化
openclaw init --force
openclaw gateway start --daemon
```

#### 故障 2：PostgreSQL 连接失败

**症状**：所有数据库操作失败

**排查步骤**：
```bash
# 1. 检查 PostgreSQL 服务
sudo systemctl status postgresql

# 2. 检查连接
psql -U memory_copilot -d memory_copilot -c "SELECT 1;"

# 3. 检查连接数
psql -U memory_copilot -d memory_copilot -c "SELECT count(*) FROM pg_stat_activity;"

# 4. 检查 pg_hba.conf
sudo cat /etc/postgresql/15/main/pg_hba.conf | grep memory_copilot

# 5. 检查 PostgreSQL 日志
sudo tail -100 /var/log/postgresql/postgresql-15-main.log
```

**处理方式**：
```bash
# 重启 PostgreSQL
sudo systemctl restart postgresql

# 如果连接数过多，终止空闲连接
psql -U memory_copilot -d memory_copilot -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '10 minutes';"
```

#### 故障 3：Ollama 不可用

**症状**：Embedding 降级到 DeterministicEmbeddingProvider

**排查步骤**：
```bash
# 1. 检查 Ollama 服务
curl http://localhost:11434/api/tags

# 2. 检查模型状态
ollama ps

# 3. 检查 Ollama 日志
journalctl -u ollama --tail 100

# 4. 检查磁盘空间
df -h ~/.ollama
```

**处理方式**：
```bash
# 重启 Ollama
pkill ollama
ollama serve &

# 重新拉取模型
ollama pull qwen3-embedding:0.6b-fp16

# 验证恢复
python3 scripts/check_live_embedding_gate.py --json
```

#### 故障 4：高错误率

**症状**：错误率 > 5%

**排查步骤**：
```bash
# 1. 检查错误日志
grep -c ERROR logs/*.log

# 2. 检查最近错误
tail -200 logs/*.log | grep ERROR

# 3. 检查审计告警
python3 scripts/check_audit_alerts.py --json

# 4. 检查服务健康
python3 scripts/check_copilot_health.py --json
```

**处理方式**：
```bash
# 根据错误类型处理
# - 权限错误：检查 permission context
# - 数据库错误：检查连接和查询
# - 超时错误：检查性能和资源
```

#### 故障 5：高延迟

**症状**：P99 延迟 > 2s

**排查步骤**：
```bash
# 1. 检查系统资源
top -bn1 | head -20

# 2. 检查数据库慢查询
psql -U memory_copilot -d memory_copilot -c "SELECT * FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 5;"

# 3. 检查 Ollama 延迟
curl -w "@curl-format.txt" -o /dev/null -s http://localhost:11434/api/embeddings

# 4. 检查网络延迟
ping localhost
```

**处理方式**：
```bash
# - 优化慢查询
# - 增加连接池大小
# - 扩容服务器
# - 优化 Ollama 配置
```

### 2.3 故障恢复流程

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Fault Recovery Flow                          │
│                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐│
│  │ Detect   │ -> │ Diagnose │ -> │ Fix      │ -> │ Verify   ││
│  │ Fault    │    │ Root     │    │ Issue    │    │ Recovery ││
│  │          │    │ Cause    │    │          │    │          ││
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘│
│       │               │               │               │       │
│       ▼               ▼               ▼               ▼       │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐│
│  │ Alert    │    │ Log      │    │ Restart  │    │ Health   ││
│  │ Triggered│    │ Analysis │    │ Service  │    │ Check    ││
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘│
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 扩缩容方案

### 3.1 扩容触发条件

| 指标 | 阈值 | 扩容类型 |
|------|------|----------|
| CPU 使用率 | > 80% 持续 30 分钟 | 垂直/水平 |
| 内存使用率 | > 85% 持续 30 分钟 | 垂直 |
| 磁盘使用率 | > 80% | 垂直 |
| 连接池使用率 | > 80% | 水平 |
| 请求延迟 P99 | > 2s 持续 30 分钟 | 水平 |
| 错误率 | > 5% 持续 30 分钟 | 水平 |

### 3.2 缩容触发条件

| 指标 | 阈值 | 缩容类型 |
|------|------|----------|
| CPU 使用率 | < 30% 持续 24 小时 | 水平 |
| 内存使用率 | < 40% 持续 24 小时 | 垂直 |
| 请求量 | < 50% 基线 持续 24 小时 | 水平 |

### 3.3 水平扩缩容

#### 扩容步骤

```bash
# 1. 增加 OpenClaw 实例
openclaw gateway start --daemon --instance-id gateway-2
openclaw agent start --agent main --daemon --instance-id agent-2

# 2. 更新负载均衡配置
# 假设使用 Nginx
vim /etc/nginx/conf.d/memory-copilot.conf
# 添加新实例到 upstream

# 3. 验证新实例
curl http://gateway-2:8080/health

# 4. 监控新实例
# 检查 Prometheus/Grafana
```

#### 缩容步骤

```bash
# 1. 停止目标实例
openclaw gateway stop --instance-id gateway-2
openclaw agent stop --instance-id agent-2

# 2. 更新负载均衡配置
vim /etc/nginx/conf.d/memory-copilot.conf
# 移除实例

# 3. 验证剩余实例
python3 scripts/check_copilot_health.py --json
```

### 3.4 垂直扩缩容

#### 扩容步骤

```bash
# 1. 停止服务
openclaw gateway stop
openclaw agent stop
sudo systemctl stop postgresql

# 2. 升级服务器配置
# - 增加 CPU
# - 增加内存
# - 增加磁盘

# 3. 更新 PostgreSQL 配置
vim /etc/postgresql/15/main/postgresql.conf
# 调整 shared_buffers, work_mem 等

# 4. 重启服务
sudo systemctl start postgresql
openclaw gateway start --daemon
openclaw agent start --agent main --daemon

# 5. 验证
python3 scripts/check_copilot_health.py --json
```

### 3.5 自动扩缩容（推荐）

```yaml
# kubernetes deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: memory-copilot
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: copilot
        resources:
          requests:
            cpu: "500m"
            memory: "512Mi"
          limits:
            cpu: "2000m"
            memory: "2Gi"
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: memory-copilot-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: memory-copilot
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

---

## 4. 版本升级流程

### 4.1 升级策略

| 组件 | 策略 | 说明 |
|------|------|------|
| OpenClaw | 锁定版本 | 当前锁定 2026.4.24 |
| CopilotService | 滚动升级 | 零停机 |
| PostgreSQL | 停机升级 | 需要维护窗口 |
| Ollama | 滚动升级 | 可降级 |
| Cognee | 滚动升级 | 可降级 |

### 4.2 升级流程

```text
┌─────────────────────────────────────────────────────────────────┐
│                     Version Upgrade Flow                         │
│                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐│
│  │ Plan     │ -> │ Backup   │ -> │ Upgrade  │ -> │ Verify   ││
│  │ Upgrade  │    │ Data     │    │          │    │          ││
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘│
│       │               │               │               │       │
│       ▼               ▼               ▼               ▼       │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐│
│  │ Review   │    │ Create   │    │ Execute  │    │ Run      ││
│  │ Changelog│    │ Snapshot │    │ Upgrade  │    │ Tests    ││
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘│
│       │                               │               │       │
│       │                               ▼               │       │
│       │                        ┌──────────┐          │       │
│       │                        │ Rollback │          │       │
│       │                        │ if Failed│          │       │
│       │                        └──────────┘          │       │
│       │                               │               │       │
│       │                               ▼               ▼       │
│       │                        ┌──────────────────────────┐   │
│       └──────────────────────> │    Complete Upgrade      │   │
│                                └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 升级步骤

#### CopilotService 升级

```bash
# 1. 计划升级
# - 阅读 Changelog
# - 确认兼容性
# - 准备回滚方案

# 2. 备份数据
pg_dump -U memory_copilot -d memory_copilot -Fc -f /path/to/backup.dump

# 3. 停止服务
openclaw gateway stop
openclaw agent stop

# 4. 拉取新代码
git fetch origin
git checkout <new-tag>

# 5. 安装依赖
pip install -r requirements.txt

# 6. 运行迁移（如果需要）
python3 scripts/migrate_copilot_storage.py --dry-run --json
python3 scripts/migrate_copilot_storage.py --apply --json

# 7. 验证
python3 -m compileall memory_engine scripts
python3 -m pytest tests/ -v

# 8. 启动服务
openclaw gateway start --daemon
openclaw agent start --agent main --daemon

# 9. 验证健康
python3 scripts/check_copilot_health.py --json

# 10. 监控 30 分钟
# 检查日志和指标
```

#### PostgreSQL 升级

```bash
# 1. 计划维护窗口
# - 选择低峰期
# - 通知用户

# 2. 备份数据
pg_dump -U memory_copilot -d memory_copilot -Fc -f /path/to/backup.dump

# 3. 停止服务
openclaw gateway stop
openclaw agent stop

# 4. 停止 PostgreSQL
sudo systemctl stop postgresql

# 5. 升级 PostgreSQL
sudo apt install postgresql-16

# 6. 运行升级脚本
sudo pg_upgradecluster 15 main

# 7. 启动 PostgreSQL
sudo systemctl start postgresql

# 8. 验证
psql -U memory_copilot -d memory_copilot -c "SELECT version();"

# 9. 启动应用服务
openclaw gateway start --daemon
openclaw agent start --agent main --daemon

# 10. 验证健康
python3 scripts/check_copilot_health.py --json
```

### 4.4 回滚流程

```bash
# 1. 停止服务
openclaw gateway stop
openclaw agent stop

# 2. 回滚代码
git checkout <previous-tag>

# 3. 回滚数据库（如果需要）
pg_restore -U memory_copilot -d memory_copilot /path/to/backup.dump

# 4. 安装依赖
pip install -r requirements.txt

# 5. 启动服务
openclaw gateway start --daemon
openclaw agent start --agent main --daemon

# 6. 验证
python3 scripts/check_copilot_health.py --json
```

---

## 5. 维护窗口管理

### 5.1 维护窗口定义

| 类型 | 时间 | 通知提前期 | 说明 |
|------|------|------------|------|
| 计划维护 | 周日 02:00-06:00 | 7 天 | 常规维护 |
| 紧急维护 | 随时 | 1 小时 | 安全漏洞 |
| 升级维护 | 周六 02:00-06:00 | 14 天 | 版本升级 |

### 5.2 维护通知

```bash
# 发送维护通知
curl -X POST -H "Content-Type: application/json" \
  -d '{
    "msg_type": "text",
    "content": {
      "text": "⚠️ 计划维护通知\n\n时间: 2026-05-01 02:00-06:00\n影响: 服务暂时不可用\n原因: 数据库升级\n\n请提前保存工作。"
    }
  }' \
  $FEISHU_WEBHOOK_URL
```

---

## 6. 应急预案

### 6.1 数据库故障

```bash
# 1. 立即停止所有写入
# 2. 启用只读模式
psql -U memory_copilot -d memory_copilot -c "ALTER SYSTEM SET default_transaction_read_only = on;"

# 3. 从备份恢复
pg_restore -U memory_copilot -d memory_copilot /path/to/latest-backup.dump

# 4. 恢复读写模式
psql -U memory_copilot -d memory_copilot -c "ALTER SYSTEM SET default_transaction_read_only = off;"

# 5. 重启服务
sudo systemctl restart postgresql
openclaw gateway restart
```

### 6.2 安全事件

```bash
# 1. 立即停止服务
openclaw gateway stop
openclaw agent stop

# 2. 通知安全团队
# 3. 收集日志和证据
# 4. 评估影响范围
# 5. 修复漏洞
# 6. 恢复服务
# 7. 事后复盘
```

---

## 7. 参考文档

- `docs/productization/feishu-staging-runbook.md` - Staging 流程
- `docs/productization/deployment-runbook.md` - 部署步骤
- `docs/productization/monitoring-design.md` - 监控方案
- `docs/productization/productized-live-architecture.md` - 架构图
