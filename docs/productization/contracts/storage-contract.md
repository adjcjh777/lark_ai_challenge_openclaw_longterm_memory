# Storage Contract：Feishu Memory Copilot Phase 1

日期：2026-05-07
状态：Phase A 已实现本地 SQLite 兼容迁移和 audit table；后期打磨 P1 已补 dry-run / apply 迁移入口、索引检查、上线试点存储方案和 Feishu 群/用户/消息图谱拓扑本地底座；仍不是生产级多租户后台。
适用范围：后续实现 `memory_engine/db.py`、`memory_engine/copilot/schemas.py`、`memory_engine/copilot/service.py`、repository adapter 和 benchmark fixture 时必须遵循。

## 1. 目标

本契约把当前 scope-first 存储模型升级为 tenant / organization / visibility-aware 的产品模型。Phase A 已把字段、索引、迁移兼容和 `memory_audit_events` 落到本地 SQLite；后期打磨 P1 已新增 `scripts/migrate_copilot_storage.py` 和 healthcheck index/audit status。后续生产化仍需真实部署、长期监控和更完整的多租户后台。

当前历史差距：

- `memory_engine/db.py` 里的 `raw_events` 和 `memories` 只有 `scope_type` / `scope_id`，没有 `tenant_id`、`organization_id`、`visibility_policy`。
- `memory_versions` 和 `memory_evidence` 不能独立表达来源组织、可见性、actor 或撤权状态。
- 当前没有 audit 表，无法追踪 permission allow/deny、confirm/reject 和 ingestion gate。
- 当前没有图谱节点表，无法把同企业下不同飞书群、群内消息事件和用户跨群关系建模成可发现、可审计的上下文拓扑。

2026-04-28 Phase A 补充：

- `raw_events`、`memories`、`memory_versions`、`memory_evidence` 已有 `tenant_id`、`organization_id`、`visibility_policy` 兼容字段。
- 已新增 `memory_audit_events`。
- `python3 scripts/check_copilot_health.py --json` 中 `storage_schema.status=pass`、`audit_smoke.status=pass`。

2026-04-28 后期打磨 P1 补充：

- 已新增 `memory_engine/storage_migration.py` 和 `scripts/migrate_copilot_storage.py`，支持 dry-run / apply / JSON 输出。
- `python3 scripts/check_copilot_health.py --json` 中 `storage_schema.index_status.status=pass`、`storage_schema.audit_status.status=pass`。
- 当前默认 SQLite 仍只作为 demo / pre-production / 本机 staging；上线试点建议托管 PostgreSQL，但本阶段未部署生产 DB。

2026-04-29 群/用户/消息图谱拓扑补充：

- 已新增 `knowledge_graph_nodes` 和 `knowledge_graph_edges`，用于把同企业下的 Feishu 群登记为 `feishu_chat` 节点，并建立 organization -> chat 边。
- Feishu live 入口会在 allowlist 判断前登记群节点；未授权群只写最小元数据，不写消息正文、不创建 candidate。
- allowlist 通过且消息可处理后，会登记 `feishu_user` 和 `feishu_message` 节点，并建立 user -> chat、user -> message、chat -> message 边。
- 同一 tenant/org 下同一个 Feishu actor ID 只对应一个 `feishu_user` 节点；其不同群上下文由 `member_of_feishu_chat` 边表达，不复制成多个“群内用户”节点。
- 消息正文不写入 `knowledge_graph_nodes.metadata_json`。授权消息正文只在 allowlist、permission 和 candidate gate 通过后进入 `raw_events.content`、candidate/evidence quote。
- SQLite `SCHEMA_VERSION` 升为 `4`；新增 `tenant_admin_policies` 用于本地/pre-production tenant policy editor。这仍是本地/pre-production 存储演进，不等于生产图谱服务或完整多租户权限后台。

## 2. Scope / Tenant 语义

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `tenant_id` | string | 是 | 飞书租户或本项目本地默认租户。旧 demo 数据迁移默认 `tenant:demo`。 |
| `organization_id` | string | 是 | 企业/组织边界。旧 demo 数据迁移默认 `org:demo`。 |
| `workspace_id` | string | 否 | 项目空间或工作区；可由旧 `scope_id` 映射。 |
| `scope_type` | string | 是 | 兼容旧模型：project/chat/doc/user 等。 |
| `scope_id` | string | 是 | 兼容旧模型的具体 scope。 |
| `visibility_policy` | enum | 是 | `private`、`team`、`organization`、`tenant`、`public_demo`。旧 demo 默认 `team` 或 `public_demo`。 |

规则：

