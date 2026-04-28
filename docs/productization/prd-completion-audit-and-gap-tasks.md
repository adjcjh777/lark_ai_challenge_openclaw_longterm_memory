# PRD Completion Audit and Gap Tasks

日期：2026-04-28
当前事实源：仓库代码、PRD、主控计划、README、handoff、healthcheck 和本轮本地验证命令。

## 先看这个

1. 今天的真实日期是 2026-04-28；仓库里已经存在 2026-05-03 到 2026-05-08 的计划、handoff 和交付文档，本审计按“当前仓库状态”核对完成度。
2. 2026-05-05 及以前的 implementation plan 已经全部完成，不再需要执行；它们只保留为历史计划、验收证据和风险参考。
3. 当前可以判断：MVP 的本地可复现闭环和受控飞书测试群 live sandbox 已经成型，但不能写成生产部署、全量飞书空间接入或 productized live。
4. 三个用户关心的问题的短答案是：MVP 可演示闭环已完成；Feishu Memory Copilot 已接入受控飞书测试群；OpenClaw 产品形态已完成本地/受控 E2E 测试，但还没完成生产级 OpenClaw + 飞书全量上线。
5. Phase A 已补齐 storage migration 和 audit table；接下来补的不是“再做一个 demo”，而是真实 OpenClaw runtime 证据、Feishu staging 边界和 live embedding 验证。
6. 所有未完成任务仍由程俊豪负责，任务完成前不要把 dry-run、replay、测试群 sandbox 写成生产 live。

## 结论总览

| 问题 | 当前判断 | 证据 | 不能 overclaim 的边界 |
|---|---|---|---|
| 是否完成 MVP 构建？ | 已完成可演示、可本地复现、可评测的 MVP 闭环；Phase A storage/audit 本地迁移已完成。 | `python3 scripts/check_demo_readiness.py --json` 通过；5 个 demo replay step 全部 pass；benchmark 六类能力全部有 runner；`python3 scripts/check_copilot_health.py --json` 中 `storage_schema.status=pass`、`audit_smoke.status=pass`。 | 不是生产部署；不是完整多租户后台；真实 OpenClaw runtime 证据和 staging runbook 仍未完成。 |
| Feishu Memory Copilot 是否接入飞书？ | 已接入受控旧飞书测试群 live sandbox，真实群消息会进入新 Copilot live 路径。 | `memory_engine/copilot/feishu_live.py`、`scripts/start_copilot_feishu_live.sh`、`tests/test_copilot_feishu_live.py`；handoff 记录 `/health`、`/remember`、`/confirm`、普通 @ 提问四步。 | 不是全量 Feishu workspace ingestion；不是生产推送；真实 ID 不进入仓库。 |
| 是否接入 OpenClaw 做完整产品形态测试？ | 已完成 OpenClaw tool schema、examples、本地 bridge、demo replay 和受控 live bridge 测试；达到 demo/pre-production 产品形态。 | `agent_adapters/openclaw/memory_tools.schema.json` 有 7 个工具；`handle_tool_request()` 统一到 `CopilotService`；healthcheck 的 schema/service/smoke tests 通过。 | 还缺真实 OpenClaw Agent runtime 的独立验收记录、生产安装包和长期运行监控。 |

## PRD 要求完成度核对

| PRD 要求 | 当前状态 | 当前证据 | 剩余动作 |
|---|---|---|---|
| `memory.search` 默认只返回 active memory，Top 3 带 evidence 和 trace | 完成 | `benchmarks/copilot_recall_cases.json`：10 条，Recall@3 = 1.0，Evidence Coverage = 1.0，Stale Leakage = 0.0。 | 后续扩大真实飞书表达样例，不删除失败样例。 |
| 自动识别 candidate，普通闲聊不乱记 | 完成 | `benchmarks/copilot_candidate_cases.json`：34 条，Candidate Precision = 1.0，false_positive_candidate = 0。 | 增加真实测试群消息样本的人工复核集。 |
| `memory.confirm` / `memory.reject` 经过治理层 | 完成 | healthcheck candidate review smoke test：candidate -> active；card action 测试走 `handle_tool_request()`；Phase A 已写 audit table。 | 生产前仍需做真实 OpenClaw runtime 和 Feishu staging 证据。 |
| 冲突更新和版本解释 | 完成 | `benchmarks/copilot_conflict_cases.json`：12 条，Conflict Accuracy = 1.0，Superseded Leakage = 0.0。 | 真实飞书来源场景继续保留 candidate-only，不自动覆盖 active。 |
| `memory.prefetch` 给 Agent 任务前上下文包 | 完成 | `benchmarks/copilot_prefetch_cases.json`：6 条，Agent Task Context Use Rate = 1.0，Evidence Coverage = 1.0。 | 在真实 OpenClaw Agent runtime 中补三条任务前调用证据。 |
| Heartbeat 主动提醒 | MVP 原型完成 | `benchmarks/copilot_heartbeat_cases.json`：7 条，Sensitive Reminder Leakage Rate = 0.0；只生成 reminder candidate。 | 不做真实群推送，直到权限、频率和审计闭环完成。 |
| Feishu card / Bitable review surface | 本地闭环完成 | `tests/test_feishu_interactive_cards.py`、`tests/test_bitable_sync.py`；card/Bitable dry-run 消费 service/tool 输出；Phase A 已补 audit table。 | 接真实 card action 前还需补 staging runbook 和可交接流程。 |
| OpenClaw E2E flows >= 2 | Demo/pre-production 完成 | demo replay 5 step pass；OpenClaw schema 7 tools；examples 覆盖 search、version、prefetch、heartbeat、permission denied。 | 补真实 OpenClaw runtime 验收记录，避免只停留在 local bridge。 |
| Evaluation report | 完成 MVP 报告 | `docs/benchmark-report.md` 覆盖 recall、candidate、conflict、layer、prefetch、heartbeat。 | 复赛前扩样例规模和真实飞书项目群表达。 |
| 生产部署和长期运行 | 未完成 | README、handoff、healthcheck 都明确声明不是 productized live。 | 进入后续产品化任务，不在 MVP 阶段冒称完成。 |

