# Feishu Memory Copilot - Productized Live 部署架构

日期：2026-04-28
状态：方案设计（未完成生产上线）
适用范围：生产部署架构参考，新成员理解系统拓扑

> 2026-04-29 校准：本文是架构参考，不代表生产部署已完成。当前事实是本地 demo / staging、受控真实 DM allow-path、candidate-only API 入口和本地审计/告警面已完成；PostgreSQL、生产级监控、权限后台、审计 UI 和长期 embedding 服务仍未实施。执行 gate 见 [productized-live-long-run-plan.md](productized-live-long-run-plan.md)。

---

## 1. 架构概览

```text
                          ┌─────────────────────────────────────────────────────────────┐
                          │                    Feishu Cloud                              │
                          │  ┌─────────────────────────────────────────────────────────┐ │
                          │  │  User Messages  │  Card Actions  │  Bot Events         │ │
                          │  └────────┬────────┴───────┬────────┴───────┬─────────────┘ │
                          │           │                │                │                │
                          └───────────┼────────────────┼────────────────┼────────────────┘
                                      │                │                │
                                      ▼                ▼                ▼
                          ┌─────────────────────────────────────────────────────────────┐
                          │                  OpenClaw Gateway                            │
                          │     (WebSocket / HTTP Webhook)                              │
                          │                                                             │
                          │  ┌───────────────────────────────────────────────────────┐  │
                          │  │  Feishu Channel Adapter                               │  │
                          │  │  - im.message.receive_v1                              │  │
                          │  │  - card.action.trigger                                │  │
                          │  └───────────────────────┬───────────────────────────────┘  │
                          └──────────────────────────┼──────────────────────────────────┘
                                                     │
                                                     ▼
                          ┌─────────────────────────────────────────────────────────────┐
                          │              OpenClaw Agent Runtime                          │
                          │                                                             │
                          │  ┌───────────────────────────────────────────────────────┐  │
                          │  │  Tool Router / Dispatch                               │  │
                          │  │  - memory.search                                      │  │
                          │  │  - memory.create_candidate                            │  │
                          │  │  - memory.confirm / reject                            │  │
                          │  │  - memory.explain_versions                            │  │
                          │  │  - memory.prefetch                                    │  │
                          │  │  - heartbeat.review_due                               │  │
                          │  └───────────────────────┬───────────────────────────────┘  │
                          │                          │                                  │
                          │  ┌───────────────────────▼───────────────────────────────┐  │
                          │  │  feishu-memory-copilot Plugin                          │  │
                          │  │  (agent_adapters/openclaw/plugin/)                    │  │
                          │  └───────────────────────┬───────────────────────────────┘  │
                          └──────────────────────────┼──────────────────────────────────┘
                                                     │
                                                     ▼
                          ┌─────────────────────────────────────────────────────────────┐
                          │              CopilotService (唯一事实源)                      │
                          │                                                             │
                          │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐│
                          │  │ Permissions │  │ Governance  │  │ Audit               ││
                          │  │ (fail-      │  │ (Candidate  │  │ (append-only        ││
                          │  │  closed)    │  │  Lifecycle) │  │  events)            ││
                          │  └─────────────┘  └─────────────┘  └─────────────────────┘│
                          │                                                             │
                          │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐│
                          │  │ Retrieval   │  │ Embedding   │  │ Ingestion           ││
                          │  │ (hybrid)    │  │ Provider    │  │ (candidate-only)    ││
                          │  └─────────────┘  └─────────────┘  └─────────────────────┘│
                          └──────────────────────────┬──────────────────────────────────┘
                                                     │
                    ┌────────────────────────────────┼────────────────────────────────┐
                    │                                │                                │
                    ▼                                ▼                                ▼
    ┌──────────────────────────┐    ┌──────────────────────────┐    ┌──────────────────────────┐
    │      PostgreSQL           │    │      Cognee              │    │      Ollama              │
    │      (生产数据库)          │    │      (Graph Engine)      │    │      (Embedding)         │
    │                          │    │                          │    │                          │
    │  - memories              │    │  - Knowledge Graph       │    │  - qwen3-embedding       │
    │  - memory_versions       │    │  - Cognify Pipeline      │    │  - 1024-dim vectors      │
    │  - memory_evidence       │    │  - Retrieval             │    │  - Local inference       │
    │  - memory_candidates     │    │                          │    │                          │
    │  - memory_audit_events   │    │  Status: Optional        │    │  Status: Required        │
    │  - raw_events            │    │  (fallback to repo)      │    │  (fallback to determin.) │
    └──────────────────────────┘    └──────────────────────────┘    └──────────────────────────┘
```

---

## 2. 组件说明

