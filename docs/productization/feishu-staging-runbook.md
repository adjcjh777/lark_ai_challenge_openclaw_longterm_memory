# Feishu Memory Copilot Staging Runbook

日期：2026-04-28
状态：Staging / Pre-production

---

## 1. 停机流程

### 1.1 正常停机

```bash
# 1. 停止 Feishu live listener
# 找到 listener 进程
ps aux | grep "copilot_feishu_live\|lark-cli.*event" | grep -v grep

# 发送 SIGTERM 优雅停止
kill -TERM <PID>

# 等待进程退出（最多 10 秒）
sleep 10

# 如果还在运行，强制停止
kill -9 <PID> 2>/dev/null

# 2. 停止 OpenClaw websocket（如果有）
ps aux | grep "openclaw" | grep -v grep
kill -TERM <PID>

# 3. 确认所有进程已停止
ps aux | grep -E "copilot|lark-cli|openclaw" | grep -v grep
# 应该无输出

# 4. 关闭数据库连接（SQLite 自动处理，无需手动操作）
```

### 1.2 紧急停机

```bash
# 强制停止所有相关进程
pkill -f "copilot_feishu_live" 2>/dev/null
pkill -f "lark-cli.*event" 2>/dev/null
pkill -f "openclaw" 2>/dev/null

# 确认停止
ps aux | grep -E "copilot|lark-cli|openclaw" | grep -v grep
```

---

## 2. 审计数据回滚

### 2.1 审计表特性

- `memory_audit_events` 表只追加不删除（append-only）
- 审计数据用于合规和复盘，不应随意删除
- SQLite 无自动清理机制，长期运行需考虑 retention 策略

### 2.2 审计数据清理（谨慎操作）

```bash
# 查看当前审计事件数量
python3 scripts/query_audit_events.py --summary --json

# 备份审计数据
cp data/memory.sqlite data/memory.sqlite.backup.$(date +%Y%m%d)

# 清理 30 天前的审计数据（需要手动执行 SQL）
sqlite3 data/memory.sqlite "
DELETE FROM memory_audit_events
WHERE created_at < strftime('%s', 'now', '-30 days') * 1000;
VACUUM;
"

# 验证清理结果
python3 scripts/query_audit_events.py --summary --json
```

### 2.3 数据库整体回滚

```bash
# 停止所有服务
pkill -f "copilot\|lark-cli\|openclaw"

# 恢复备份
cp data/memory.sqlite.backup.20260428 data/memory.sqlite

# 重启服务
python3 -m memory_engine.copilot.feishu_live
```

---

## 3. 紧急降级流程

### 3.1 Embedding 服务不可用

**症状**：`healthcheck` 中 `embedding_provider.status` 变为 `warning` 或 `not_configured`

**影响**：
- `memory.search` 降级为基于文本匹配的 retrieval
- 搜索质量下降但功能可用

**降级操作**：
```bash
# 检查 Ollama 状态
ollama list

# 重启 Ollama 服务
ollama serve &

# 拉取 embedding 模型
ollama pull qwen3-embedding:0.6b-fp16

# 验证恢复
python3 scripts/check_embedding_provider.py --live
```

**无需停机**：embedding 不可用时系统自动 fallback 到 `DeterministicEmbeddingProvider`。

### 3.2 Cognee 不可用

**症状**：`healthcheck` 中 `cognee_adapter.status` 变为 `fallback_used`

**影响**：
- `memory.confirm` 后不会同步到 Cognee graph
- `memory.reject` 后不会从 Cognee withdrawal
- 搜索仍走 repository fallback

**降级操作**：
```bash
# 检查 Cognee 配置
python3 -c "from memory_engine.copilot.cognee_adapter import _validate_cognee_configuration; _validate_cognee_configuration()"

# 修复 .env 配置
# 确保 LLM_API_KEY 和 EMBEDDING_MODEL 正确

# 验证恢复
python3 scripts/check_copilot_health.py --json | jq '.checks.cognee_adapter'
```

**无需停机**：Cognee 不可用时系统自动 fallback 到 repository-ledger 模式。

### 3.3 OpenClaw WebSocket 断开

**症状**：飞书消息不再触发 Copilot 处理

**影响**：
- 飞书群聊中的 @Bot 消息不会被处理
- Card action（confirm/reject 按钮）不会触发

**降级操作**：
```bash
# 检查 OpenClaw websocket 状态
python3 scripts/check_openclaw_feishu_websocket.py

# 重启 websocket
# 方式 1: 通过 start 脚本
bash scripts/start_copilot_feishu_live.sh

# 方式 2: 手动启动
lark-cli event +subscribe --as bot --event-types "im.message.receive_v1,card.action.trigger" --quiet

# 验证恢复
# 在飞书测试群发送 @Bot /health
```

**需要停机重启**：websocket 断开需要重新建立连接。

### 3.4 数据库损坏

**症状**：SQLite 报错 "database disk image is malformed"

**影响**：
- 所有读写操作失败

**恢复操作**：
```bash
# 停止所有服务
pkill -f "copilot\|lark-cli\|openclaw"

# 尝试修复
sqlite3 data/memory.sqlite "PRAGMA integrity_check;"

# 如果无法修复，从备份恢复
cp data/memory.sqlite.backup.latest data/memory.sqlite

# 如果没有备份，重新初始化
python3 scripts/init_db.py

# 重启服务
python3 -m memory_engine.copilot.feishu_live
```

---

## 4. 健康检查命令

```bash
# 完整健康检查
python3 scripts/check_copilot_health.py --json

# 审计告警检查
python3 scripts/check_audit_alerts.py --json

# 审计查询
python3 scripts/query_audit_events.py --summary --json

# Embedding 检查
python3 scripts/check_embedding_provider.py --live

# OpenClaw 版本检查
python3 scripts/check_openclaw_version.py

# 编译检查
python3 -m compileall memory_engine scripts
```

---

## 5. 日志位置

| 组件 | 日志位置 |
|---|---|
| Feishu live listener | `logs/feishu_live_*.log` |
| Healthcheck | stdout (通过 `check_copilot_health.py`) |
| 审计事件 | `data/memory.sqlite` → `memory_audit_events` 表 |

---

## 6. 数据库维护

### 6.1 定期备份

```bash
# 每日备份
cp data/memory.sqlite data/memory.sqlite.backup.$(date +%Y%m%d)

# 清理 7 天前的备份
find data/ -name "memory.sqlite.backup.*" -mtime +7 -delete
```

### 6.2 审计数据 retention

建议保留 90 天审计数据。超过 90 天的数据可按需清理。

```bash
# 清理 90 天前的审计数据
sqlite3 data/memory.sqlite "
DELETE FROM memory_audit_events
WHERE created_at < strftime('%s', 'now', '-90 days') * 1000;
VACUUM;
"
```