## 本轮重新跑过的验证证据

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_copilot_health.py --json
python3 scripts/check_demo_readiness.py --json
python3 -m unittest tests.test_copilot_feishu_live tests.test_demo_readiness tests.test_demo_seed
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_layer_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
```

结果摘要：

- OpenClaw version OK：`2026.4.24`。
- Healthcheck：`ok=true`；`fail=0`；`pass=5`；`warning=2`；`fallback_used=1`。
- Demo readiness：`ok=true`；demo replay `step_count=5`，`failed_steps=[]`；provider 仍是 configuration-only warning。
- Feishu live / demo 单测：14 tests OK。
- Benchmark：recall 10/10、candidate 34/34、conflict 12/12、layer 15/15、prefetch 6/6、heartbeat 7/7 全部通过。

## 已完成任务

| 任务 | 优先级 | 负责人 | 完成时间 | 文件/页面位置 | 完成标准 |
|---|---|---|---|---|---|
| 补 storage migration 和 audit table | P0 | 程俊豪 | 2026-04-28 | `memory_engine/db.py`、`memory_engine/copilot/service.py`、`memory_engine/copilot/healthcheck.py`、[Phase A handoff](phase-a-storage-audit-handoff.md) | 数据库有 `tenant_id`、`organization_id`、`visibility_policy` 和 `memory_audit_events`；healthcheck 不再报 storage warning；确认/拒绝/权限拒绝、limited ingestion candidate、heartbeat candidate 都有审计记录。 |

## 仍未完成任务拆分

| 任务 | 优先级 | 负责人 | 截止建议 | 文件/页面位置 | 完成标准 |
|---|---|---|---|---|---|
| 补真实 OpenClaw Agent runtime 验收记录 | P0 | 程俊豪 | 2026-05-09 | `agent_adapters/openclaw/`、`docs/demo-runbook.md`、新增 runtime evidence 文档 | 在真实 OpenClaw Agent runtime 中跑通至少 3 条：历史召回、candidate 确认、任务前 prefetch；记录输入、输出、request_id、trace_id 和失败回退。 |
| 把 Feishu live sandbox 升级成 staging runbook | P0 | 程俊豪 | 2026-05-10 | `scripts/start_copilot_feishu_live.sh`、`memory_engine/copilot/feishu_live.py`、`docs/reference/local-lark-cli-setup.md` | 明确 allowlist、reviewer、日志、退出、权限失败处理；真实 ID 只进本机环境；README 继续声明不是全量 workspace ingestion。 |
| 验证 live Cognee / Ollama embedding，不再只做 configuration-only | P1 | 程俊豪 | 2026-05-10 | `scripts/check_embedding_provider.py`、`scripts/spike_cognee_local.py`、`memory_engine/copilot/cognee_adapter.py` | 能跑真实 provider 检查；若失败，文档写清 fallback；每次运行后 `ollama ps` 无本项目模型驻留或记录保留原因。 |
| 做 no-overclaim 交付物审查 | P1 | 程俊豪 | 2026-05-10 | `README.md`、`docs/demo-runbook.md`、`docs/benchmark-report.md`、`docs/memory-definition-and-architecture-whitepaper.md` | 所有材料统一口径：已完成 demo/pre-production 和测试群 sandbox；未完成生产部署、全量 ingestion、多租户后台和 productized live。 |

## 对外汇报口径

可以说：

- 已完成 Feishu Memory Copilot 的 MVP demo/pre-production 闭环。
- 已通过 OpenClaw tool schema、本地 bridge、demo replay、benchmark 和受控飞书测试群验证核心产品形态。
- 已接入飞书测试群 live sandbox，真实消息会进入新的 `CopilotService` 路径，不再走旧 Bot handler 作为主架构。

不要说：

- 已生产上线。
- 已全量接入飞书 workspace。
- 已完成多租户企业后台。
- 已完成真实 embedding 默认门禁。
- 已完成 productized live 长期运行。
