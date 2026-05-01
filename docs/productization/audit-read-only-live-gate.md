# Audit Read-Only Live Gate

日期：2026-05-01

选择的 productized live 小 gate：先实施 **审计 read-only view**，不碰生产写入、不开放后台配置写操作。

## 为什么选这个 gate

- 已有本地审计表、healthcheck、admin read-only snapshot 和 audit ops scripts。
- 风险低：只读，不改变 memory / candidate 状态。
- 能直接服务评委和内部试点：展示权限门控、候选状态机、版本解释、graph 拓扑和失败审计是否可追溯。

## Gate 范围

已具备：

- `memory_audit_events` 本地表和多 action 审计写入。
- `scripts/query_audit_events.py` 查询/导出，支持 `tenant_id` / `organization_id` 过滤，并对 `source_context` 做递归脱敏。
- `scripts/check_audit_alerts.py` 告警检查。
- `memory_engine/copilot/admin.py` read-only dashboard snapshot，包含 audit 和 knowledge graph 概览。
- `tests/test_copilot_healthcheck.py`、`tests/test_audit_ops_scripts.py` 覆盖基础健康检查。

本 gate 可执行验收：

- `scripts/check_copilot_audit_readonly_gate.py` 会 seed 或读取 SQLite 审计数据，验证 CLI 与 Admin `/api/audit` 的 tenant/org 过滤、`source_context` 脱敏、CSV 导出、POST 写入拒绝和只读计数不变。
- README 和 benchmark 文档必须只称 “read-only gate / pre-production local”，不能写 production live 完成。
- 真实 Feishu smoke 时，审计读回作为每个场景的完成证据。
- dashboard 只读；确认/拒绝/补证据仍必须走 `CopilotService` 状态机和权限上下文。

## 验收命令

```bash
python3 scripts/check_copilot_health.py --json
python3 scripts/query_audit_events.py --limit 10
python3 scripts/check_copilot_audit_readonly_gate.py --json
python3 scripts/check_audit_alerts.py
python3 -m unittest tests.test_copilot_healthcheck tests.test_audit_ops_scripts
```

## 未完成边界

- 不是多租户企业后台。
- 不是生产长期运行。
- 不是全量 Feishu workspace 审计接入。
- 不提供后台写配置、权限策略编辑或人工批量确认。
