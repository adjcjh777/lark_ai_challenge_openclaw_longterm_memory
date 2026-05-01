# PRD Completion Audit and Gap Tasks

日期：2026-04-28
当前事实源：仓库代码、PRD、主控计划、README、handoff、healthcheck 和本轮本地验证命令。

## 先看这个

1. 今天的真实日期是 2026-04-28；仓库里已经存在 2026-05-03 到 2026-05-08 的计划、handoff 和交付文档，本审计按“当前仓库状态”核对完成度。
2. 2026-05-05 及以前的 implementation plan 已经全部完成，不再需要执行；它们只保留为历史计划、验收证据和风险参考。
3. 当前可以判断：MVP 的本地可复现闭环和受控飞书测试群 live sandbox 已经成型，但不能写成生产部署、全量飞书空间接入或 productized live。
4. 三个用户关心的问题的短答案是：MVP 可演示闭环已完成；Feishu Memory Copilot 已接入受控飞书测试群；OpenClaw 产品形态已完成本地/受控 E2E 测试，但还没完成生产级 OpenClaw + 飞书全量上线。
5. Phase A 已补齐 storage migration 和 audit table；Phase B 已补真实 OpenClaw Agent runtime 受控证据；Phase D 已补 live Cognee / Ollama embedding gate；Phase E 已完成 no-overclaim 审查；后期打磨已补 first-class OpenClaw tool registry、Agent 本地 `fmc_*` 工具调用验证、OpenClaw Feishu websocket running 本机 staging 证据、一次受控真实 Feishu DM `fmc_memory_search` allow-path live E2E 证据、P1 生产存储/索引/迁移方案、真实飞书权限映射、limited Feishu ingestion 本地底座、真实 Feishu API review-policy 拉取入口、审计查询/告警/运维 healthcheck 面、productized live 长期运行方案、真实飞书可点击卡片的受控 sandbox/pre-production 路径、Feishu 群/用户/消息作为企业图谱拓扑的本地发现能力、OpenClaw gateway 本地不 @ 静默候选筛选入口、审核卡片 publisher 层 DM/private 定向投递、群级设置/启停策略，以及本地/pre-production LLM Wiki / Graph Admin tenant policy editor。
6. 所有未完成任务仍由程俊豪负责，后续不要把 dry-run、replay、测试群 sandbox、live embedding gate 写成生产 live。

## 结论总览

| 问题 | 当前判断 | 证据 | 不能 overclaim 的边界 |
|---|---|---|---|
| 是否完成 MVP 构建？ | 已完成可演示、可本地复现、可评测的 MVP 闭环；Phase A storage/audit 本地迁移、Phase B runtime 受控证据、first-class OpenClaw tool registry、Agent 本地 `fmc_*` 工具调用验证、websocket staging 证据和一次受控真实 DM allow-path 证据已完成。 | `python3 scripts/check_demo_readiness.py --json` 通过；5 个 demo replay step 全部 pass；benchmark 六类能力全部有 runner；`python3 scripts/check_copilot_health.py --json` 中 `storage_schema.status=pass`、`audit_smoke.status=pass`、`openclaw_native_registry.status=pass`；OpenClaw Agent run `b252f11e-b49d-495c-a14f-0b823a888a5e` 通过三条 flow；`openclaw plugins inspect feishu-memory-copilot --json` 读回 7 个 `toolNames`；`scripts/check_feishu_dm_routing.py` 验证本地 Agent 可见 `fmc_*` 工具；`python3 scripts/check_openclaw_feishu_websocket.py --json --timeout 45` 返回 `ok=true`；2026-04-29 11:04 真实 DM 触发 `fmc_memory_search`，11:07 机器人回复读回 `request_id=req_feishu_dm_live_20260429_1104`、`trace_id=trace_feishu_dm_live_20260429_1104`、`permission_decision=allow/scope_access_granted`。 | 不是生产部署；不是完整多租户后台；不能把一次受控 DM 证据写成稳定长期路由。 |
| Feishu Memory Copilot 是否接入飞书？ | 已接入受控旧飞书测试群 live sandbox，真实群消息会进入新 Copilot live 路径；定向审核卡片已在 publisher 层改为 DM/private 发送；群级设置/启停策略已有本地/pre-production 闭环：新群默认 pending_onboarding，显式启用后才做静默候选筛选。 | `memory_engine/copilot/feishu_live.py`、`memory_engine/copilot/group_policies.py`、`memory_engine/feishu_publisher.py`、`memory_engine/feishu_cards.py`、`scripts/start_copilot_feishu_live.sh`、`tests/test_copilot_feishu_live.py`、`tests/test_feishu_publisher.py`。 | 不是全量 Feishu workspace ingestion；不是生产推送；真实 ID 不进入仓库；DM 投递仍需受控真实环境读回。 |
| 是否接入 OpenClaw 做完整产品形态测试？ | 已完成 OpenClaw tool schema、examples、本地 bridge、demo replay、受控 live bridge、Agent runtime 受控验收、first-class tool registry 本机证据、Agent 本地 `fmc_*` 工具调用验证、websocket staging running 证据、一次受控真实 DM allow-path 证据和 live embedding gate；达到 demo/pre-production 产品形态。 | `agent_adapters/openclaw/memory_tools.schema.json` 有 7 个 OpenClaw-facing `fmc_*` 工具；`handle_tool_request()` 统一到 `CopilotService`；healthcheck 的 schema/service/smoke/registry tests 通过；Phase B evidence 记录真实 `openclaw agent` run id；`feishu-memory-copilot` 插件读回 7 个 toolNames；`tests.test_feishu_dm_routing` 覆盖 `fmc_* -> memory.*` 翻译和 bridge metadata；Phase D gate 真实返回 1024 维 embedding；websocket check 证明真实 DM 已进入 OpenClaw Agent dispatch；2026-04-29 11:04 真实 DM 进入 `fmc_memory_search` 并读回 allow-path 结果。 | 还缺生产安装包、生产级长期监控，以及更多真实 DM 工具动作和稳定性验收。 |

