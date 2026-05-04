# Productized Live Long-Run Plan Handoff

日期：2026-04-29

## 结论

已完成 productized live 长期运行**方案**，尚未实施 productized live。

本轮交付的是进入长期运行前的 gate 和 runbook：

- 分阶段上线 gate：L0 local staging、L1 internal pilot、L2 limited workspace pilot、L3 production candidate。
- 目标部署拓扑：OpenClaw Feishu websocket 单监听、OpenClaw Agent、first-class `fmc_*`、`CopilotService`、PostgreSQL ledger、Cognee curated recall、Feishu/Bitable review、audit surface。
- 监控和告警：healthcheck、audit query、audit alerts、websocket checker、后续 Prometheus exporter 指标。
- 权限后台最小形态：allowlist、reviewer/admin、source scope、visibility policy、source revoke。
- 审计 UI 最小形态：CLI + Bitable read-only view，后续再做 admin UI。
- 回滚和停机：停止唯一 listener、冻结写入、保留审计、SQLite/PostgreSQL/Cognee 回滚边界。
- 草案校准：`deployment-runbook.md`、`productized-live-architecture.md`、`monitoring-design.md`、`permission-admin-design.md`、`audit-ui-design.md`、`ops-runbook.md` 已加“方案设计 / 未完成上线 / 部分命令未实现”的校准说明。

## 主要文件

```text
docs/productization/productized-live-long-run-plan.md
docs/productization/full-copilot-next-execution-doc.md
docs/productization/prd-completion-audit-and-gap-tasks.md
docs/productization/launch-polish-todo.md
docs/README.md
README.md
docs/productization/deployment-runbook.md
docs/productization/productized-live-architecture.md
docs/productization/monitoring-design.md
docs/productization/permission-admin-design.md
docs/productization/audit-ui-design.md
docs/productization/ops-runbook.md
```

## 验证

文档-only 变更，最小 gate：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
git diff --check
ollama ps
```

如果下一轮开始实施 L1/L2，请先跑：

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

## 边界

可以说：

- productized live 长期运行方案已完成。
- 进入 L1/L2/L3 前需要满足的部署、监控、回滚、权限后台、审计 UI 和运维 gate 已写清。
- 当前仍保持 candidate-only、permission fail-closed、single-listener 和 no-overclaim。

不能说：

- productized live 已完成。
- 生产 PostgreSQL 已部署。
- 生产级 Prometheus/Grafana 已完成。
- 多租户企业后台、权限后台和审计 UI 已实现。
- 长期 embedding 服务已完成。
- 真实 Feishu DM 已稳定覆盖全部 first-class `fmc_*` / `memory.*` 工具动作。

## 下一步

如继续产品化，下一步不是再写大计划，而是选择一个 gate 做受控实施：

1. L1 internal pilot：用 allowlist 群和指定 reviewer 跑 24 小时受控试点。
2. PostgreSQL pilot：做一套托管 PostgreSQL dry-run / restore 演练，不切全量生产。
3. 权限后台最小化：把 allowlist / reviewer / source scope 配到 Bitable，并读回确认。
4. 审计 read-only view：把 `query_audit_events.py` 的输出同步到只读 Bitable 视图。

## Workspace Ingestion Finalizer

2026-05-04 已补 workspace productized evidence finalizer：

```bash
python3 scripts/finalize_workspace_ingestion_productized_evidence.py --launchd-label com.feishu-ai-challenge.workspace-ingestion-longrun --json
```

它只读现有 manifest、objective audit 和 long-run evidence，不启动 ingestion、Feishu listener 或 bot 消息发送。当前复跑结果是 `goal_complete=false`：source coverage、scheduler/cursor、rate-limit、governance 和 operations 已通过，唯一 blocker 仍是 `live_long_run.duration_hours_at_least_24`；最新 active finalization 读回 11 次成功、0 unresolved failure、`window_hours=1.4839`。`run_workspace_ingestion_long_run_tick.py` 现在会在每轮 merge 成功后自动写 `workspace-productized-finalization.active.json`，因此 24 小时窗口满足后先检查这个 finalization status，再同步 README、handoff、飞书看板、commit/push 和目标状态。
