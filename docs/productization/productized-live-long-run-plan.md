# Productized Live Long-Run Plan

日期：2026-04-29  
状态：方案已完成，尚未实施生产部署。  
范围：OpenClaw-native Feishu Memory Copilot 从本机 demo / staging 进入受控长期运行试点前的部署、监控、回滚、权限后台、审计 UI 和运维边界。

## 先看这个

本文件不是上线证明。它定义进入 productized live 前必须满足的 gate，以及出现问题时怎么停、怎么回滚、怎么查。

当前可以说：

- 本地 MVP / Demo / Pre-production 闭环已完成。
- OpenClaw first-class `fmc_*` 工具、本机 websocket staging、一次受控真实 DM allow-path、真实 Feishu API candidate-only 拉取入口、审计查询和告警面已完成。
- 真实飞书来源仍只进入 candidate，不能自动 active。

当前不能说：

- 已生产部署。
- 已全量接入飞书 workspace。
- 已完成多租户企业后台。
- 已完成长期 embedding 服务。
- 已完成真实 Feishu DM 到全部 first-class `fmc_*` / `memory.*` 工具的稳定长期路由。
- 已完成 productized live 长期运行。

## 目标运行形态

```text
Feishu workspace
  -> OpenClaw Feishu websocket (single listener)
  -> OpenClaw Agent runtime
  -> fmc_* first-class tools
  -> memory.* bridge
  -> handle_tool_request()
  -> CopilotService
  -> permission / governance / retrieval / audit
  -> PostgreSQL primary ledger
  -> Cognee / curated embedding recall channel
  -> Feishu card / Bitable review and audit surfaces
```

长期运行时，`CopilotService` 仍是事实源。OpenClaw、Feishu card、Bitable、CLI、benchmark runner 都不能直接改 active memory。

## 现有草案文档的使用边界

仓库已有一组 productized live 草案，可以作为设计参考，但不能直接当成当前可执行 runbook。

| 文档 | 当前用途 | 边界 |
|---|---|---|
| [productized-live-architecture.md](productized-live-architecture.md) | 生产拓扑参考 | PostgreSQL、Cognee server、Ollama 长期服务仍未部署 |
| [deployment-runbook.md](deployment-runbook.md) | 部署步骤草案 | 包含当前仓库未实现或未验证的命令，例如 `scripts/validate_env.py`、`requirements.txt`、`scripts/backup_database.sh` |
| [ops-runbook.md](ops-runbook.md) | 运维流程草案 | 包含生产 PostgreSQL / systemd / exporter 假设，当前只作未来实施参考 |
| [monitoring-design.md](monitoring-design.md) | Prometheus/Grafana 指标设计 | 生产级 exporter / dashboard 尚未实现 |
| [permission-admin-design.md](permission-admin-design.md) | 多租户权限后台设计 | 当前只有权限映射和 fail-closed 本地闭环，不是企业后台 |
| [audit-ui-design.md](audit-ui-design.md) | 审计 UI 设计 | 当前实现是 CLI 查询/导出和告警脚本，不是生产 UI |

当前事实源以本文件、`README.md`、`full-copilot-next-execution-doc.md`、`prd-completion-audit-and-gap-tasks.md` 和各 handoff 为准。后续实施时，先把草案命令对齐当前仓库，再进入 L1/L2 gate。

## 分阶段上线 Gate

| Gate | 目标 | 允许流量 | 通过标准 | 失败处理 |
|---|---|---|---|---|
| L0 local staging | 保持当前本机可复现能力 | 本机 fixture / 受控测试群 | healthcheck、demo readiness、单测、audit/query/alert 脚本通过 | 停止进入 L1，回到本机修复 |
| L1 internal pilot | 小范围内部群试点 | allowlist 群、指定 reviewer、指定 source | 单监听、candidate-only、review flow、audit query、告警读数稳定 | 停止 Feishu websocket，保留审计，回滚到上一版本 |
| L2 limited workspace pilot | 指定 workspace / 项目群 | 指定群聊、文档、任务、会议、Bitable 记录 | source_context 不越权，source revoke 生效，PostgreSQL 备份恢复演练通过 | 冻结 ingestion，只保留 read/search 或完全停用 |
| L3 production candidate | 可申请生产上线 | 仍需租户管理员批准和安全审查 | SLO、监控、权限后台、审计 UI、数据保留、应急值班都齐备 | 不进入生产，维持 pilot |

## 部署拓扑

第一版长期试点建议用“少组件、强 gate”的拓扑：

| 组件 | 建议形态 | 说明 |
|---|---|---|
| OpenClaw gateway | 单实例托管进程或受控主机 service | 固定 `2026.4.24`，禁止自动升级 |
| Feishu listener | OpenClaw Feishu websocket only | 与 Copilot lark-cli sandbox、legacy listener 三选一 |
| Copilot service | Python service / worker | 所有工具入口进入 `handle_tool_request()` / `CopilotService` |
| Primary ledger | 托管 PostgreSQL | SQLite 只保留本机 demo / staging |
| Cognee recall | 窄 adapter | 只同步 curated memory fields，不向量化 raw events |
| Review surface | Feishu card + Bitable | confirm/reject 必须回到 service |
| Audit surface | query script + Bitable/dashboard + later admin UI | 第一版先用只读审计查询和导出，不直接开放改写 |
| Metrics | healthcheck + audit alerts + Prometheus exporter 待实现 | 当前已有本地脚本，生产 exporter 尚未完成 |

## 配置和 Secret 边界

所有真实配置只放部署环境或密钥管理系统，不写仓库：