### 2.1 OpenClaw Gateway

| 项目 | 说明 |
|------|------|
| 职责 | 接收飞书 WebSocket/Webhook 事件，分发到 Agent Runtime |
| 版本 | 2026.4.24（当前锁定） |
| 监听 | im.message.receive_v1, card.action.trigger |
| 部署 | 容器化，可水平扩展 |
| 健康检查 | `/health` endpoint |

### 2.2 OpenClaw Agent Runtime

| 项目 | 说明 |
|------|------|
| 职责 | Agent 调度、Tool Router、插件加载 |
| 插件 | feishu-memory-copilot |
| 工具注册 | 7 个 memory.* 工具 |
| 路由 | Tool Router -> handle_tool_request() |
| 部署 | 与 Gateway 同 Pod 或独立进程 |

### 2.3 CopilotService

| 项目 | 说明 |
|------|------|
| 职责 | 唯一事实源，权限门控，业务逻辑 |
| 核心模块 | Permissions, Governance, Retrieval, Audit, Ingestion, Embedding |
| 入口 | handle_tool_request() |
| 约束 | 所有入口必须经过 CopilotService |

### 2.4 PostgreSQL（生产数据库）

| 项目 | 说明 |
|------|------|
| 用途 | 替代 SQLite，支持并发和持久化 |
| 表结构 | memories, memory_versions, memory_evidence, memory_candidates, memory_audit_events, raw_events |
| 索引 | tenant_id, organization_id, scope, status 复合索引 |
| 备份 | 每日全量 + WAL 增量 |
| 迁移 | 使用 migrate_copilot_storage.py |

### 2.5 Cognee（Graph Engine）

| 项目 | 说明 |
|------|------|
| 用途 | 知识图谱存储、语义检索 |
| 状态 | Optional（可 fallback 到 repository） |
| 同步 | confirm -> add -> cognify; reject -> withdrawal |
| 部署 | 独立服务 |

### 2.6 Ollama（Embedding）

| 项目 | 说明 |
|------|------|
| 用途 | 向量嵌入生成 |
| 模型 | qwen3-embedding:0.6b-fp16 |
| 维度 | 1024 |
| 状态 | Required（可 fallback 到 DeterministicEmbeddingProvider） |
| 部署 | 本地或容器化 |

---

## 3. 数据流

### 3.1 搜索流程

```
User DM (@Bot question)
  -> OpenClaw Gateway
  -> Agent Runtime (Tool Router)
  -> memory.search
  -> handle_tool_request()
  -> CopilotService.search()
    -> Permission Check (fail-closed)
    -> Retrieval (hybrid: Cognee + SQLite)
    -> Audit Log (allow/deny/redact)
  -> Return memory + evidence
```

### 3.2 候选确认流程

```
User DM (/remember ...)
  -> OpenClaw Gateway
  -> Agent Runtime
  -> memory.create_candidate
  -> handle_tool_request()
  -> CopilotService.create_candidate()
    -> Permission Check
    -> Candidate Created (status=candidate)
    -> Audit Log
  -> Return candidate_id

Reviewer Click (Card Action)
  -> OpenClaw Gateway
  -> Agent Runtime
  -> memory.confirm
  -> handle_tool_request()
  -> CopilotService.confirm()
    -> Permission Check (reviewer/admin)
    -> Candidate -> Active Memory
    -> Cognee Sync (optional)
    -> Audit Log
  -> Return confirmation
```

### 3.3 Ingestion 流程

```
Feishu Message/Doc/Task/Meeting/Bitable
  -> Limited Ingestion Pipeline
  -> Source Validation (permission, tenant, org)
  -> Candidate Creation (candidate-only, no auto-active)
  -> Audit Log
```

---

## 4. 多租户隔离

### 4.1 隔离层级

| 层级 | 字段 | 说明 |
|------|------|------|
| 租户 | tenant_id | 最外层隔离，跨租户数据不可见 |
| 组织 | organization_id | 租户内组织隔离 |
| 工作区 | workspace_id | 可选，组织内项目隔离 |
| 范围 | scope_type + scope_id | 兼容旧模型 |

### 4.2 权限决策

```text
Permission Context (current_context.permission)
  -> actor.tenant_id == request.tenant_id ?  [Tenant Match]
  -> actor.organization_id == request.organization_id ?  [Org Match]
  -> visibility_policy check?  [Visibility]
  -> role check (admin/reviewer/member)?  [Role]
  -> Permission Decision (allow/deny/redact)
```

### 4.3 Fail-Closed 规则

- 缺失 permission context -> deny
- Malformed permission context -> deny
- Tenant mismatch -> deny
- Organization mismatch -> deny
- Visibility violation -> deny/redact

