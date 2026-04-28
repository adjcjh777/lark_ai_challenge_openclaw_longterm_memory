# Audit & Observability Contract：Feishu Memory Copilot Phase 1

日期：2026-05-07
状态：Phase A 已实现本地 SQLite audit table 和 healthcheck audit smoke；仍不是生产监控系统。
适用范围：Copilot service、permission decisions、Feishu review surface、OpenClaw tool trace、healthcheck。

## 1. 目标

让完整产品能解释每次记忆读写和提醒为什么发生、谁触发、谁能看、哪些字段被遮挡。Phase A 已把最小审计事件写入 `memory_audit_events`，覆盖 confirm/reject/deny/limited ingestion candidate/heartbeat candidate。

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
| source revoked/deleted handling | 是 |

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
    "available": true
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
- `sensitive_redaction_total`

## 6. Safe Logging Rules

- 不记录 token、app secret、OpenAI/RightCode key、Bearer token。
- deny 日志不记录 raw private memory、完整 evidence quote 或真实飞书私密内容。
- `redacted_fields` 只记录字段名，不记录被遮挡明文。
- 飞书 chat_id/user_id 可以记录内部 ID，但提交仓库前必须确保日志不进入 git。

## 7. Acceptance Criteria

- 每个 permission decision 有 audit 事件或结构化日志。
- 每个 review action 有 actor、role、reason 和 source_context。
- Healthcheck 能显示 schema version 和 permission contract loaded 状态。
- Product QA 能按 audit/trace 查出一次 search 或 confirm 的完整链路。
