# PRD Completion Audit and Gap Tasks

日期：2026-04-28
当前事实源：仓库代码、PRD、主控计划、README、handoff、healthcheck 和本轮本地验证命令。

## 先看这个

1. 今天的真实日期是 2026-04-28；仓库里已经存在 2026-05-03 到 2026-05-08 的计划、handoff 和交付文档，本审计按“当前仓库状态”核对完成度。
2. 2026-05-05 及以前的 implementation plan 已经全部完成，不再需要执行；它们只保留为历史计划、验收证据和风险参考。
3. 当前可以判断：MVP 的本地可复现闭环和受控飞书测试群 live sandbox 已经成型，但不能写成生产部署、全量飞书空间接入或 productized live。
4. 三个用户关心的问题的短答案是：MVP 可演示闭环已完成；Feishu Memory Copilot 已接入受控飞书测试群；OpenClaw 产品形态已完成本地/受控 E2E 测试，但还没完成生产级 OpenClaw + 飞书全量上线。
5. Phase A 已补齐 storage migration 和 audit table；Phase B 已补真实 OpenClaw Agent runtime 受控证据；Phase D 已补 live Cognee / Ollama embedding gate；Phase E 已完成 no-overclaim 审查；后期打磨已补 first-class OpenClaw tool registry、OpenClaw Feishu websocket running 本机 staging 证据、P1 生产存储/索引/迁移方案、真实飞书权限映射和 limited Feishu ingestion 本地底座。
6. 所有未完成任务仍由程俊豪负责，后续不要把 dry-run、replay、测试群 sandbox、live embedding gate 写成生产 live。

## 结论总览

| 问题 | 当前判断 | 证据 | 不能 overclaim 的边界 |
|---|---|---|---|
| 是否完成 MVP 构建？ | 已完成可演示、可本地复现、可评测的 MVP 闭环；Phase A storage/audit 本地迁移、Phase B runtime 受控证据、first-class OpenClaw tool registry 和 websocket staging 证据已完成。 | `python3 scripts/check_demo_readiness.py --json` 通过；5 个 demo replay step 全部 pass；benchmark 六类能力全部有 runner；`python3 scripts/check_copilot_health.py --json` 中 `storage_schema.status=pass`、`audit_smoke.status=pass`、`openclaw_native_registry.status=pass`；OpenClaw Agent run `b252f11e-b49d-495c-a14f-0b823a888a5e` 通过三条 flow；`openclaw plugins inspect feishu-memory-copilot --json` 读回 7 个 `toolNames`；`python3 scripts/check_openclaw_feishu_websocket.py --json --timeout 45` 返回 `ok=true`。 | 不是生产部署；不是完整多租户后台；真实 Feishu DM 到项目 first-class `memory.*` tool routing 仍未完成。 |
| Feishu Memory Copilot 是否接入飞书？ | 已接入受控旧飞书测试群 live sandbox，真实群消息会进入新 Copilot live 路径。 | `memory_engine/copilot/feishu_live.py`、`scripts/start_copilot_feishu_live.sh`、`tests/test_copilot_feishu_live.py`；handoff 记录 `/health`、`/remember`、`/confirm`、普通 @ 提问四步。 | 不是全量 Feishu workspace ingestion；不是生产推送；真实 ID 不进入仓库。 |
| 是否接入 OpenClaw 做完整产品形态测试？ | 已完成 OpenClaw tool schema、examples、本地 bridge、demo replay、受控 live bridge、Agent runtime 受控验收、first-class tool registry 本机证据、websocket staging running 证据和 live embedding gate；达到 demo/pre-production 产品形态。 | `agent_adapters/openclaw/memory_tools.schema.json` 有 7 个工具；`handle_tool_request()` 统一到 `CopilotService`；healthcheck 的 schema/service/smoke/registry tests 通过；Phase B evidence 记录真实 `openclaw agent` run id；`feishu-memory-copilot` 插件读回 7 个 toolNames；Phase D gate 真实返回 1024 维 embedding；websocket check 证明真实 DM 已进入 OpenClaw Agent dispatch。 | 还缺真实 Feishu DM 到项目 first-class `memory.*` tool routing、生产安装包和长期运行监控。 |

## PRD 要求完成度核对