---

## 5. 高可用设计

### 5.1 组件冗余

| 组件 | 冗余策略 | 说明 |
|------|----------|------|
| OpenClaw Gateway | 多实例 + Load Balancer | WebSocket 连接亲和性 |
| Agent Runtime | 多实例 | 无状态 |
| CopilotService | 多实例 | 无状态，依赖 DB |
| PostgreSQL | Primary + Replica | 主从复制 |
| Cognee | 单实例 + Fallback | Optional |
| Ollama | 单实例 + Fallback | 可用 DeterministicEmbedding |

### 5.2 故障降级

| 故障场景 | 降级策略 | 影响 |
|----------|----------|------|
| Ollama 不可用 | Fallback 到 DeterministicEmbedding | 搜索质量下降 |
| Cognee 不可用 | Fallback 到 repository-ledger | 图谱功能不可用 |
| PostgreSQL 不可用 | 服务不可用（无法降级） | 完全中断 |
| OpenClaw 断开 | 自动重连 + 手动重启 | 消息处理中断 |

---

## 6. 安全边界

### 6.1 数据安全

- 真实飞书数据只进 candidate，不自动 active
- Permission fail-closed，缺失/畸形一律拒绝
- Audit append-only，不删除不修改
- Token/Secret 不写入日志或 git

### 6.2 网络安全

- OpenClaw Gateway: HTTPS/WSS
- PostgreSQL: 内网访问
- Ollama: 内网访问
- Cognee: 内网访问

### 6.3 权限边界

- 所有 memory.* 工具必须带 current_context.permission
- Review 操作需要 reviewer/admin 角色
- 真实飞书来源默认 review_required=true

---

## 7. 监控点位

| 点位 | 说明 | 告警阈值 |
|------|------|----------|
| Gateway 连接数 | WebSocket 连接数 | > 1000 |
| 请求延迟 | memory.search P99 | > 2000ms |
| 错误率 | 所有工具错误率 | > 5% |
| Permission Deny 率 | deny / total | > 30% |
| Ingestion 失败率 | failure / total | > 10% |
| Audit 间隔 | 最近两条 audit 时间差 | > 30min |
| DB 连接数 | PostgreSQL 连接池使用率 | > 80% |

---

## 8. 部署拓扑

### 8.1 单节点部署（开发/测试）

```text
┌─────────────────────────────────────────────┐
│                  单节点                      │
│                                             │
│  OpenClaw (Gateway + Agent)                 │
│  CopilotService                             │
│  PostgreSQL (本地)                           │
│  Cognee (本地)                              │
│  Ollama (本地)                              │
└─────────────────────────────────────────────┘
```

### 8.2 生产部署

```text
┌─────────────────────────────────────────────────────────────────────┐
│                          Load Balancer                              │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     OpenClaw Cluster                                │
│                                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │
│  │  Instance 1 │  │  Instance 2 │  │  Instance N │               │
│  │  (Gateway + │  │  (Gateway + │  │  (Gateway + │               │
│  │   Agent)    │  │   Agent)    │  │   Agent)    │               │
│  └─────────────┘  └─────────────┘  └─────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     PostgreSQL Cluster                               │
│                                                                     │
│  ┌─────────────┐        ┌─────────────┐                           │
│  │   Primary   │ -----> │   Replica   │                           │
│  │   (Read/    │        │   (Read)    │                           │
│  │    Write)   │        │             │                           │
│  └─────────────┘        └─────────────┘                           │
└─────────────────────────────────────────────────────────────────────┘
                    │                               │
                    ▼                               ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│      Cognee              │    │      Ollama              │
│      (Graph Engine)      │    │      (Embedding)         │
└──────────────────────────┘    └──────────────────────────┘
```

---

## 9. 待实现清单

| 项目 | 状态 | 优先级 |
|------|------|--------|
| PostgreSQL 生产部署 | 待实现 | P0 |
| OpenClaw 多实例部署 | 待实现 | P1 |
| Cognee 容器化 | 待实现 | P2 |
| Ollama 容器化 | 待实现 | P1 |
| 监控告警 | 待实现 | P1 |
| 备份恢复演练 | 待实现 | P0 |
| 灾备切换 | 待实现 | P2 |

---

## 10. 参考文档

- `docs/productization/contracts/storage-contract.md` - 存储契约
- `docs/productization/contracts/permission-contract.md` - 权限契约
- `docs/productization/contracts/audit-observability-contract.md` - 审计契约
- `docs/productization/deployment-runbook.md` - 部署步骤
- `docs/productization/monitoring-design.md` - 监控方案
- `docs/productization/ops-runbook.md` - 运维流程
