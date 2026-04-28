# Storage Contract：Feishu Memory Copilot Phase 1

日期：2026-05-07
状态：Phase A 已实现本地 SQLite 兼容迁移和 audit table；后期打磨 P1 已补 dry-run / apply 迁移入口、索引检查和上线试点存储方案；仍不是生产级多租户后台。
适用范围：后续实现 `memory_engine/db.py`、`memory_engine/copilot/schemas.py`、`memory_engine/copilot/service.py`、repository adapter 和 benchmark fixture 时必须遵循。

## 1. 目标

本契约把当前 scope-first 存储模型升级为 tenant / organization / visibility-aware 的产品模型。Phase A 已把字段、索引、迁移兼容和 `memory_audit_events` 落到本地 SQLite；后期打磨 P1 已新增 `scripts/migrate_copilot_storage.py` 和 healthcheck index/audit status。后续生产化仍需真实部署、长期监控和更完整的多租户后台。

当前历史差距：

- `memory_engine/db.py` 里的 `raw_events` 和 `memories` 只有 `scope_type` / `scope_id`，没有 `tenant_id`、`organization_id`、`visibility_policy`。
- `memory_versions` 和 `memory_evidence` 不能独立表达来源组织、可见性、actor 或撤权状态。
- 当前没有 audit 表，无法追踪 permission allow/deny、confirm/reject 和 ingestion gate。

2026-04-28 Phase A 补充：

- `raw_events`、`memories`、`memory_versions`、`memory_evidence` 已有 `tenant_id`、`organization_id`、`visibility_policy` 兼容字段。
- 已新增 `memory_audit_events`。
- `python3 scripts/check_copilot_health.py --json` 中 `storage_schema.status=pass`、`audit_smoke.status=pass`。

2026-04-28 后期打磨 P1 补充：

- 已新增 `memory_engine/storage_migration.py` 和 `scripts/migrate_copilot_storage.py`，支持 dry-run / apply / JSON 输出。
- `python3 scripts/check_copilot_health.py --json` 中 `storage_schema.index_status.status=pass`、`storage_schema.audit_status.status=pass`。
- 当前默认 SQLite 仍只作为 demo / pre-production / 本机 staging；上线试点建议托管 PostgreSQL，但本阶段未部署生产 DB。

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
```

## 5. Acceptance Criteria

- 新写入数据必须带 tenant/org/visibility。
- 旧 demo/benchmark 数据有默认 tenant/org/visibility，并保持旧 benchmark 可跑。
- 默认 search 不返回 unauthorized、stale、superseded、rejected、archived 内容。
- 版本解释和 evidence 输出必须经过 permission decision。
- 审计事件不记录 token、secret、raw private memory。
