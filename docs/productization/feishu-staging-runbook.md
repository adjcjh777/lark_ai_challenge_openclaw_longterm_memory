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

# 如果要验证非 @ 群消息，先在已启用群策略的测试群发送一条普通文本，不要 @Bot；
# 再把 lark-cli/OpenClaw 捕获的 NDJSON/JSON 事件日志传给 gate。
python3 scripts/check_feishu_passive_message_event_gate.py --event-log /path/to/feishu-events.ndjson --json

# 重启 websocket
# 当前 OpenClaw-native 主线只重启 OpenClaw gateway；不要再启动 repo 内
# start_copilot_feishu_live.sh 或直接 lark-cli event +subscribe，
# 否则会和 OpenClaw websocket 形成双 listener。
openclaw channels restart feishu
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket

# 验证恢复
# 在飞书测试群发送 @Bot /health
```

**需要停机重启**：websocket 断开需要重新建立连接。

### 3.3.1 非 @ 群消息只看到 reaction

**症状**：测试群里发送普通非 `@Bot` 文本后，Copilot / OpenClaw 日志只看到 reaction 事件，没有看到 `im.message.receive_v1` 的 group text message。

**影响**：
- passive 静默筛选代码不会被真实触发。
- 本地单测通过也不能证明真实 Feishu 非 @ 群消息 live 投递完成。

**诊断操作**：
```bash
python3 scripts/check_feishu_passive_message_event_gate.py --event-log /path/to/feishu-events.ndjson --json
```

通过标准：
- `ok=true`
- `summary.passive_group_text_messages >= 1`
- `reason=passive_group_message_seen`

失败含义：
- `reaction_only_no_passive_message_event`：当前捕获只证明 reaction 事件可达，应检查 Feishu app 事件订阅和普通群消息权限。
- `only_at_mention_group_messages_seen`：当前只证明 @Bot 群消息可达，需要重新发送不 @Bot 的普通群文本。
- `expected_chat_not_seen`：日志来源或测试群 chat id 不匹配。

这个 gate 只证明捕获到的事件形态，不等于生产长期运行，也不替代单监听检查。

### 3.3.2 统一 live evidence 采集预检

在下一次真实 Feishu / OpenClaw 采证前，先生成一次预检清单：

```bash
python3 scripts/prepare_feishu_live_evidence_run.py \
  --planned-listener openclaw-websocket \
  --controlled-chat-id <受控测试群 chat_id> \
  --non-reviewer-open-id <第二个真实非 reviewer open_id> \
  --reviewer-open-id <reviewer open_id> \
  --create-dirs \
  --json
```

输出里的 `evidence_checklist` 会把每个未完成项映射到具体证据文件和 gate 命令：

- 非 `@Bot` 群消息投递：`check_feishu_passive_message_event_gate.py`
- first-class `fmc_memory_search` / `fmc_memory_create_candidate` / `fmc_memory_prefetch` live routing：`collect_feishu_live_evidence_packet.py`
- 第二个非 reviewer 权限负例：`check_feishu_permission_negative_gate.py`
- `/review` 私聊 DM / card / update-card E2E：`check_feishu_review_delivery_gate.py`
- Cognee 长跑：`check_openclaw_feishu_productization_completion.py --cognee-long-run-evidence ...`

这个预检只生成路径、命令和防 overclaim 清单；不会发送飞书消息、不会点击卡片，也不能替代真实 live 日志。带 `--create-dirs` 时会在 run 目录写出 `operator-checklist.md`，给测试者逐项执行；如果 Feishu event subscription 因 group-message scope 缺失 fail closed，还会写出 `feishu-console-remediation.md`，单独列出 required scopes、当前 schema scopes 和后台修复步骤；预检输出里的 completion audit 步骤会带 `--output <run-dir>/completion-audit.json`；即使审计仍是 `goal_complete=false`，也会保留完整 JSON 供 handoff 和证据包归档。

如果 OpenClaw 插件诊断暂时卡住，但只想先生成离线采证清单，可以追加：

```bash
python3 scripts/prepare_feishu_live_evidence_run.py \
  --planned-listener openclaw-websocket \
  --skip-event-diagnostics \
  --json
```

这种模式会保持 `ready_to_capture_live_logs=false`，只能用于准备路径和 checklist；正式发送真实消息前必须重新跑通过事件订阅诊断。已有诊断 JSON 时可用 `--event-diagnostics-file <path>` 复用，避免重复探测。

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