1. 新写入 memory/candidate/raw_event 必须带 `tenant_id`、`organization_id`、`visibility_policy`。
2. 旧 `scope_type/scope_id` 暂不删除，作为兼容层和 benchmark fallback。
3. 默认 recall 只返回 `status=active` 且 permission decision allow 的 memory。
4. `visibility_policy=public_demo` 只允许 seed/demo/replay 数据使用，真实飞书 ingestion 不得使用。

## 3. 表结构契约

### 3.1 raw_events

新增或等价表达：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `tenant_id` | text | 是 | 来源租户。 |
| `organization_id` | text | 是 | 来源组织。 |
| `workspace_id` | text | 否 | 来源项目空间。 |
| `visibility_policy` | text | 是 | 来源事件可见性。 |
| `source_url` | text | 否 | 飞书消息/文档/Bitable 行链接。 |
| `source_deleted_at` | integer | 否 | 来源删除或撤权时间。 |
| `ingestion_status` | text | 是 | `raw`、`candidate_created`、`blocked`、`ignored`。 |

### 3.2 memory_candidates

Phase 1 建议新增候选表，或在现有 memories 中用 `status=candidate` 兼容，但产品契约必须包含：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `candidate_id` | text | 是 | 候选 ID。 |
| `tenant_id` | text | 是 | 权限边界。 |
| `organization_id` | text | 是 | 权限边界。 |
| `workspace_id` | text | 否 | 项目空间。 |
| `scope_type` / `scope_id` | text | 是 | 兼容旧 scope。 |
| `visibility_policy` | text | 是 | 候选可见性。 |
| `source_type` | text | 是 | message/doc/bitable/manual/benchmark。 |
| `source_id` | text | 是 | 来源 ID。 |
| `source_url` | text | 否 | 可追溯链接。 |
| `suggested_subject` | text | 是 | 建议主题。 |
| `suggested_value` | text | 是 | 建议记忆值。 |
| `confidence` | real | 是 | 候选置信度。 |
| `status` | text | 是 | `candidate`、`confirmed`、`rejected`、`blocked`。 |
| `review_required` | boolean | 是 | 真实飞书来源默认 true。 |
| `review_reason` | text | 否 | 为什么需要审核。 |
| `created_by` | text | 是 | actor ID。 |
| `created_at` | integer | 是 | 创建时间。 |

### 3.3 memories

现有 `memories` 表需保留旧字段并新增：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `tenant_id` | text | 是 | 权限边界。 |
| `organization_id` | text | 是 | 权限边界。 |
| `workspace_id` | text | 否 | 项目空间。 |
| `visibility_policy` | text | 是 | active memory 可见性。 |
| `summary` | text | 否 | 用于 curated embedding 和 compact display。 |
| `owner_id` | text | 否 | MVP 默认等同 `created_by`；后续如引入 ACL，可独立于创建人。 |
| `created_by` | text | 否 | 创建 actor。 |
| `updated_by` | text | 否 | 最近更新 actor。 |
| `schema_version` | integer | 是 | 当前存储 schema version。 |
| `source_visibility_revoked_at` | integer | 否 | 来源撤权时间。 |

唯一约束建议从：

```text
UNIQUE(scope_type, scope_id, type, normalized_subject)
```

升级为：

```text
UNIQUE(tenant_id, organization_id, scope_type, scope_id, type, normalized_subject)
```

### 3.4 memory_versions

新增或等价表达：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `tenant_id` | text | 是 | 冗余边界，便于 audit 和版本解释过滤。 |
| `organization_id` | text | 是 | 冗余边界。 |
| `visibility_policy` | text | 是 | 旧版本可见性。 |
| `decision_reason` | text | 否 | confirm/supersede/reject 原因。 |
| `permission_snapshot` | text/json | 否 | 创建版本时的权限摘要，不存 token。 |

### 3.5 memory_evidence

新增或等价表达：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `tenant_id` | text | 是 | evidence 权限边界。 |
| `organization_id` | text | 是 | evidence 权限边界。 |
| `visibility_policy` | text | 是 | evidence 可见性。 |
| `source_type` | text | 是 | message/doc/bitable/manual/benchmark；保留旧字段，供索引和追溯使用。 |
| `source_event_id` | text | 是 | 来源事件 ID；旧表已有字段，后续不得与 `source_id` 混用。 |
| `source_url` | text | 否 | 来源链接。 |
| `quote` | text | 是 | evidence 原文片段；输出前必须经过 permission / redaction。 |
| `actor_id` | text | 否 | 来源 actor。 |
| `actor_display` | text | 否 | 展示名，禁止作为权限依据。 |
| `event_time` | integer | 否 | 来源事件时间。 |
| `ingested_at` | integer | 是 | 摄取时间。 |
| `source_deleted_at` | integer | 否 | 来源删除/撤权时间。 |
| `redaction_state` | text | 是 | `none`、`redacted`、`withheld`。 |

### 3.6 memory_audit_events