| PRD 要求 | 当前状态 | 当前证据 | 剩余动作 |
|---|---|---|---|
| `memory.search` 默认只返回 active memory，Top 3 带 evidence 和 trace | 完成 | `benchmarks/copilot_recall_cases.json`：10 条，Recall@3 = 1.0，Evidence Coverage = 1.0，Stale Leakage = 0.0。 | 后续扩大真实飞书表达样例，不删除失败样例。 |
| 自动识别 candidate，普通闲聊不乱记 | 完成 | `benchmarks/copilot_candidate_cases.json`：34 条，Candidate Precision = 1.0，false_positive_candidate = 0。 | 增加真实测试群消息样本的人工复核集。 |
| `memory.confirm` / `memory.reject` 经过治理层 | 完成 | healthcheck candidate review smoke test：candidate -> active；card action 测试走 `handle_tool_request()`；Phase A 已写 audit table；Phase B runtime evidence 已跑 candidate -> confirm。 | 生产前仍需 no-overclaim 审查和长期运行设计。 |
| 冲突更新和版本解释 | 完成 | `benchmarks/copilot_conflict_cases.json`：12 条，Conflict Accuracy = 1.0，Superseded Leakage = 0.0。 | 真实飞书来源场景继续保留 candidate-only，不自动覆盖 active。 |
| `memory.prefetch` 给 Agent 任务前上下文包 | 完成 | `benchmarks/copilot_prefetch_cases.json`：6 条，Agent Task Context Use Rate = 1.0，Evidence Coverage = 1.0；Phase B runtime evidence 已跑 `task_prefetch_context_pack`。 | 后续扩大真实任务表达样例，不删除失败样例。 |
| Heartbeat 主动提醒 | MVP 原型完成 | `benchmarks/copilot_heartbeat_cases.json`：7 条，Sensitive Reminder Leakage Rate = 0.0；只生成 reminder candidate。 | 不做真实群推送，直到权限、频率和审计闭环完成。 |
| Feishu card / Bitable review surface | 本地闭环完成 | `tests/test_feishu_interactive_cards.py`、`tests/test_bitable_sync.py`；card/Bitable dry-run 消费 service/tool 输出；Phase A 已补 audit table。 | 接真实 card action 前还需补 staging runbook 和可交接流程。 |
| OpenClaw E2E flows >= 2 | 受控 runtime 证据、first-class registry 本机证据和 websocket staging running 证据完成 | demo replay 5 step pass；OpenClaw schema 7 tools；examples 覆盖 search、version、prefetch、heartbeat、permission denied；Phase B OpenClaw Agent run `b252f11e-b49d-495c-a14f-0b823a888a5e` 通过 `exec` 调用证据脚本，三条 Copilot flow 全部 `ok=true`；`openclaw plugins inspect feishu-memory-copilot --json` 读回 7 个 `toolNames`；websocket check 证明真实 DM 已进入 OpenClaw Agent dispatch。 | 后续还需真实飞书消息进入 OpenClaw Agent 后自然选择本项目 first-class `memory.*` 工具。 |
| Evaluation report | 完成 MVP 报告 | `docs/benchmark-report.md` 覆盖 recall、candidate、conflict、layer、prefetch、heartbeat。 | 复赛前扩样例规模和真实飞书项目群表达。 |
| 生产部署和长期运行 | 未完成 | README、handoff、healthcheck 都明确声明不是 productized live。 | 进入后续产品化任务，不在 MVP 阶段冒称完成。 |

## 本轮重新跑过的验证证据

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_copilot_health.py --json
python3 scripts/check_demo_readiness.py --json
python3 scripts/check_live_embedding_gate.py --json
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
- Phase D live embedding gate：`ok=true`；model=`ollama/qwen3-embedding:0.6b-fp16`；actual_dimensions=1024；Cognee dry-run pass；`ollama_cleanup.running_after_cleanup=[]`。
- Feishu live / demo 单测：14 tests OK。
- Benchmark：recall 10/10、candidate 34/34、conflict 12/12、layer 15/15、prefetch 6/6、heartbeat 7/7 全部通过。

## 已完成任务