## PRD 要求完成度核对

| PRD 要求 | 当前状态 | 当前证据 | 剩余动作 |
|---|---|---|---|
| `memory.search` 默认只返回 active memory，Top 3 带 evidence 和 trace | 完成 | `benchmarks/copilot_recall_cases.json`：10 条，Recall@3 = 1.0，Evidence Coverage = 1.0，Stale Leakage = 0.0。 | 后续扩大真实飞书表达样例，不删除失败样例。 |
| 自动识别 candidate，普通闲聊不乱记 | 完成 | `benchmarks/copilot_candidate_cases.json`：34 条，Candidate Precision = 1.0，false_positive_candidate = 0。 | 增加真实测试群消息样本的人工复核集。 |
| `memory.confirm` / `memory.reject` 经过治理层 | 完成 | healthcheck candidate review smoke test：candidate -> active；card action 测试走 `handle_tool_request()`；Phase A 已写 audit table；Phase B runtime evidence 已跑 candidate -> confirm。 | 生产前仍需 no-overclaim 审查和长期运行设计。 |
| 冲突更新和版本解释 | 完成 | `benchmarks/copilot_conflict_cases.json`：12 条，Conflict Accuracy = 1.0，Superseded Leakage = 0.0。 | 真实飞书来源场景继续保留 review-policy gate；冲突内容不自动覆盖 active。 |
| `memory.prefetch` 给 Agent 任务前上下文包 | 完成 | `benchmarks/copilot_prefetch_cases.json`：6 条，Agent Task Context Use Rate = 1.0，Evidence Coverage = 1.0；Phase B runtime evidence 已跑 `task_prefetch_context_pack`。 | 后续扩大真实任务表达样例，不删除失败样例。 |
| Heartbeat 主动提醒 | MVP 原型完成 | `benchmarks/copilot_heartbeat_cases.json`：7 条，Sensitive Reminder Leakage Rate = 0.0；只生成 reminder candidate。 | 不做真实群推送，直到权限、频率和审计闭环完成。 |
| Feishu card / Bitable review surface | 本地闭环完成；真实飞书可点击卡片已完成受控 sandbox/pre-production 路径，审核卡片 publisher 层已支持 DM/private 定向投递，Bitable 写回已补幂等和读回确认 | `tests/test_feishu_interactive_cards.py`、`tests/test_copilot_feishu_live.py`、`tests/test_feishu_publisher.py`、`tests/test_bitable_sync.py`、`scripts/check_feishu_review_delivery_gate.py`；Feishu live interactive 回复使用 typed card；候选审核卡点击确认、拒绝、要求补证据、标记过期后回到当前 operator 权限上下文，并通过 `handle_tool_request()` / `CopilotService`；定向卡片逐个 `open_id/user_id` 发送 DM，失败 fallback 不回群；缺 Feishu card update token 的 card action 会 fail closed，不执行状态变更；Candidate Review / Reminder Candidate 写回带稳定 `sync_key`，非 dry-run 写入前查已有记录，写后读回确认；Phase A 已补 audit table。 | 仍不能说真实飞书 card action 已完成生产级长期运行；DM 投递仍需受控真实环境读回。 |
| OpenClaw E2E flows >= 2 | 受控 runtime 证据、first-class registry 本机证据、Agent 本地 `fmc_*` 工具调用验证、websocket staging running 证据和一次受控真实 DM allow-path 证据完成 | demo replay 5 step pass；OpenClaw schema 7 个 `fmc_*` tools；examples 覆盖 search、version、prefetch、heartbeat、permission denied；Phase B OpenClaw Agent run `b252f11e-b49d-495c-a14f-0b823a888a5e` 通过 `exec` 调用证据脚本，三条 Copilot flow 全部 `ok=true`；`openclaw plugins inspect feishu-memory-copilot --json` 读回 7 个 `toolNames`；`scripts/check_feishu_dm_routing.py` 验证本地 Agent 可见并可调用 `fmc_memory_search`；websocket check 证明真实 DM 已进入 OpenClaw Agent dispatch；2026-04-29 11:04 真实 DM allow-path 读回 5 条命中和 bridge metadata。 | 后续还需固化评委/用户主路径，并扩大到 `prefetch` / `create_candidate` 等真实 DM 工具动作。 |
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
| 补 Feishu 单监听 staging 流程 | P0 | 程俊豪 | 2026-04-28 | `scripts/check_feishu_listener_singleton.py`、`memory_engine/feishu_listener_guard.py`、[Feishu staging runbook](feishu-staging-runbook.md)、[single listener handoff](feishu-single-listener-handoff.md) | OpenClaw Feishu websocket、Copilot lark-cli sandbox、legacy fallback 三选一；repo 内启动脚本和 direct CLI 启动前都会做 singleton preflight；泛化 `openclaw-gateway` 对 repo lark-cli planned listener fail closed，只允许 OpenClaw planned owner 继续做 channel/log 验证；冲突时记录 pid、kind、command。 |
| 补真实 OpenClaw Agent runtime 验收记录 | P0 | 程俊豪 | 2026-04-28 | `scripts/openclaw_runtime_evidence.py`、[Phase B evidence](openclaw-runtime-evidence.md)、[Phase B handoff](phase-b-openclaw-runtime-handoff.md) | OpenClaw Agent run `b252f11e-b49d-495c-a14f-0b823a888a5e` 通过；三条 flow：`memory.search`、`memory.create_candidate + memory.confirm`、`memory.prefetch` 都有 request_id、trace_id、permission_decision=allow；边界写清不是 production live、不是全量 Feishu ingestion。 |
| 验证 live Cognee / Ollama embedding，不再只做 configuration-only | P1 | 程俊豪 | 2026-04-28 | `scripts/check_live_embedding_gate.py`、`scripts/check_embedding_provider.py`、`scripts/spike_cognee_local.py`、[Phase D handoff](phase-d-live-embedding-handoff.md) | 真实 provider 检查通过；`ollama/qwen3-embedding:0.6b-fp16` 返回 1024 维；Cognee dry-run adapter 路径通过；每次运行后 `ollama ps` 无本项目模型驻留。 |
| 实现 `memory.*` first-class OpenClaw 原生工具注册 | P0 | 程俊豪 | 2026-04-28 | `agent_adapters/openclaw/plugin/`、`agent_adapters/openclaw/tool_registry.py`、`memory_engine/copilot/openclaw_tool_runner.py`、[first-class tools handoff](first-class-openclaw-tools-handoff.md) | `feishu-memory-copilot` 插件可安装启用；`openclaw plugins inspect feishu-memory-copilot --json` 读回 7 个 `toolNames`；runner 调用仍进入 `handle_tool_request()` / `CopilotService` 并保留 bridge metadata。 |
| 补 OpenClaw Feishu websocket running 本机 staging 证据 | P0 | 程俊豪 | 2026-04-28 | `scripts/check_openclaw_feishu_websocket.py`、`tests/test_openclaw_feishu_websocket_evidence.py`、[websocket handoff](openclaw-feishu-websocket-handoff.md)、[Feishu staging runbook](feishu-staging-runbook.md) | `channels.status` 显示 Feishu channel 和 default account running；真实 DM 已进入 OpenClaw Agent dispatch；没有 repo 内 lark-cli listener 冲突；health running 字段不一致写为 warning；真实 ID 不写仓库。 |
| 补生产存储、索引和迁移方案 | P1 | 程俊豪 | 2026-04-28 | `memory_engine/storage_migration.py`、`scripts/migrate_copilot_storage.py`、`memory_engine/copilot/healthcheck.py`、[storage migration handoff](storage-migration-productization-handoff.md) | dry-run 不改库并报告缺失表/列/索引；apply 可重复执行；healthcheck 报告 schema version、index status、audit status；文档写清 SQLite 与托管 PostgreSQL 试点边界、备份恢复、审计保留和数据删除策略。 |
| 补真实飞书权限映射 | P0 | 程俊豪 | 2026-04-28 | `memory_engine/copilot/permissions.py`、`memory_engine/copilot/feishu_live.py`、`memory_engine/copilot/governance.py`、[permission mapping handoff](real-feishu-permission-mapping-handoff.md) | 非 demo tenant/org 在目标上下文一致时允许；tenant/org/private/source context mismatch fail closed；真实飞书 candidate 写入 tenant/org/visibility ledger；deny 不返回明文 evidence/current_value。 |
| 补 limited Feishu ingestion 本地底座 | P1 | 程俊豪 | 2026-04-28 | `memory_engine/document_ingestion.py`、`memory_engine/copilot/schemas.py`、[limited ingestion handoff](handoffs/limited-feishu-ingestion-handoff.md) | 群聊、文档、任务、会议、Bitable 来源文本可进入 review-policy pipeline；每类来源保留 source metadata 和 evidence quote；source context mismatch fail closed；source revoked 后 active memory 标记 stale 并从默认 recall 隐藏。 |
| 固定评委/用户主路径脚本和体验验收 | P0 | 程俊豪 | 2026-04-29 | `docs/judge-10-minute-experience.md`、`docs/demo-runbook.md`、`docs/productization/user-experience-todo.md`、`docs/human-product-guide.md` | 已固化 10 分钟评委入口、主路径脚本、可选受控真实 DM allow-path、失败 fallback 和 no-overclaim 边界；commit `b77f367` 已推送。 |
| 接真实 Feishu API 拉取和扩充 review-policy 路径 | P1 | 程俊豪 | 2026-04-29 | `memory_engine/feishu_task_fetcher.py`、`memory_engine/feishu_meeting_fetcher.py`、`memory_engine/feishu_bitable_fetcher.py`、`memory_engine/copilot/tools.py`、[Feishu API pull handoff](handoffs/feishu-api-pull-handoff.md) | 任务、会议、Bitable fetcher 已接入 review-policy pipeline；`feishu.fetch_*` 在真实 API fetch 前做 permission/source_context fail-closed；Feishu live `/task`、`/meeting`、`/bitable` payload 写入 `permission.source_context`；API 失败不创建 candidate，不冒称 live 成功。 |
| 补审计查询、告警和运维 healthcheck 面 | P1 | 程俊豪 | 2026-04-29 | `memory_engine/document_ingestion.py`、`memory_engine/copilot/healthcheck.py`、`memory_engine/copilot/service.py`、`scripts/query_audit_events.py`、`scripts/check_audit_alerts.py`、[audit ops observability handoff](handoffs/audit-ops-observability-handoff.md) | 权限拒绝、candidate/review、limited ingestion、source revoke、显式 `ingestion_failed`、embedding unavailable fallback 可查询；healthcheck 默认给出 websocket 运维入口，显式开启时纳入 staging 结果；仍不宣称生产级监控或 productized live。 |
| 设计 productized live 长期运行方案 | P2 | 程俊豪 | 2026-04-29 | [productized-live-long-run-plan.md](productized-live-long-run-plan.md)、[productized-live handoff](handoffs/productized-live-long-run-plan-handoff.md)、`deployment-runbook.md`、`monitoring-design.md`、`permission-admin-design.md`、`audit-ui-design.md`、`ops-runbook.md` | 已写清 L0/L1/L2/L3 gate、部署拓扑、单监听、PostgreSQL ledger、监控告警、权限后台、审计 UI、回滚停写和草案文档边界；仍不宣称 productized live 已完成。 |
| 补 Cognee 主路径本地闭环 | P1 | 程俊豪 | 2026-05-01 | `memory_engine/copilot/cognee_adapter.py`、`memory_engine/copilot/service.py`、`memory_engine/copilot/retrieval.py`、`scripts/check_cognee_curated_sync_gate.py`、[Cognee 主路径 handoff](handoffs/cognee-main-path-handoff.md) | confirm 后只同步 curated memory fields 和 ledger metadata 到 Cognee add -> cognify；reject 会 withdrawal；未匹配 ledger 的 Cognee result 不进入正式 answer；同步失败时 repository fallback 清楚可见；当前安装 Cognee SDK 的 metadata-optional / async 调用形态已兼容，并新增隔离真实 Cognee store gate。当前本机 LLM 仍会在 Cognee 结构化图谱抽取阶段触发 `InstructorRetryException`，因此长期 embedding 服务和生产持久化 Cognee 部署仍未完成。 |
| 补 review surface 可操作写回闭环 | P1 | 程俊豪 | 2026-04-28 | `memory_engine/bitable_sync.py`、`tests/test_bitable_sync.py`、[review surface operability handoff](review-surface-operability-handoff.md) | Candidate Review / Reminder Candidate 行有稳定 `sync_key`；Bitable 非 dry-run 写入前查已有记录，命中则 upsert 更新；写入后读回确认；失败不声称同步成功。 |
| 补真实 Feishu DM 到本项目 first-class 工具的受控 live E2E 证据 | P1 | 程俊豪 | 2026-04-29 | `agent_adapters/openclaw/plugin/`、`memory_engine/copilot/openclaw_tool_runner.py`、[DM routing handoff](handoffs/feishu-dm-routing-handoff.md) | 真实 DM 进入 OpenClaw websocket 后直接调用 `fmc_memory_search`，插件/Python runner 解析 JSON-string `current_context`，进入 `handle_tool_request()` / `CopilotService`；飞书机器人回复读回 5 条命中、`request_id=req_feishu_dm_live_20260429_1104`、`trace_id=trace_feishu_dm_live_20260429_1104`、`permission_decision=allow/scope_access_granted`；仍不宣称稳定长期路由。 |
| 补真实飞书可点击卡片受控路径 | P1 | 程俊豪 | 2026-04-29 | `memory_engine/copilot/feishu_live.py`、`memory_engine/feishu_events.py`、`tests/test_copilot_feishu_live.py`、[互动卡片 handoff](handoffs/real-feishu-interactive-cards-handoff.md) | Feishu live `card_mode=interactive` 使用 typed card builder；候选审核卡按钮 value 只携带 action 和 candidate id，不内嵌 `current_context`；点击确认、拒绝、要求补证据、标记过期会重新按当前 operator 构造 permission 并进入 `handle_tool_request()` / `CopilotService`；非 reviewer 点击 fail closed，候选不变；仍不宣称生产级 card action 长期运行。 |
| 补审核收件箱、冲突合并和撤销入口 | P1 | 程俊豪 | 2026-04-30 | `memory_engine/copilot/review_inbox.py`、`memory_engine/copilot/feishu_live.py`、`memory_engine/feishu_cards.py`、`memory_engine/feishu_events.py`、`scripts/openclaw_feishu_card_action_router.py` | `/review` 默认打开“待我审核”定向卡片，支持 mine/conflicts/high_risk 视图；候选可在收件箱里直接确认、拒绝、补证据；冲突候选显示旧结论/新结论并提供“确认合并”；`/undo` 和 card action router 可撤销已确认/已拒绝/需补证据/已过期状态；所有状态变更仍进入 `handle_tool_request()` / `CopilotService`，当前仍是受控 sandbox/pre-production 路径，不宣称生产长期运行。 |
| 补 Feishu 群/用户/消息企业图谱拓扑 | P1 | 程俊豪 | 2026-04-29 | `memory_engine/copilot/graph_context.py`、`memory_engine/copilot/feishu_live.py`、`memory_engine/db.py`、[群图谱节点 handoff](handoffs/feishu-group-graph-node-handoff.md) | 新群进入 Feishu live 入口时先登记为同 tenant/org 下的 `feishu_chat` 图谱节点；未在 allowlist 的群只写 org/chat 最小元数据，不写 raw_events、不创建 candidate、不回复消息、不创建 user/message 节点；allowlist 通过后登记同一用户唯一 `feishu_user` 节点、`feishu_message` 节点和群/用户/消息关系边，消息正文仍只走 raw_events/candidate/evidence，后续仍按 review-policy 和 CopilotService 权限门控处理。 |
| 补 OpenClaw gateway 不 @ 静默候选筛选和群设置/启停入口 | P1 | 程俊豪 | 2026-05-01 | `scripts/openclaw_feishu_remember_router.py`、`tests/test_openclaw_feishu_remember_router.py`、`memory_engine/copilot/group_policies.py` | `route_gateway_message()` 支持 allowlist 群未 @ 消息静默筛选；普通问句、低信号消息、非 allowlist 群不调用 tool、不回群卡片；命中企业记忆信号时通过 `handle_tool_request("memory.create_candidate")` / `CopilotService` 并携带 `current_context.permission`；gateway 抢到 `/settings`、`/enable_memory`、`/disable_memory` 时也进入本地群策略读写/审计路径，reviewer/admin allow，member deny 并写审计 source_context=`openclaw_gateway_live`。这是本地 gateway 路由入口，不宣称长期 live 完成。 |
| 补审核卡片 DM/private 定向投递 | P1 | 程俊豪 | 2026-04-30 | `memory_engine/feishu_publisher.py`、`memory_engine/feishu_events.py`、`scripts/check_feishu_review_delivery_gate.py`、`tests/test_feishu_publisher.py`、`tests/test_feishu_interactive_cards.py`、`tests/test_feishu_review_delivery_gate.py` | 带 `open_ids` / `user_ids` 的 interactive card 不再发群 `chat_id`；publisher 逐个 `--user-id` 发送 DM 卡片；失败 fallback 只发 DM 文本；timeout ambiguity 不回群；dry-run 输出 DM mode 和 targets；card action 必须带 Feishu update token，否则 fail closed 且不改候选状态；本地 gate 覆盖 `/review` private card、confirm update 原卡片和缺 token 不变更。当前为本地测试闭环，不宣称真实飞书长期投递已完成。 |
| 补群级设置和启停策略 | P2 | 程俊豪 | 2026-05-01 | `memory_engine/copilot/feishu_live.py`、`memory_engine/copilot/group_policies.py`、`memory_engine/feishu_cards.py`、`tests/test_copilot_feishu_live.py`、`tests/test_copilot_admin.py` | `/settings` / `/group_settings` 展示 allowlist 和当前群策略；新群默认 pending_onboarding，只登记最小群策略和群节点；`/enable_memory` / `/disable_memory` 需要 reviewer/admin 授权并写审计；Admin Groups 视图/API 可查看群策略状态。不是全量 workspace ingestion，也不是生产级企业配置后台。 |
| 补干净评委 Demo DB 隔离工具 | P2 | 程俊豪 | 2026-05-01 | `scripts/prepare_clean_demo_db.py`、`tests/test_clean_demo_db.py`、`docs/manual-testing-guide.md` | 生成新的 SQLite demo DB 并写入固定 demo seed；只检查 source DB 噪声计数，不修改 live/staging 源库；输出库不带入 live `feishu_group_policies` 或非 `demo_seed` raw event source type；demo replay 全绿。不是生产数据保留、删除或长期运维策略。 |
| 补非 @ 群消息事件投递 gate | P1 | 程俊豪 | 2026-05-01 | `scripts/check_feishu_passive_message_event_gate.py`、`tests/test_feishu_passive_message_event_gate.py`、[passive message gate handoff](handoffs/feishu-passive-message-event-gate-handoff.md) | 可对真实 lark-cli/OpenClaw NDJSON/JSON 事件日志检查普通非 @ 群文本是否到达 listener；能明确区分 `reaction_only_no_passive_message_event`、只 @Bot、目标群不匹配和真正 passive message seen。当前只是排障 gate，未跑真实日志前不能宣称非 @ 群消息 live 投递已打通。 |

