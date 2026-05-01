# Feishu Memory Copilot - 部署步骤文档

日期：2026-04-28
状态：方案设计（未完成生产上线）
适用范围：从零到可运行的完整部署步骤，新机器可按文档部署

> 2026-05-01 校准：本文是 productized live 部署草案，不是当前已验证 runbook。文中 `scripts/validate_env.py`、`requirements.txt` 等命令或文件在当前仓库未实现或未作为验收入口；SQLite staging 备份/校验/恢复已落成 `scripts/backup_copilot_storage.py`，但 PostgreSQL 生产备份、PITR 和托管数据库部署仍未实施。实施前以 [productized-live-long-run-plan.md](productized-live-long-run-plan.md) 的 gate 为准，逐条校准命令后再执行。

---

## 1. 前置条件

### 1.1 硬件要求

| 环境 | CPU | 内存 | 存储 | 说明 |
|------|-----|------|------|------|
| 开发/测试 | 4 核 | 8 GB | 50 GB SSD | 单节点部署 |
| 生产 | 8 核 | 16 GB | 200 GB SSD | 最小配置 |
| 生产（推荐） | 16 核 | 32 GB | 500 GB SSD | 含 Ollama |

### 1.2 软件要求

| 软件 | 版本 | 说明 |
|------|------|------|
| Python | 3.11+ | 运行时 |
| PostgreSQL | 15+ | 生产数据库 |
| OpenClaw | 2026.4.24 | Agent Gateway |
| Ollama | 最新 | Embedding 服务 |
| Docker | 24+ | 容器化部署（可选） |
| Git | 2.40+ | 版本控制 |

### 1.3 网络要求

| 端口 | 用途 | 方向 |
|------|------|------|
| 443 | OpenClaw Gateway (HTTPS/WSS) | 入站 |
| 5432 | PostgreSQL | 内网 |
| 11434 | Ollama | 内网 |
| 8080 | Cognee | 内网（可选） |

---

## 2. 环境变量配置

### 2.1 必需环境变量

```bash
# 飞书应用配置
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_app_secret
FEISHU_ENCRYPT_KEY=your_encrypt_key
FEISHU_VERIFICATION_TOKEN=your_verification_token

# OpenClaw 配置
OPENCLAW_VERSION=2026.4.24

# PostgreSQL 配置（生产）
DATABASE_URL=postgresql://user:password@localhost:5432/memory_copilot
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20

# Ollama 配置
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDING_MODEL=qwen3-embedding:0.6b-fp16

# 日志配置
LOG_LEVEL=INFO
LOG_DIR=/var/log/memory-copilot

# 安全配置
SECRET_KEY=your-secret-key
ALLOWED_ORIGINS=https://your-domain.com
```

### 2.2 可选环境变量

```bash
# Cognee 配置（可选）
COGNEE_API_URL=http://localhost:8080
COGNEE_API_KEY=your_cognee_api_key

# 监控配置
PROMETHEUS_PORT=9090
SENTRY_DSN=your_sentry_dsn

# 邮件告警配置
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=alerts@example.com
SMTP_PASSWORD=your_smtp_password
ALERT_EMAIL=ops-team@example.com
```

### 2.3 环境变量文件

```bash
# 复制模板
cp .env.example .env

# 编辑配置
vim .env

# 验证配置
python3 scripts/validate_env.py
```

---

## 3. 数据库部署

### 3.1 PostgreSQL 安装

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install postgresql postgresql-contrib

# macOS
brew install postgresql@15

# 启动服务
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### 3.2 创建数据库和用户

```bash
# 登录 PostgreSQL
sudo -u postgres psql

# 创建用户
CREATE USER memory_copilot WITH PASSWORD 'your_secure_password';

# 创建数据库
CREATE DATABASE memory_copilot OWNER memory_copilot;

# 授权
GRANT ALL PRIVILEGES ON DATABASE memory_copilot TO memory_copilot;

# 退出
\q
```