| 任务 | 优先级 | 负责人 | 完成时间 | 文件/页面位置 | 完成标准 |
|---|---|---|---|---|---|
| 补 storage migration 和 audit table | P0 | 程俊豪 | 2026-04-28 | `memory_engine/db.py`、`memory_engine/copilot/service.py`、`memory_engine/copilot/healthcheck.py`、[Phase A handoff](phase-a-storage-audit-handoff.md) | 数据库有 `tenant_id`、`organization_id`、`visibility_policy` 和 `memory_audit_events`；healthcheck 不再报 storage warning；确认/拒绝/权限拒绝、limited ingestion candidate、heartbeat candidate 都有审计记录。 |
| 补 Feishu 单监听 staging 流程 | P0 | 程俊豪 | 2026-04-28 | `scripts/check_feishu_listener_singleton.py`、`memory_engine/feishu_listener_guard.py`、[Feishu staging runbook](feishu-staging-runbook.md)、[single listener handoff](feishu-single-listener-handoff.md) | OpenClaw Feishu websocket、Copilot lark-cli sandbox、legacy fallback 三选一；repo 内启动脚本和 direct CLI 启动前都会做 singleton preflight；冲突时记录 pid、kind、command。 |
| 补真实 OpenClaw Agent runtime 验收记录 | P0 | 程俊豪 | 2026-04-28 | `scripts/openclaw_runtime_evidence.py`、[Phase B evidence](openclaw-runtime-evidence.md)、[Phase B handoff](phase-b-openclaw-runtime-handoff.md) | OpenClaw Agent run `b252f11e-b49d-495c-a14f-0b823a888a5e` 通过；三条 flow：`memory.search`、`memory.create_candidate + memory.confirm`、`memory.prefetch` 都有 request_id、trace_id、permission_decision=allow；边界写清不是 production live、不是全量 Feishu ingestion。 |
| 验证 live Cognee / Ollama embedding，不再只做 configuration-only | P1 | 程俊豪 | 2026-04-28 | `scripts/check_live_embedding_gate.py`、`scripts/check_embedding_provider.py`、`scripts/spike_cognee_local.py`、[Phase D handoff](phase-d-live-embedding-handoff.md) | 真实 provider 检查通过；`ollama/qwen3-embedding:0.6b-fp16` 返回 1024 维；Cognee dry-run adapter 路径通过；每次运行后 `ollama ps` 无本项目模型驻留。 |
| 实现 `memory.*` first-class OpenClaw 原生工具注册 | P0 | 程俊豪 | 2026-04-28 | `agent_adapters/openclaw/plugin/`、`agent_adapters/openclaw/tool_registry.py`、`memory_engine/copilot/openclaw_tool_runner.py`、[first-class tools handoff](first-class-openclaw-tools-handoff.md) | `feishu-memory-copilot` 插件可安装启用；`openclaw plugins inspect feishu-memory-copilot --json` 读回 7 个 `toolNames`；runner 调用仍进入 `handle_tool_request()` / `CopilotService` 并保留 bridge metadata。 |
| 补 OpenClaw Feishu websocket running 本机 staging 证据 | P0 | 程俊豪 | 2026-04-28 | `scripts/check_openclaw_feishu_websocket.py`、`tests/test_openclaw_feishu_websocket_evidence.py`、[websocket handoff](openclaw-feishu-websocket-handoff.md)、[Feishu staging runbook](feishu-staging-runbook.md) | `channels.status` 显示 Feishu channel 和 default account running；真实 DM 已进入 OpenClaw Agent dispatch；没有 repo 内 lark-cli listener 冲突；health running 字段不一致写为 warning；真实 ID 不写仓库。 |
| 补生产存储、索引和迁移方案 | P1 | 程俊豪 | 2026-04-28 | `memory_engine/storage_migration.py`、`scripts/migrate_copilot_storage.py`、`memory_engine/copilot/healthcheck.py`、[storage migration handoff](storage-migration-productization-handoff.md) | dry-run 不改库并报告缺失表/列/索引；apply 可重复执行；healthcheck 报告 schema version、index status、audit status；文档写清 SQLite 与托管 PostgreSQL 试点边界、备份恢复、审计保留和数据删除策略。 |
| 补真实飞书权限映射 | P0 | 程俊豪 | 2026-04-28 | `memory_engine/copilot/permissions.py`、`memory_engine/copilot/feishu_live.py`、`memory_engine/copilot/governance.py`、[permission mapping handoff](real-feishu-permission-mapping-handoff.md) | 非 demo tenant/org 在目标上下文一致时允许；tenant/org/private/source context mismatch fail closed；真实飞书 candidate 写入 tenant/org/visibility ledger；deny 不返回明文 evidence/current_value。 |
| 补 limited Feishu ingestion 本地底座 | P1 | 程俊豪 | 2026-04-28 | `memory_engine/document_ingestion.py`、`memory_engine/copilot/schemas.py`、[limited ingestion handoff](limited-feishu-ingestion-handoff.md) | 群聊、文档、任务、会议、Bitable 来源文本可进入 candidate-only pipeline；每类来源保留 source metadata 和 evidence quote；source context mismatch fail closed；source revoked 后 active memory 标记 stale 并从默认 recall 隐藏。 |
| 补 Cognee 主路径本地闭环 | P1 | 程俊豪 | 2026-04-28 | `memory_engine/copilot/cognee_adapter.py`、`memory_engine/copilot/service.py`、`memory_engine/copilot/retrieval.py`、[Cognee 主路径 handoff](cognee-main-path-handoff.md) | confirm 后只同步 curated memory fields 和 ledger metadata 到 Cognee add -> cognify；reject 会 withdrawal；未匹配 ledger 的 Cognee result 不进入正式 answer；同步失败时 repository fallback 清楚可见。 |