- Feishu app id / secret / token。
- OpenClaw channel credentials。
- PostgreSQL `DATABASE_URL`。
- LLM / embedding provider API key。
- 真实 chat_id、open_id、user_id allowlist。

仓库只保留：

- `.env.example` 的字段名。
- 脱敏 runbook。
- 本机验证命令。
- request_id / trace_id / 统计结果。

## 上线前 Preflight

每次进入 L1/L2 前按顺序执行：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
python3 scripts/check_copilot_health.py --json
python3 scripts/check_demo_readiness.py --json
python3 scripts/migrate_copilot_storage.py --dry-run --json
python3 scripts/query_audit_events.py --summary --json
python3 scripts/check_audit_alerts.py --json
git diff --check
ollama ps
```

如果需要验证 OpenClaw Feishu websocket running：

```bash
python3 scripts/check_copilot_health.py --json --openclaw-websocket-check
```

注意：`check_audit_alerts.py` 在真实数据库上发现 critical alert 时会返回非 0。此时不要把它当成脚本坏了，要先读 JSON，判断是否是近期 deny/failure 激增。

## 监控和告警

当前已有本地脚本：

- `scripts/check_copilot_health.py --json`
- `scripts/query_audit_events.py --summary --json`
- `scripts/check_audit_alerts.py --json`
- `scripts/check_openclaw_feishu_websocket.py --json`

进入 L2 前必须补生产采集面：

| 指标 | 来源 | 阈值建议 |
|---|---|---|
| `permission_deny_rate` | `memory_audit_events` | 60 分钟 > 30% warning，> 60% critical |
| `ingestion_failed_rate` | `event_type=ingestion_failed` | 60 分钟 > 10% warning，> 20% critical |
| `review_backlog_count` | candidate table / Bitable | 超过 50 条 warning |
| `websocket_down` | OpenClaw channels status + gateway logs | 连续 2 次失败 critical |
| `embedding_unavailable_total` | `event_type=embedding_unavailable` | 连续出现 warning；影响 recall 时 critical |
| `audit_gap_minutes` | audit max created_at | > 30 分钟 warning，> 90 分钟 critical |
| `source_revoked_count` | `source_permission_revoked` | 突增时人工复核 |

## 权限后台最小形态

第一版不要做大而全后台。先把可控项放到 Bitable / config 管理：

| 配置 | 最小形态 | 必须行为 |
|---|---|---|
| 群聊 allowlist | Bitable 或环境配置 | 不在 allowlist 的真实消息不进入 ingestion |
| reviewer/admin | Bitable 或环境配置 | confirm/reject 只允许 reviewer/owner/admin |
| source scope | chat/document/task/meeting/bitable source_context | mismatch fail closed before fetch |
| visibility policy | `private/team/organization/tenant` | 默认 `team`，敏感 source 不自动扩大 |
| source revoke | `mark_feishu_source_revoked()` | active memory 标 stale，默认 recall 隐藏 |

## 审计 UI 最小形态

L1 可以先使用 CLI + Bitable read-only view：

```bash
python3 scripts/query_audit_events.py --event-type permission_denied --json --limit 20
python3 scripts/query_audit_events.py --event-type ingestion_failed --json --limit 20
python3 scripts/query_audit_events.py --summary --group-by reason_code --json
```

L2 前必须补：

- 按 `request_id` / `trace_id` 查完整链路。
- 按 actor / tenant / source_type 查最近事件。
- 按 event_type 聚合 deny、failure、confirm/reject、source revoke。
- 导出时自动隐藏 token、secret、raw text、quote。

审计 UI 只能读，不允许直接改 candidate / active / superseded 状态。

## 回滚和停机

### 立即停止入口

```bash
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
```

然后停止当前唯一 listener。不要同时启动 fallback listener 作为“热修”。

### 冻结写入

当出现权限泄露风险、大量 ingestion failure、source revoke 异常时：

1. 停止 Feishu websocket 或把 allowlist 清空。
2. 保留 `memory.search` read-only 能力，或完全停用 OpenClaw plugin。
3. 禁止 confirm/reject 直接操作，直到审计复核完成。
4. 导出最近 24 小时 audit summary。

### 数据回滚

- SQLite staging：按备份文件恢复，不 drop audit table。
- PostgreSQL pilot：使用托管 PITR / snapshot；恢复前先停 ingestion。
- Cognee：以本地 ledger 为事实源；Cognee result 未匹配 ledger 不进入 answer。

## Release Acceptance

进入 L1 需要：

- 单监听 preflight 通过。
- `check_copilot_health.py --json` fail=0。
- `check_demo_readiness.py --json` ok=true。
- `query_audit_events.py --summary --json` 可读。
- `check_audit_alerts.py --json` 无未解释 critical，或已记录解释和处理人。
- README / handoff / 看板都不 overclaim。

进入 L2 还需要：

- PostgreSQL 试点库 dry-run / apply / restore 演练完成。
- allowlist、reviewer/admin、source_context 配置有变更记录。
- 真实 Task / Meeting / Bitable source smoke 至少各 1 条，仍 candidate-only。
- websocket down、embedding unavailable、ingestion_failed、permission_denied 都能在运维报告里定位。

## 当前剩余风险

- 生产 PostgreSQL 未部署。
- 生产级 Prometheus/Grafana/exporter 未实现。
- 权限后台和审计 UI 仍是方案，不是完整产品页面。
- 长期 embedding 服务未完成；当前只是本机 Ollama / Cognee gate 和 fallback 方案。
- 真实 Feishu DM 只有 `fmc_memory_search` 一次 allow-path 证据，未覆盖全部工具动作和长期稳定性。
- 全量 Feishu workspace ingestion 不在当前范围内。
