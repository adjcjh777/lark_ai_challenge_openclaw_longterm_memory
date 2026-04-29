# Audit Ops Observability Handoff

日期：2026-04-29

## 结论

本轮补齐的是 **本地审计查询、告警和 health/ops 口径**，不是生产级监控平台。

已完成：

- `memory_audit_events` 不再只覆盖成功路径和 smoke test；limited ingestion 的 permission/source mismatch、Feishu fetch 失败、候选提取为空会写 `event_type=ingestion_failed`。
- `scripts/query_audit_events.py` 可用于按 event/action/actor/tenant/permission/time 查询审计事件，支持 JSON、CSV 和 summary。
- `scripts/check_audit_alerts.py` 的 ingestion failure rate 优先使用显式 `ingestion_failed`，并保留旧 deny/error 兼容口径。
- `scripts/check_copilot_health.py --json` 默认包含 `openclaw_websocket.status=skipped` 运维入口，不主动跑真实 websocket；需要 staging 证据时用 `--openclaw-websocket-check` 显式纳入。
- `embedding_provider` healthcheck 输出 `runtime_fallback_available`、`unavailable_reason`、`monitoring_status`；runtime search 如果使用 deterministic fallback，会写 `event_type=embedding_unavailable` ops audit。
- 审计失败事件只写 source/type/reason/request/trace，不写 raw text、quote、token 或 secret。

## 主要文件

```text
memory_engine/document_ingestion.py
memory_engine/copilot/healthcheck.py
memory_engine/copilot/service.py
scripts/check_copilot_health.py
scripts/check_audit_alerts.py
tests/test_document_ingestion.py
tests/test_copilot_healthcheck.py
tests/test_audit_ops_scripts.py
docs/productization/contracts/audit-observability-contract.md
```

## 可复现命令

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_healthcheck tests.test_audit_ops_scripts tests.test_document_ingestion tests.test_audit_log_sanitization -v
python3 scripts/check_copilot_health.py --json
python3 scripts/query_audit_events.py --summary --json
python3 scripts/check_audit_alerts.py --json
git diff --check
ollama ps
```

需要真实 OpenClaw Feishu websocket staging 运维检查时，先确认单监听，再显式运行：

```bash
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
python3 scripts/check_copilot_health.py --json --openclaw-websocket-check
```

## 查询示例

```bash
python3 scripts/query_audit_events.py --event-type permission_denied --json --limit 20
python3 scripts/query_audit_events.py --event-type ingestion_failed --json --limit 20
python3 scripts/query_audit_events.py --summary --group-by reason_code --json
python3 scripts/check_audit_alerts.py --json --window-minutes 60
```

## 边界

可以说：

- 本地 SQLite 审计表、查询、导出、告警脚本和 healthcheck ops 口径已补齐。
- 权限拒绝、candidate/review、limited ingestion、source revoke、显式 ingestion failure、embedding unavailable fallback 都有可查询面或 health/ops 面。
- websocket down 可通过独立 staging checker 或显式 healthcheck 参数纳入运维报告。

不能说：

- 已完成生产级 Prometheus/Grafana。
- 已完成长期线上指标采集、自动扩缩容或自动回滚。
- 已完成 productized live 长期运行。
- 真实 Feishu DM 已稳定长期路由到全部 first-class `fmc_*` / `memory.*` 工具。
