# OpenClaw Payload Contract：Feishu Memory Copilot Phase 1

日期：2026-05-07
状态：Phase 1 contract freeze 已完成；OpenClaw schema 已按 `current_context.permission` 更新（commit `b6b17b4`）
适用范围：`agent_adapters/openclaw/memory_tools.schema.json`、OpenClaw examples、`memory_engine/copilot/tools.py`。

## 1. 决策

首版采用兼容过渡方案：继续保留现有 `current_context`，但冻结 `current_context.permission` 子结构。

原因：

- 当前 OpenClaw schema 已经把 `current_context` 作为对象传入 `memory.search`、`memory.create_candidate`、`memory.prefetch`。
- 直接新增顶层 `permission_context` 会造成 schema/examples/tools 同时 breaking change。
- 兼容方案可以让旧 schema demo 和 benchmark 继续跑，同时要求真实产品路径必须传 `current_context.permission`。

未来如果进入 major schema version，可把 `current_context.permission` 提升为顶层 `permission_context`。

## 2. Payload Shape

所有 `memory.*` tool 后续都必须支持：

```json
{
  "scope": "project:feishu-memory-copilot",
  "current_context": {
    "scope": "project:feishu-memory-copilot",
    "session_id": "optional",
    "chat_id": "optional",
    "task_id": "optional",
    "intent": "optional",
    "thread_topic": "optional",
    "permission": {
      "request_id": "req_demo_001",
      "trace_id": "trace_demo_001",
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
  }
}
```

## 3. Required Per Tool

| Tool | Required fields after Phase 1 implementation | Compatibility note |
|---|---|---|
| `memory.search` | `query`, `scope`, `current_context.permission` | schema demo 可临时缺 permission，但 product/live path 必须 fail closed。 |
| `memory.create_candidate` | `text`, `scope`, `source`, `current_context.permission` | `auto_confirm` 对真实飞书来源必须 ignored/false。 |
| `memory.confirm` | `candidate_id`, `scope`, `current_context.permission`, `reason` | `actor_id` 可保留兼容，但不能替代 permission actor。 |
| `memory.reject` | `candidate_id`, `scope`, `current_context.permission`, `reason` | 同上。 |
| `memory.explain_versions` | `memory_id`, `scope`, `current_context.permission` | 版本值/evidence 可能 redacted。 |
| `memory.prefetch` | `task`, `scope`, `current_context.permission` | 返回 denied/empty pack 时仍含 trace。 |

实现状态（2026-05-07）：

- 已完成：`agent_adapters/openclaw/memory_tools.schema.json` 要求六个 MVP 工具携带 `current_context.permission`。
- 已完成：examples 已补 allow/deny/redacted 相关样例。
- 已完成：OpenClaw/runtime 本地桥通过 `handle_tool_request()` 真实调用 seed/local `CopilotService`，并返回 bridge request/trace/permission decision；仍不是 Feishu live ingestion。

## 4. Error Format

统一错误仍使用现有 error schema：

```json
{
  "ok": false,
  "error": {
    "code": "permission_denied",
    "message": "permission context is required",
    "retryable": false,
    "details": {
      "reason_code": "missing_permission_context",
      "request_id": "req_demo_001",
      "trace_id": "trace_demo_001"
    }
  }
}
```

新增 reason_code 不一定需要新增 top-level error code，优先放在 `details.reason_code`。

## 5. Versioning

- 当前 schema `version` 保持 `2026-04-27`，直到实现时决定是否 bump。
- 如果实现改变 required fields，应 bump 到 `2026-05-07` 或更高，并同步 examples/tests。
- OpenClaw 运行版本仍锁定 `2026.4.24`。

## 6. Acceptance Criteria

- 真实产品路径不能只依赖 `actor_id` 或 `allowed_scopes`。
- 所有工具都有 request_id/trace_id 贯穿服务输出或错误输出。
- schema demo、dry-run、OpenClaw live bridge 的文档标签必须不同。
- Phase 2 前，examples 至少提供 allow、deny、redact 三种 payload。