## 仍未完成任务拆分

| 任务 | 优先级 | 负责人 | 截止建议 | 文件/页面位置 | 完成标准 |
|---|---|---|---|---|---|
当前 P1 no-overclaim 审查已完成，剩余项只在继续产品化时启动：

| 任务 | 优先级 | 负责人 | 截止建议 | 文件/页面位置 | 完成标准 |
|---|---|---|---|---|---|
| 打通真实 Feishu DM 到本项目 first-class `memory.*` tool routing | P1 | 程俊豪 | 待定 | `agent_adapters/openclaw/plugin/`、`memory_engine/copilot/openclaw_tool_runner.py`、`docs/productization/openclaw-feishu-websocket-handoff.md` | 真实 Feishu DM 进入 OpenClaw Agent 后自然选择本项目 `memory.search` / `memory.prefetch` 等工具，并进入 `handle_tool_request()`；回复保留 request_id、trace_id、permission_decision；仍保持 candidate-only 和 permission fail-closed。 |
| 接真实 Feishu API 拉取和扩充人工复核样本 | P1 | 程俊豪 | 待定 | `memory_engine/copilot/feishu_live.py`、`memory_engine/document_ingestion.py`、`memory_engine/bitable_sync.py`、`docs/productization/feishu-staging-runbook.md` | 在 limited ingestion 底座之上，接任务、会议、Bitable 等真实 API 拉取；lark-cli / OpenAPI 失败时有明确 fallback，不冒称 live 成功；增加真实测试群消息样本的人工复核集。 |
| 设计 productized live 长期运行方案 | P2 | 程俊豪 | 待定 | `docs/productization/full-copilot-next-execution-doc.md` 或后续 handoff | 写清部署、监控、回滚、权限后台、审计 UI 和运维边界；本阶段不把它写成已完成。 |

## Phase E 已完成审查

| 任务 | 优先级 | 负责人 | 完成时间 | 文件/页面位置 | 完成标准 |
|---|---|---|---|---|---|
| 做 no-overclaim 交付物审查 | P1 | 程俊豪 | 2026-04-28 | `README.md`、`docs/demo-runbook.md`、`docs/benchmark-report.md`、`docs/memory-definition-and-architecture-whitepaper.md`、[Phase E handoff](phase-e-no-overclaim-handoff.md) | 所有材料统一口径：已完成 demo/pre-production、受控测试群 sandbox、OpenClaw Agent runtime 受控证据和 Phase D live embedding gate；后续 first-class registry 和 websocket staging 证据已补本机证据；未完成生产部署、全量 ingestion、多租户后台、长期 embedding 服务、Feishu tool routing 和 productized live。 |

## 对外汇报口径

可以说：

- 已完成 Feishu Memory Copilot 的 MVP demo/pre-production 闭环。
- 已通过 OpenClaw tool schema、本地 bridge、demo replay、benchmark 和受控飞书测试群验证核心产品形态。
- 已接入飞书测试群 live sandbox，真实消息会进入新的 `CopilotService` 路径，不再走旧 Bot handler 作为主架构。
- 已完成 live embedding gate：本机 Ollama `qwen3-embedding:0.6b-fp16` 真实返回 1024 维，并在验证后清理模型驻留。

不要说：

- 已生产上线。
- 已全量接入飞书 workspace。
- 已完成多租户企业后台。
- 已完成真实 embedding 默认门禁。
- 已完成长期 embedding 服务。
- 已完成真实 Feishu DM 到本项目 first-class `memory.*` tool routing。
- 已完成 productized live 长期运行。