### 3.3 初始化 Schema

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行迁移
python3 scripts/migrate_copilot_storage.py --apply --json

# 验证迁移
python3 scripts/check_copilot_health.py --json | jq '.checks.storage_schema'
```

### 3.4 索引创建

```sql
-- 连接数据库
psql -U memory_copilot -d memory_copilot

-- 创建索引
CREATE INDEX idx_memories_tenant_org_scope_status
  ON memories(tenant_id, organization_id, scope_type, scope_id, status);

CREATE INDEX idx_memories_visibility_status
  ON memories(tenant_id, organization_id, visibility_policy, status);

CREATE INDEX idx_candidates_review_status
  ON memory_candidates(tenant_id, organization_id, status, review_required);

CREATE INDEX idx_evidence_source
  ON memory_evidence(tenant_id, organization_id, source_type, source_event_id);

CREATE INDEX idx_audit_request_trace
  ON memory_audit_events(request_id, trace_id);

CREATE INDEX idx_audit_created_at
  ON memory_audit_events(created_at);

-- 退出
\q
```

---

## 4. 应用部署

### 4.1 克隆代码

```bash
# 克隆仓库
git clone https://github.com/your-org/feishu-memory-copilot.git
cd feishu-memory-copilot

# 切换到稳定版本
git checkout main
git pull origin main
```

### 4.2 创建虚拟环境

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活
source venv/bin/activate

# 安装依赖
pip install --upgrade pip
pip install -r requirements.txt

# 安装项目
pip install -e .
```

### 4.3 配置环境

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑配置（按 2.1 节填写）
vim .env

# 验证配置
python3 scripts/validate_env.py
```

### 4.4 验证安装

```bash
# 编译检查
python3 -m compileall memory_engine scripts

# 运行测试
python3 -m pytest tests/ -v

# 健康检查
python3 scripts/check_copilot_health.py --json

# OpenClaw 版本检查
python3 scripts/check_openclaw_version.py
```

---

## 5. OpenClaw 部署

### 5.1 安装 OpenClaw

```bash
# 安装 OpenClaw（版本 2026.4.24）
pip install openclaw==2026.4.24

# 验证安装
openclaw --version
```

### 5.2 配置 OpenClaw

```bash
# 初始化配置
openclaw init

# 配置飞书通道
openclaw channels add feishu \
  --app-id $FEISHU_APP_ID \
  --app-secret $FEISHU_APP_SECRET \
  --encrypt-key $FEISHU_ENCRYPT_KEY \
  --verification-token $FEISHU_VERIFICATION_TOKEN
```

### 5.3 注册插件

```bash
# 安装 feishu-memory-copilot 插件
openclaw plugins install agent_adapters/openclaw/plugin/

# 验证插件
openclaw plugins inspect feishu-memory-copilot --json
```

### 5.4 启动 OpenClaw

```bash
# 启动 Gateway
openclaw gateway start --daemon

# 启动 Agent
openclaw agent start --agent main --daemon

# 检查状态
openclaw health --json
openclaw channels status --probe --json
```

---

## 6. Ollama 部署

### 6.1 安装 Ollama

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# 启动服务
ollama serve &
```

### 6.2 拉取模型

```bash
# 拉取 embedding 模型
ollama pull qwen3-embedding:0.6b-fp16

# 验证模型
ollama list
```

### 6.3 验证 Embedding

```bash
# 运行 live embedding gate
python3 scripts/check_live_embedding_gate.py --json

# 运行 embedding provider 检查
python3 scripts/check_embedding_provider.py --live
```

---

## 7. Cognee 部署（可选）

### 7.1 安装 Cognee

```bash
# 参考 Cognee 官方文档安装
# https://docs.cognee.ai

# 配置环境变量
export COGNEE_API_URL=http://localhost:8080
export COGNEE_API_KEY=your_api_key
```

### 7.2 验证 Cognee

```bash
# 运行 Cognee 验证
python3 scripts/spike_cognee_local.py --dry-run

# 检查配置
python3 -c "from memory_engine.copilot.cognee_adapter import _validate_cognee_configuration; _validate_cognee_configuration()"
```