Phase 1 必须新增审计事件契约。后续实现可先写 SQLite 表或结构化日志，但字段必须稳定：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `audit_id` | text | 是 | 审计 ID。 |
| `request_id` | text | 是 | 调用请求 ID。 |
| `trace_id` | text | 是 | 链路 ID。 |
| `actor_id` | text | 是 | 操作者。 |
| `actor_roles` | text/json | 是 | 操作者角色列表；SQLite 可用 JSON text 存储。 |
| `tenant_id` | text | 是 | 请求租户。 |
| `organization_id` | text | 是 | 请求组织。 |
| `action` | text | 是 | `memory.search` 等动作。 |
| `target_type` | text | 是 | memory/candidate/evidence/reminder。 |
| `target_id` | text | 否 | 目标 ID，可为空。 |
| `permission_decision` | text | 是 | allow/deny/redact/withhold。 |
| `reason_code` | text | 是 | 机器可读原因。 |
| `visible_fields` | text/json | 是 | 允许输出的字段名，用于证明 allow path 的字段边界。 |
| `redacted_fields` | text/json | 是 | 被遮挡字段名，不存明文 secret。 |
| `source_context` | text/json | 是 | entrypoint/chat/doc/workspace。 |
| `created_at` | integer | 是 | 审计时间。 |

### 3.7 knowledge_graph_nodes / knowledge_graph_edges

用于记录企业内可发现的上下文节点。当前权威图谱账本只落本地 SQLite，服务于 Feishu 群节点发现、用户跨群关系、授权消息事件拓扑和后续 Cognee/图谱同步；Cognee 当前只是 curated memory recall/sync channel，不是这些拓扑关系的事实源。不直接把 raw message 向量化或自动 active。

`knowledge_graph_nodes`：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | text | 是 | 节点 ID。 |
| `tenant_id` | text | 是 | 租户边界。 |
| `organization_id` | text | 是 | 企业/组织边界。 |
| `node_type` | text | 是 | 当前支持 `organization`、`feishu_chat`、`feishu_user`、`feishu_message`。 |
| `node_key` | text | 是 | 外部稳定 ID；Feishu 群为 chat_id，用户为 open_id/user_id，消息为 message_id。 |
| `label` | text | 是 | 脱敏可读标签；不承诺为飞书群名。 |
| `visibility_policy` | text | 是 | 节点默认可见性。 |
| `status` | text | 是 | `discovered`、`active` 等；未在 allowlist 的群为 `discovered`。 |
| `metadata_json` | text/json | 是 | entrypoint、scope、chat_type、last_message_id、content_policy 等最小元数据；`feishu_message` 节点不得存消息正文。 |
| `first_seen_at` / `last_seen_at` | integer | 是 | 发现和最近观测时间。 |
| `observation_count` | integer | 是 | 观测次数。 |

`knowledge_graph_edges`：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | text | 是 | 边 ID。 |
| `tenant_id` | text | 是 | 租户边界。 |
| `organization_id` | text | 是 | 企业/组织边界。 |
| `source_node_id` | text | 是 | 起点节点。 |
| `target_node_id` | text | 是 | 终点节点。 |
| `edge_type` | text | 是 | 当前支持 `contains_feishu_chat`、`member_of_feishu_chat`、`sent_feishu_message`、`contains_feishu_message`。 |
| `metadata_json` | text/json | 是 | entrypoint、scope、chat_type 等最小元数据。 |
| `first_seen_at` / `last_seen_at` | integer | 是 | 发现和最近观测时间。 |
| `observation_count` | integer | 是 | 观测次数。 |

## 4. 索引契约

后续迁移至少补充：

```sql
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

CREATE INDEX idx_kg_nodes_tenant_org_type_key
  ON knowledge_graph_nodes(tenant_id, organization_id, node_type, node_key);

CREATE INDEX idx_kg_edges_tenant_org_type
  ON knowledge_graph_edges(tenant_id, organization_id, edge_type);
```

## 5. Acceptance Criteria

- 新写入数据必须带 tenant/org/visibility。
- 旧 demo/benchmark 数据有默认 tenant/org/visibility，并保持旧 benchmark 可跑。
- 默认 search 不返回 unauthorized、stale、superseded、rejected、archived 内容。
- 版本解释和 evidence 输出必须经过 permission decision。
- 审计事件不记录 token、secret、raw private memory。
- 新 Feishu 群在 allowlist 判断前可登记为图谱节点；未授权群不得记录消息正文或创建 candidate。
- 未授权群不得创建 `feishu_user` 或 `feishu_message` 节点。
- 授权群消息可创建 `feishu_message` 节点，但节点 metadata 必须只存事件拓扑元数据和 `raw_text_not_stored_in_graph_node` 策略标记。
- 同一 tenant/org 下同一用户跨多个群只保留一个 `feishu_user` 节点，群差异由边表达。