## 仍未完成任务拆分

| 任务 | 优先级 | 负责人 | 截止建议 | 文件/页面位置 | 完成标准 |
|---|---|---|---|---|---|
当前 P1 no-overclaim 审查已完成，剩余项只在继续产品化时启动：

| 任务 | 优先级 | 负责人 | 截止建议 | 文件/页面位置 | 完成标准 |
|---|---|---|---|---|---|
| 扩大真实飞书样本实测 | P1 | 程俊豪 | 待定 | `memory_engine/copilot/feishu_live.py`、`memory_engine/document_ingestion.py`、`docs/productization/feishu-staging-runbook.md` | 在已完成 Task / Meeting / Bitable fetcher 入口基础上，用受控真实资源 ID 继续扩样；失败时保留 fallback，不冒称全量 workspace ingestion。 |
| 跑通非 @ 群消息真实投递证据 | P1 | 程俊豪 | 待定 | `scripts/check_feishu_passive_message_event_gate.py`、`docs/manual-testing-guide.md`、`docs/productization/feishu-staging-runbook.md` | 在已启用群策略的真实测试群发送普通非 @ 文本，导出当前单监听入口捕获日志，gate 返回 `passive_group_message_seen`，并继续读回 candidate/audit；如果仍是 reaction-only，则先修 Feishu app 事件订阅/权限。 |
| 跑通真实飞书权限负例证据 | P1 | 程俊豪 | 待定 | `scripts/check_feishu_permission_negative_gate.py`、`docs/manual-testing-guide.md`、`docs/productization/feishu-staging-runbook.md` | 第二个非 reviewer 真实用户在受控测试群发送 `@Bot /enable_memory`，导出当前单监听入口 result log，gate 返回 `non_reviewer_enable_memory_denied`；audit-only 不算完成，仍不得冒称生产级 RBAC。 |
| 扩大真实飞书卡片点击实测 | P1 | 程俊豪 | 待定 | `memory_engine/copilot/feishu_live.py`、`memory_engine/feishu_events.py`、`scripts/check_feishu_review_delivery_gate.py`、`docs/manual-testing-guide.md` | 本地 gate 已验证 card action update-token 和缺 token fail-closed；后续仍需在受控测试群里真实点击 `确认保存`、`拒绝候选`、`要求补证据`、`标记过期` 并读回审计；失败时保留 fallback，不冒称生产级 card action 长期运行。 |
| 扩大真实 DM 定向投递实测 | P1 | 程俊豪 | 待定 | `memory_engine/feishu_publisher.py`、`docs/manual-testing-guide.md` | lark-cli 认证可用后，用受控 reviewer/owner open_id 读回 DM 卡片投递、DM 文本 fallback 和超时不回群行为；失败时保留 fallback，不冒称生产级长期运行。 |
| 固定真实 Cognee provider/model gate | P1 | 程俊豪 | 待定 | `scripts/check_cognee_curated_sync_gate.py`、`memory_engine/copilot/cognee_adapter.py`、`docs/productization/handoffs/cognee-main-path-handoff.md` | 当前 SDK 调用形态已兼容，但默认本地 LLM 仍会在 Cognee 结构化图谱抽取阶段失败；后续需选定稳定 provider/model 或配置策略，让 gate 返回 `cognee_sync.status=pass` 且 `fallback=null`，仍不得把它写成长期 embedding 服务。 |
| 跟踪 7 个用户体验产品化缺口 | P0 | 程俊豪 | 待定 | [user-experience-todo.md](user-experience-todo.md) | 逐项跟踪飞书主路径、记忆卡片、解释层、审核队列、可控提醒、真实表达样本和 10 分钟评委体验包；只有普通用户不理解内部 ID 也能完成动作时才标记完成。 |
| 继续推进 productized live gate | P2 | 程俊豪 | 待定 | [productized-live-long-run-plan.md](productized-live-long-run-plan.md) | 已完成本地 tenant policy editor；后续在 L1 internal pilot、PostgreSQL pilot、真实企业 IdP SSO 验收、审计 read-only view 中选一个小 gate 实施；本阶段仍不把 productized live 写成已完成。 |

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
- 已完成真实 Feishu DM 到本项目 first-class `fmc_*` / `memory.*` tool routing 的稳定长期路由。
- 已完成 productized live 长期运行。当前只能说长期运行方案已完成，尚未上线运行。