---

## 8. 服务启动

### 8.1 启动顺序

```bash
# 1. 启动 PostgreSQL（如果不是系统服务）
sudo systemctl start postgresql

# 2. 启动 Ollama
ollama serve &

# 3. 启动 Cognee（可选）
# 参考 Cognee 文档

# 4. 启动 OpenClaw
openclaw gateway start --daemon
openclaw agent start --agent main --daemon

# 5. 启动 Copilot Listener（如果使用 lark-cli）
bash scripts/start_copilot_feishu_live.sh
```

### 8.2 验证服务

```bash
# 完整健康检查
python3 scripts/check_copilot_health.py --json

# 审计告警检查
python3 scripts/check_audit_alerts.py --json

# OpenClaw 状态
openclaw health --json
openclaw channels status --probe --json

# Ollama 状态
ollama ps
```

### 8.3 单监听验证

```bash
# 确保只有一个监听入口
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
```

---

## 9. 回滚流程

### 9.1 代码回滚

```bash
# 1. 停止服务
openclaw gateway stop
openclaw agent stop

# 2. 回滚代码
git log --oneline -10  # 查看历史版本
git checkout <previous-commit-hash>

# 3. 重新安装依赖
pip install -r requirements.txt

# 4. 验证
python3 scripts/check_copilot_health.py --json

# 5. 重启服务
openclaw gateway start --daemon
openclaw agent start --agent main --daemon
```

### 9.2 数据库回滚

```bash
# 1. 停止服务
openclaw gateway stop
openclaw agent stop

# 2. 从备份恢复
pg_restore -U memory_copilot -d memory_copilot /path/to/backup.dump

# 或者使用备份文件
psql -U memory_copilot -d memory_copilot < /path/to/backup.sql

# 3. 重启服务
openclaw gateway start --daemon
openclaw agent start --agent main --daemon
```

### 9.3 完整回滚

```bash
# 1. 停止所有服务
pkill -f "openclaw\|ollama\|copilot"

# 2. 恢复数据库
pg_restore -U memory_copilot -d memory_copilot /path/to/backup.dump

# 3. 回滚代码
git checkout <previous-commit-hash>

# 4. 重新安装
pip install -r requirements.txt

# 5. 重启服务
sudo systemctl start postgresql
ollama serve &
openclaw gateway start --daemon
openclaw agent start --agent main --daemon
```

---

## 10. 数据备份

### 10.1 备份策略

| 备份类型 | 频率 | 保留周期 | 说明 |
|----------|------|----------|------|
| 全量备份 | 每日 02:00 | 30 天 | PostgreSQL pg_dump |
| WAL 归档 | 实时 | 7 天 | 增量备份 |
| 配置备份 | 每次变更 | 永久 | .env, 配置文件 |
| 代码备份 | 每次 push | 永久 | Git |

### 10.2 SQLite staging 备份脚本

当前仓库已实现本地 / staging SQLite backup / verify / restore drill：

```bash
python3 scripts/backup_copilot_storage.py \
  --db-path data/memory.sqlite \
  --backup-dir data/backups \
  --json
```

校验已有备份：

```bash
python3 scripts/backup_copilot_storage.py \
  --verify-backup data/backups/<backup>.sqlite \
  --json
```

恢复到新路径或停写后的目标路径：

```bash
python3 scripts/backup_copilot_storage.py \
  --restore-backup data/backups/<backup>.sqlite \
  --restore-to data/memory.restored.sqlite \
  --json
```

如果要覆盖现有 SQLite，必须先停止 Feishu/OpenClaw 写入入口，再显式加 `--force`。这个脚本会运行 `PRAGMA integrity_check`、检查 Copilot schema/index/audit readiness，并写 `.manifest.json`。它不是 PostgreSQL 生产备份、PITR 或 productized live 证明。

### 10.3 PostgreSQL 生产备份草案