---

## 6. 生产 DB 选型：SQLite -> PostgreSQL 迁移方案

日期：2026-04-28
状态：方案设计（未完成生产上线）

### 6.1 选型理由

| 维度 | SQLite | PostgreSQL | 说明 |
|------|--------|------------|------|
| 并发 | 单写多读 | 多写多读 | 生产需要并发写入 |
| 性能 | 受限于本地 I/O | 支持连接池、并行查询 | 生产需要高性能 |
| 可靠性 | 文件级备份 | WAL + 定时备份 | 生产需要高可靠 |
| 扩展性 | 单机 | 支持主从复制 | 生产需要可扩展 |
| 运维 | 无 | 成熟工具链 | 生产需要可运维 |

**结论**：生产环境必须迁移到 PostgreSQL。

### 6.2 托管 vs 自建

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **托管 PostgreSQL**（推荐） | 免运维、高可用、自动备份 | 成本高、定制性低 | 生产环境 |
| **自建 PostgreSQL** | 成本低、定制性高 | 运维复杂、需要专人维护 | 预算有限 |

**推荐方案**：托管 PostgreSQL（如 AWS RDS、阿里云 RDS、腾讯云 TDSQL）

### 6.3 迁移步骤

#### 6.3.1 准备阶段

```bash
# 1. 创建 PostgreSQL 数据库
# 使用托管服务或自建

# 2. 安装迁移工具
pip install psycopg2-binary alembic

# 3. 配置环境变量
export DATABASE_URL=postgresql://user:password@host:5432/memory_copilot
```

#### 6.3.2 Schema 迁移

```bash
# 1. 导出当前 SQLite schema
sqlite3 data/memory.sqlite ".schema" > schema.sql

# 2. 转换为 PostgreSQL 兼容格式
# 手动或使用工具转换数据类型

# 3. 执行 PostgreSQL 迁移
psql -U memory_copilot -d memory_copilot -f schema_postgresql.sql

# 4. 验证迁移
python3 scripts/migrate_copilot_storage.py --dry-run --json
```

#### 6.3.3 数据迁移

```bash
# 1. 导出 SQLite 数据
sqlite3 data/memory.sqlite ".dump" > data_dump.sql

# 2. 转换数据格式
# 使用脚本转换 SQLite 特定语法

# 3. 导入 PostgreSQL
psql -U memory_copilot -d memory_copilot < data_dump_converted.sql

# 4. 验证数据
psql -U memory_copilot -d memory_copilot -c "SELECT COUNT(*) FROM memories;"
```

#### 6.3.4 索引迁移

```sql
-- 执行索引创建
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
```

#### 6.3.5 验证阶段

```bash
# 1. 运行健康检查
python3 scripts/check_copilot_health.py --json

# 2. 运行测试
python3 -m pytest tests/ -v

# 3. 运行 benchmark
python3 -m memory_engine benchmark run benchmarks/day1_cases.json

# 4. 验证审计
python3 scripts/query_audit_events.py --summary --json
```

### 6.4 回滚方案

```bash
# 1. 停止服务
openclaw gateway stop
openclaw agent stop

# 2. 切换回 SQLite
export DATABASE_URL=sqlite:///data/memory.sqlite

# 3. 重启服务
openclaw gateway start --daemon
openclaw agent start --agent main --daemon

# 4. 验证
python3 scripts/check_copilot_health.py --json
```

### 6.5 迁移检查清单

- [ ] PostgreSQL 数据库创建完成
- [ ] Schema 迁移完成
- [ ] 数据迁移完成
- [ ] 索引创建完成
- [ ] 健康检查通过
- [ ] 测试全部通过
- [ ] Benchmark 通过
- [ ] 审计日志正常
- [ ] 回滚方案验证

### 6.6 迁移时间窗口

| 阶段 | 预计时间 | 说明 |
|------|----------|------|
| 准备 | 2 小时 | 环境准备、工具安装 |
| Schema 迁移 | 1 小时 | 创建表和索引 |
| 数据迁移 | 2 小时 | 导出、转换、导入 |
| 验证 | 2 小时 | 测试、benchmark |
| 监控 | 24 小时 | 观察生产运行 |
| **总计** | **约 31 小时** | 含监控 |

### 6.7 风险和注意事项

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 数据丢失 | 高 | 完整备份 + 验证 |
| 迁移失败 | 中 | 回滚方案 |
| 性能下降 | 中 | 索引优化 + 监控 |
| 应用兼容性 | 低 | 充分测试 |

### 6.8 参考文档

- `docs/productization/productized-live-architecture.md` - 架构图
- `docs/productization/deployment-runbook.md` - 部署步骤
- `docs/productization/contracts/migration-rfc.md` - 迁移 RFC
