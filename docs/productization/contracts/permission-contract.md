# Permission Contract：Feishu Memory Copilot Phase 1

日期：2026-05-07
状态：Phase 1 contract freeze 已完成；Phase 2 权限前置实现已完成（commit `b6b17b4`）；2026-04-28 后期打磨已补真实飞书权限映射本地闭环
适用范围：`memory_engine/copilot/permissions.py`、`schemas.py`、`service.py`、OpenClaw tool payload、Feishu review surface。

## 1. 目标

把当前 scope-level allowlist 升级为 tenant / organization / visibility-aware permission contract。Phase 1 冻结行为；2026-05-07 已把第一批 fail-closed 和 service-action 权限门控落到代码。

当前差距（历史快照；已部分修复）：

- 已修复：`current_context.permission` 缺失或畸形时 fail closed。
- 已修复：`memory.search/create_candidate/confirm/reject/explain_versions/prefetch` 统一经过 `CopilotService` 权限门控。
- 已修复：`confirm/reject` 不再只依赖 `actor_id` 字符串；可从 permission actor 派生 actor。
- 已修复：数据库层 tenant / organization / visibility migration、audit table、Feishu review surface、OpenClaw live bridge。
- 已修复：真实飞书 live sandbox 能把 actor、tenant、organization、chat、visibility 映射进 `current_context.permission`，非 demo tenant/org 不再被硬编码拒绝。
- 仍未完成：真实 Feishu DM 到本项目 first-class `memory.*` tool routing 和 productized live 长期运行。

## 2. Permission Context

首版兼容方案：OpenClaw payload 使用 `current_context.permission`。后续如果改为顶层 `permission_context`，字段语义必须保持一致。

```json
{
  "request_id": "req_20260507_xxx",
  "trace_id": "trace_20260507_xxx",
  "actor": {
    "user_id": "u_demo_owner",
    "open_id": "ou_demo_owner",
    "tenant_id": "tenant:demo",
    "organization_id": "org:demo",
    "roles": ["member", "reviewer"]
  },
  "source_context": {
    "entrypoint": "openclaw",
    "workspace_id": "project:feishu-memory-copilot",
    "chat_id": "optional",
    "document_id": "optional"
  },
  "requested_action": "memory.search",
  "requested_visibility": "team",
  "timestamp": "2026-05-07T00:00:00+08:00"
}
```

必填字段：

- `request_id`
- `trace_id`
- `actor.user_id` 或 `actor.open_id` 至少一个
- `actor.tenant_id`
- `actor.organization_id`
- `actor.roles`
- `source_context.entrypoint`
- `requested_action`
- `requested_visibility`
- `timestamp`

缺失或 malformed 时必须 fail closed。

## 3. Visibility Policy

| visibility_policy | 允许访问 |
|---|---|
| `private` | owner 或显式 reviewer/admin。 |
| `team` | 同 tenant、同 organization、同 workspace/scope 且角色允许。 |
| `organization` | 同 tenant、同 organization。 |
| `tenant` | 同 tenant 且非敏感字段；evidence 仍可被 redacted。 |
| `public_demo` | 只允许 seed/demo/replay；禁止真实飞书来源使用。 |

MVP 的 owner 判断规则：`owner_id` 优先；若旧数据没有 `owner_id`，则 `created_by` 作为 owner。后续引入 ACL 时可以扩展，但不能改变 `private` 默认不可被非 owner 读取的行为。

## 4. Permission Decision

允许：

```json
{
  "allowed": true,
  "decision": "allow",
  "reason_code": "same_org_team_visibility",
  "visible_fields": ["subject", "current_value", "summary", "evidence.quote"],
  "redacted_fields": [],
  "audit_required": true
}
```

拒绝：

```json
{
  "allowed": false,
  "decision": "deny",
  "reason_code": "tenant_mismatch",
  "visible_fields": [],
  "redacted_fields": ["current_value", "summary", "evidence"],
  "audit_required": true
}
```

脱敏：

```json
{
  "allowed": true,
  "decision": "redact",
  "reason_code": "evidence_source_restricted",
  "visible_fields": ["subject", "summary"],
  "redacted_fields": ["current_value", "evidence.quote"],
  "audit_required": true
}
```

## 5. Service Action Permission Matrix

| Action | Required decision | Fail-closed behavior | Audit |
|---|---|---|---|
| `memory.search` | actor can read requested visibility and scope | return `permission_denied`; no memory/evidence | allow/deny/redact |
| `memory.create_candidate` | actor can propose candidate in tenant/org/source context | reject candidate creation; no hidden auto-create | allow/deny |
| `memory.confirm` | actor has `reviewer`, `owner`, or `admin` role for candidate scope | candidate remains candidate | allow/deny |
| `memory.reject` | actor has `reviewer`, `owner`, or `admin` role for candidate scope | candidate remains unchanged | allow/deny |
| `memory.explain_versions` | actor can view memory and version evidence | deny or redact old values/evidence | allow/deny/redact |
| `memory.prefetch` | actor can read context pack fields | return denied/empty context pack | allow/deny/redact |
| `heartbeat.review_due` | actor/context can receive reminder candidate | withhold or redact reminder | allow/deny/redact |
| Feishu review card action | actor can review candidate | action rejected; card shows safe error | allow/deny |

## 6. Reason Codes

最小稳定 reason codes：

- `missing_permission_context`
- `malformed_permission_context`
- `tenant_mismatch`
- `organization_mismatch`
- `scope_mismatch`
- `visibility_private_non_owner`
- `review_role_required`
- `source_context_mismatch`
- `source_permission_revoked`
- `sensitive_content_redacted`
- `same_org_team_visibility`
- `public_demo_allowed`

## 7. Acceptance Criteria

- 所有 read/mutate action 都有 permission check，不只 search/create/prefetch。
- 缺失 permission context 必须 fail closed。
- denied response 不返回 memory/evidence 明文。
- redacted response 只能返回允许字段。
- 每个 decision 都写 audit 或结构化审计日志。