```bash
#!/bin/bash
# scripts/backup_database.sh

BACKUP_DIR="/var/backups/memory-copilot"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/memory_copilot_$DATE.dump"

# 创建备份目录
mkdir -p $BACKUP_DIR

# 执行备份
pg_dump -U memory_copilot -d memory_copilot -Fc -f $BACKUP_FILE

# 清理 30 天前的备份
find $BACKUP_DIR -name "*.dump" -mtime +30 -delete

echo "Backup completed: $BACKUP_FILE"
```

### 10.4 PostgreSQL 恢复测试草案

```bash
# 恢复到测试数据库
pg_restore -U memory_copilot -d memory_copilot_test /path/to/backup.dump

# 验证数据
psql -U memory_copilot -d memory_copilot_test -c "SELECT COUNT(*) FROM memories;"
```

---

## 11. 环境变量清单

### 11.1 必需变量

| 变量名 | 说明 | 示例 |
|--------|------|------|
| FEISHU_APP_ID | 飞书应用 ID | cli_xxxxx |
| FEISHU_APP_SECRET | 飞书应用密钥 | xxxxx |
| FEISHU_ENCRYPT_KEY | 飞书加密密钥 | xxxxx |
| FEISHU_VERIFICATION_TOKEN | 飞书验证 token | xxxxx |
| DATABASE_URL | PostgreSQL 连接串 | postgresql://user:pass@host:5432/db |
| OLLAMA_BASE_URL | Ollama 服务地址 | http://localhost:11434 |
| EMBEDDING_MODEL | Embedding 模型名 | qwen3-embedding:0.6b-fp16 |
| SECRET_KEY | 应用密钥 | 随机生成 |

### 11.2 可选变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| DATABASE_POOL_SIZE | 连接池大小 | 10 |
| DATABASE_MAX_OVERFLOW | 最大溢出连接 | 20 |
| LOG_LEVEL | 日志级别 | INFO |
| LOG_DIR | 日志目录 | logs/ |
| COGNEE_API_URL | Cognee 地址 | http://localhost:8080 |
| PROMETHEUS_PORT | Prometheus 端口 | 9090 |
| SENTRY_DSN | Sentry DSN | 空 |

---

## 12. 部署验证清单

### 12.1 基础验证

- [ ] PostgreSQL 连接正常
- [ ] Ollama 服务运行
- [ ] Embedding 模型可用
- [ ] OpenClaw 版本正确 (2026.4.24)
- [ ] 插件注册成功

### 12.2 功能验证

- [ ] memory.search 正常
- [ ] memory.create_candidate 正常
- [ ] memory.confirm/reject 正常
- [ ] memory.explain_versions 正常
- [ ] memory.prefetch 正常
- [ ] Permission fail-closed 验证

### 12.3 运维验证

- [ ] 健康检查通过
- [ ] 审计日志正常
- [ ] 备份脚本运行
- [ ] 回滚流程测试

---

## 13. 常见问题

### Q1: PostgreSQL 连接失败

```bash
# 检查服务状态
sudo systemctl status postgresql

# 检查连接
psql -U memory_copilot -d memory_copilot -c "SELECT 1;"

# 检查 pg_hba.conf
sudo cat /etc/postgresql/15/main/pg_hba.conf
```

### Q2: Ollama 模型不可用

```bash
# 检查模型
ollama list

# 重新拉取
ollama pull qwen3-embedding:0.6b-fp16

# 检查服务
curl http://localhost:11434/api/tags
```

### Q3: OpenClaw 启动失败

```bash
# 检查日志
openclaw gateway logs
openclaw agent logs

# 检查配置
openclaw config show

# 重新初始化
openclaw init --force
```

---

## 14. 参考文档

- `docs/productization/productized-live-architecture.md` - 架构图
- `docs/productization/monitoring-design.md` - 监控方案
- `docs/productization/ops-runbook.md` - 运维流程
- `docs/productization/feishu-staging-runbook.md` - Staging 流程
- `docs/productization/contracts/storage-contract.md` - 存储契约
