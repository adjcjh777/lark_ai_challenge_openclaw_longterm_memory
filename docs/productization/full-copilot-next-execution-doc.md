# 完整可用 Copilot 后续执行文档

日期：2026-04-28  
更新：2026-05-04，已把 workspace ingestion 方向和 bot 单聊回读证据纳入当前主控文档。

这份文档是后续 agent 的产品化执行入口。它不再用来证明“初赛 MVP 能跑”；那个阶段已经有 demo / pre-production 证据。现在要继续推进的是：在不破坏现有稳定闭环的前提下，把飞书文档、云文档、Bitable、Sheet 和群聊来源放进同一条受治理的企业记忆链路。

## 一句话目标

把 Feishu Memory Copilot 做成一个完整可用的 OpenClaw-native 企业记忆产品：Agent 能调用带权限、证据、版本和审计的团队记忆；飞书侧能在受控范围内发现候选、搜索当前结论、解释版本、预取任务上下文，并把需要人工判断的内容交给 reviewer / owner。

## 先看这个

当前状态是 **demo / pre-production 闭环已完成，workspace ingestion 进入 limited pilot，生产全量 workspace ingestion 还未完成**。

已成型的主线包括：OpenClaw `fmc_*` 工具、本地 bridge、`CopilotService` 权限门控、候选记忆、版本链、审计、检索、受控飞书测试群 live sandbox、first-class OpenClaw tool registry、本机 websocket staging 证据、一次受控真实 Feishu DM allow-path、Cognee 本地/staging 长跑证据，以及九项 demo/pre-production completion audit gate。

Workspace ingestion 的当前选择是 **lark-cli first**。原因很直接：lark-cli 已经把 Drive、Wiki、Docs、Sheets、Base/Bitable 等操作包装成适合 OpenClaw 调用的命令，能更快做出可审计 pilot。native Feishu OpenAPI / SDK 后续只在长期 daemon、高吞吐热路径、rate-limit 管理或更强错误分类需要时替换子进程边界。

当前 workspace pilot 已经证明：Drive / Wiki / Docx / Sheet / Bitable 能被发现、读取并进入 candidate pipeline；registry、cursor、revision skip、stale 标记、fetch failure 和同结论回读都有受控证据。受控 normal Sheet 加真实 OpenClaw Feishu 群消息已经关闭 controlled readiness gate，bot 单聊也能通过 `fmc_memory_search` 回读这条 workspace Sheet 记忆。这些证据证明 limited pilot 可验收，不是生产 SLO、长期 crawler 或 productized live。

还不能说完成的是：生产全量 workspace ingestion、生产 DB / 生产监控、productized live 长期运行、完整多租户企业后台和长期运行 SLO。更严格的 productized gate 已经把 source coverage、workspace surface、scheduler/cursor、rate-limit/backoff、governance、operations 和 24h+ long-run 绑定到非示例 manifest；collector、merger、scheduler 和 finalizer 都只是整理证据，不替代真实运行。当前 blocker 仍是 `live_long_run.duration_hours_at_least_24`，所以 finalization status 继续保持 `goal_complete=false`。

所有真实飞书来源仍必须先进入 `memory.create_candidate` 和 review policy。低重要性、无冲突、无敏感风险内容可以自动确认成 active；项目进展重要、重要角色发言、敏感/高风险或冲突内容必须停在 candidate；confirm / reject / undo 必须走 `CopilotService` / `handle_tool_request()`。

已完成并归档的日期计划只作为历史证据，不再作为默认执行入口。如果历史计划和当前代码或本文件冲突，以当前代码、`README.md` 顶部状态和本文件为准。

## 下一步怎么选

如果要继续 workspace ingestion，优先做这三类实证，而不是再写一轮架构讨论：

1. 扩大 organic 项目/企业 workspace 样本，不再只依赖这次受控 normal Sheet。
2. 把真实 same-conclusion 样本扩到 Docs、Sheets、Base/Bitable 和 Wiki space，并保留 conflict negative：同值追加证据，差异值停在 conflict candidate。
3. 把真实 lark-cli fetch latency gate 和 run registry 继续扩到项目/企业资源，保持 bounded discovery、registry skip、失败审计和 no raw-event embedding。
4. 用 `deploy/workspace-ingestion.schedule.example.json` 派生真实 schedule config，先跑 `python3 scripts/run_workspace_ingestion_schedule.py --config <schedule> --json` 确认 plan，再由外部 timer 显式 `--execute` 收集多轮运行证据。
5. 需要自动采集时，用 `python3 scripts/sample_workspace_ingestion_schedule.py --config <schedule> --execute --sample-count <n> --interval-seconds <seconds> --output-dir <redacted-dir> --json` 连续写出脱敏 reports 和 sampler status。
6. source coverage 证据只保留脱敏 gate / ingest reports，再用 `python3 scripts/collect_workspace_source_coverage_evidence.py --evidence-report <report.json> --evidence-ref <redacted-ref> --json` 生成 `source_coverage` manifest patch。
7. rate-limit / governance / operations 证据来自外部已验证记录，再用 `python3 scripts/collect_workspace_ops_governance_evidence.py ... --json` 生成三个 manifest patch section。
8. 多轮 schedule report 只保留脱敏输出；无人值守采集时用 `python3 scripts/run_workspace_ingestion_long_run_tick.py --config <schedule> --output-dir <redacted-dir> --merge-patch <source-coverage.json> --merge-patch <ops-governance.json> --json`，外部 timer 每次调用一轮。手工汇总时用 `python3 scripts/collect_workspace_ingestion_long_run_evidence.py --schedule-report-glob '<redacted-dir>/schedule-report-*.json' --evidence-ref <redacted-ref> --json` 生成 long-run manifest patch。
9. 多个 evidence patch 准备好后，用 `python3 scripts/merge_workspace_productized_ingestion_evidence.py --patch <patch.json> --output <manifest.json> --json` 合并并验证；合并器会拒绝未知 section、placeholder 和 secret-like 值。
10. 需要宣称“全量 workspace 接入”前，先填充并审计 `deploy/workspace-ingestion.production-evidence.example.json` 的非示例 manifest，再跑 `python3 scripts/check_workspace_productized_ingestion_readiness.py --manifest <manifest> --require-productized-ready --json`、`python3 scripts/check_workspace_ingestion_objective_completion.py --manifest <manifest> --json` 和 `python3 scripts/finalize_workspace_ingestion_productized_evidence.py --manifest <manifest> --long-run-evidence <long-run.json> --output <finalization.json> --json`。finalizer 只读现有证据，不启动 ingestion 或 Feishu listener；它返回 `goal_complete=true` 后，仍要由当前 agent 同步 README、handoff、看板和提交记录，再关闭目标。

具体采证步骤看 `docs/productization/workspace-ingestion-evidence-collection-runbook.md`。当前 controlled readiness 已通过；这个 runbook 继续用于后续扩样和防回退。总 readiness gate 会复用 `--resource sheet:<token>:<title>` 做项目 normal Sheet evidence，也支持 `--sheet-folder-walk-*` / `--sheet-wiki-space-walk-ids` 直接验收文件夹或知识库空间里的 Sheet；同结论资源池也可通过 `--corroboration-query`、`--corroboration-folder-walk-*` 和 `--corroboration-wiki-space-walk-ids` 做受控只读扩搜，并把显式资源失败和可选 discovery 失败分开计数。任何新增样本都必须继续保留 no-overclaim 边界：controlled readiness 完成，不等于生产全量 workspace ingestion。

如果要继续文档重写，按 `docs/productization/document-writing-style-guide-opus-4-6.md` 只改活跃入口文档。历史 handoff 和 archived plans 保留审计用途，除非被重新提升为当前执行入口。

## 本轮验证底线

文档-only 改动至少运行：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
git diff --check
```

改 Python、脚本、schema 或 benchmark runner 时，追加：

```bash
python3 -m compileall memory_engine scripts
```

改 Copilot schema / tools / service、权限、治理或候选记忆时，再按 `AGENTS.md` 和 `docs/productization/agent-execution-contract.md` 追加对应 unittest。

## 必读文件

执行前按顺序读取：

```text
AGENTS.md
README.md
docs/README.md
docs/human-product-guide.md
docs/productization/prd-completion-audit-and-gap-tasks.md
docs/productization/launch-polish-todo.md
docs/productization/user-experience-todo.md
docs/productization/workflow-and-test-process.md
docs/productization/complete-product-roadmap-prd.md
docs/productization/complete-product-roadmap-test-spec.md
docs/productization/contracts/storage-contract.md
docs/productization/contracts/permission-contract.md
docs/productization/contracts/audit-observability-contract.md
docs/productization/contracts/openclaw-payload-contract.md
docs/productization/contracts/migration-rfc.md
docs/productization/contracts/negative-permission-test-plan.md
docs/plans/2026-05-08-demo-readiness-handoff.md
docs/productization/feishu-single-listener-handoff.md
```

如果这些文件与当前代码冲突，以当前代码和本执行文档的产品化目标为准；已完成的日期计划和旧 Day1-Day7 文档只作 reference，不要回到旧 CLI-first / Bot-first 主线。这里的旧 CLI-first 指 legacy Bot / legacy CLI 主线，不是当前 workspace pilot 的 lark-cli-first adapter。

## 当前事实基线

已经完成：

- 存储、审计和核心工具链已完成本地闭环：schema version、audit table、`memory.search/create_candidate/confirm/reject/explain_versions/prefetch`、`heartbeat.review_due` 和 7 个 OpenClaw schema 工具都已纳入 CopilotService 主线。
- Feishu 受控入口已完成 sandbox/pre-production 路径：allowlist 或显式启用群策略后，非 `@Bot` 消息可做静默 candidate probe；`@Bot` / 私聊走主动交互；新群默认只登记最小群策略，不写 raw events。
- OpenClaw / Feishu runtime 证据已覆盖：单监听 preflight、非 @ 群消息投递、本机 websocket staging、first-class `fmc_*` routing、本地 Agent runtime flow 和受控真实 DM allow-path。它们证明受控链路，不证明长期稳定生产路由。
- Cognee、embedding、demo readiness 和 benchmark 已有本地/staging gate：Cognee curated sync / fallback、live embedding gate、demo readiness、recall/candidate/conflict/layer/prefetch/heartbeat runner 都可复现；这些不等于生产长期 embedding 服务。
- Review surface 已完成受控可操作路径：interactive card、review inbox、DM 投递、confirm / reject / needs_evidence / expire / undo、Bitable review 写回和群级设置启停都通过 `handle_tool_request()` / `CopilotService`。
- 权限、ingestion 和运维侧已补 gate：真实飞书 permission context、第二用户权限负例 gate、limited Feishu ingestion、任务/会议/Bitable fetcher、审计查询、告警脚本和 healthcheck 可观测字段都有对应 handoff。
- Productized live 目前只有方案和 gate：部署拓扑、单监听、PostgreSQL ledger、监控告警、权限后台、审计 UI 和回滚边界已经写清，但不是已验证上线 runbook。
- 详细证据入口统一看 `docs/productization/handoffs/`、`docs/productization/openclaw-runtime-evidence.md`、`docs/productization/productized-live-long-run-plan.md` 和本文件顶部 workspace 状态说明。

仍未完成：

- Feishu Agent live DM routing：本地 Agent 到 `fmc_*` 插件工具、再到 Python 侧 `memory.*` / `CopilotService` 的调用验证已补；2026-04-29 已补一次受控真实 DM `fmc_memory_search` allow-path live E2E 和飞书回复读回证据；2026-04-30 已补 OpenClaw gateway 本地静默候选筛选入口；2026-05-04 已补 p2p DM before_dispatch 路由和多次 workspace 记忆 bot 单聊回读，最新 13:08 自动复测通过。后续仍要扩大到真实 gateway/live 下的 `prefetch` / `create_candidate` 等关键动作、读回 DM 定向卡片投递，并验证长期稳定性；不能把单次或本地证据写成稳定长期路由。
- 真实 Feishu 样本实测扩样：任务、会议、Bitable 读取入口和 review-policy 路径已补；后续仍可用受控真实资源 ID 继续扩样，但不能冒称全量 workspace ingestion 或生产 live。
- 用户体验产品化：7 个 UX 缺口已单独进入 [用户体验产品化 TODO 清单](user-experience-todo.md)，包括飞书主路径、记忆卡片、解释层、审核队列、可控提醒、真实表达样本和 10 分钟评委体验包；当前已完成受控 UX 路径，但仍不能写成 production live、全量 workspace 接入或长期稳定线上运行。
- OpenClaw health running 字段一致性：OpenClaw 2026.4.24 的 `openclaw health --json` 总览仍把 Feishu running 报为 `false`，但 `openclaw channels status --probe --json` 和 gateway 日志显示 running；当前作为 warning 记录。
- productized live：长期运行方案已完成，本地/pre-production LLM Wiki / Graph Admin 已有 admin-only tenant policy editor；但没有生产 DB 部署、生产级 Prometheus/Grafana 长期监控、真实企业目录/IdP/RBAC 接入，也没有长期线上运行证据。
- productized workspace ingestion：已有 one-shot schedule runner、schedule sampler、source coverage collector、ops/governance/rate-limit collector、long-run evidence collector、evidence patch merger、production evidence gate、objective completion audit 和 example manifests；最新非 dry-run sampler 已证明一小批 organic docx/Base 能真实进入 candidate pipeline，并让 scheduler/cursor 子项通过，但没有非示例 manifest 完整证明 source adapter coverage、workspace surface coverage、same-conclusion、conflict-negative、rate-limit/backoff、governance、operations 和 24h+ long-run，因此不能说全量 workspace ingestion 完成。

## 产品完成定义

“完整可用 Copilot”在本阶段不是大而全企业后台，而是满足以下条件：

1. OpenClaw Agent 能真实调用 `memory.search`、`memory.create_candidate`、`memory.confirm`、`memory.reject`、`memory.explain_versions`、`memory.prefetch`、`heartbeat.review_due`。
2. 飞书测试/预发布环境中能完成：查询当前有效结论、创建候选记忆、人工确认/拒绝、查看版本链、任务前上下文预取、提醒候选审核。
3. Copilot Core 是唯一事实源：任何入口都不能直接改 repository 状态，必须经过 `CopilotService` / `handle_tool_request()`。
4. 每条 active memory 都有 evidence；没有 evidence 的内容不能成为可信结论。
5. 每次确认、拒绝、权限拒绝、真实 ingestion、提醒生成都有 audit record。
6. 权限缺失或畸形必须 fail closed，不允许 fallback 到宽松默认。
7. README、runbook、benchmark report、whitepaper、handoff 和飞书看板口径一致。

## 执行总原则

- 先补产品化硬缺口，再加新功能。
- 先写测试和 healthcheck，再改核心状态。
- 先走 Copilot Core，再接飞书 UI / OpenClaw runtime。
- 真实飞书来源先走 review policy：低重要性安全候选可自动 active，重要/敏感/冲突候选仍需人工确认。
- 所有外部副作用必须有日志、审计和可撤回路径。
- 每完成一个阶段，都同步 README、handoff、飞书任务看板，并 commit + push。

## Phase A：Storage Migration + Audit Table

状态：已完成本地闭环，详见 [Phase A handoff](phase-a-storage-audit-handoff.md)。Phase B 已补受控 runtime 证据，Phase D 已补 live embedding gate，下一轮优先从 Phase E 开始。

目标：让 Copilot Core 具备产品级事实源，不再只有 legacy scope。

主要文件：

```text
memory_engine/db.py
memory_engine/repository.py
memory_engine/copilot/service.py
memory_engine/copilot/governance.py
memory_engine/copilot/permissions.py
memory_engine/copilot/healthcheck.py
tests/test_copilot_permissions.py
tests/test_copilot_healthcheck.py
docs/productization/contracts/storage-contract.md
docs/productization/contracts/audit-observability-contract.md
```

必须完成：

1. 已完成：新增或迁移字段：`tenant_id`、`organization_id`、`visibility_policy`。
2. 已完成：新增 audit table，至少记录：
   - `audit_id`
   - `event_type`
   - `tool_name`
   - `memory_id`
   - `candidate_id`
   - `actor_id`
   - `tenant_id`
   - `organization_id`
   - `scope`
   - `permission_decision`
   - `request_id`
   - `trace_id`
   - `created_at`
3. 已完成：`memory.confirm`、`memory.reject`、permission denied、limited ingestion、heartbeat candidate 都写 audit record。
4. 已完成：`scripts/check_copilot_health.py --json` 不再把 storage schema 报为 warning。
5. 已完成：旧数据能兼容读取；不要破坏现有 benchmark。

验收命令：

```bash
python3 scripts/check_openclaw_version.py
git diff --check
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_permissions tests.test_copilot_healthcheck
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools
python3 scripts/check_copilot_health.py --json
ollama ps
```

完成标准：

- 已完成：healthcheck 中 `storage_schema.status=pass`。
- 已完成：audit smoke test 能证明 confirm/reject/deny、limited ingestion candidate、heartbeat candidate 都有记录。
- 已完成：所有旧 Copilot tests 仍通过。

## Phase B：真实 OpenClaw Agent Runtime 验收

状态：已完成受控闭环，详见 [Phase B runtime evidence](openclaw-runtime-evidence.md) 和 [Phase B handoff](phase-b-openclaw-runtime-handoff.md)。边界：这证明 OpenClaw Agent runtime 可以通过 `exec` 调用仓库证据脚本进入 `handle_tool_request()` / `CopilotService`；后续 first-class registry 和 Feishu websocket staging running 证据已分别补齐。

目标：把 OpenClaw 产品形态从 schema/local bridge/replay 推到真实 runtime 证据。

主要文件：

```text
agent_adapters/openclaw/memory_tools.schema.json
agent_adapters/openclaw/feishu_memory_copilot.skill.md
agent_adapters/openclaw/examples/*.json
memory_engine/copilot/tools.py
docs/demo-runbook.md
docs/productization/openclaw-runtime-evidence.md
docs/productization/feishu-staging-runbook.md
```

必须完成：

1. 已完成：新增 `docs/productization/openclaw-runtime-evidence.md`。
2. 已完成：真实 runtime 验收前先运行 `python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket`，确认没有 legacy `memory_engine feishu listen`、repo 内 `copilot-feishu listen` 或直接 `lark-cli event +subscribe` 同时消费同一个 bot；如果只看到泛化 `openclaw-gateway`，必须继续用 `channels.status` / gateway log 判断 Feishu channel 是否真的 active。
3. 已完成：在真实 OpenClaw Agent runtime 中至少跑通 3 条：
   - 历史决策召回：Agent 调用 `memory.search`。
   - 候选确认：Agent 调用 `memory.create_candidate` 后再确认或拒绝。
   - 任务前上下文：Agent 调用 `memory.prefetch` 后生成 checklist / plan / report。
4. 已完成：每条记录输入、输出、tool、request_id、trace_id、permission_decision、失败回退。
5. 已完成：边界写清，不冒称 production live；first-class tool registry 和 Feishu websocket staging running 证据已在后续 handoff 中补齐。

验收命令：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_demo_readiness.py --json
python3 -m unittest tests.test_copilot_tools tests.test_demo_seed tests.test_demo_readiness
git diff --check
ollama ps
```

完成标准：

- 已完成：runtime evidence 文档可给评委或队友复现。
- 已完成：至少 3 条 runtime flow 有证据。
- 已完成：README 不再只依赖 local bridge 表述。
- 已完成：验收记录能证明同一时间没有 repo 内 lark-cli listener 冲突；如果后续 OpenClaw websocket owns the bot，仍不得同时运行 lark-cli event listener；如果泛化 `openclaw-gateway` 正在运行，repo 内 lark-cli planned listener 默认 fail closed。

## Phase C：Feishu Staging Runbook

状态：已补单监听守卫和 staging runbook；真实 OpenClaw runtime 受控证据已在 Phase B 补齐。

目标：把受控飞书测试群 live sandbox 变成可复现、可交接、可停止的 staging 流程。

主要文件：

```text
scripts/start_copilot_feishu_live.sh
memory_engine/copilot/feishu_live.py
memory_engine/cli.py
docs/reference/local-lark-cli-setup.md
docs/productization/feishu-staging-runbook.md
tests/test_copilot_feishu_live.py
scripts/check_feishu_listener_singleton.py
memory_engine/feishu_listener_guard.py
```

必须完成：

1. 新增并维护 `docs/productization/feishu-staging-runbook.md`。
2. 写清如何设置 allowlist 群聊、reviewer、日志路径、启动命令、停止命令。
3. 写清单监听规则：OpenClaw Feishu websocket、Copilot lark-cli sandbox、legacy fallback 三选一；不得让 legacy `memory_engine copilot-feishu listen` / `lark-cli event +subscribe` 干扰 OpenClaw Feishu websocket。
4. 写清测试顺序：
   - `/health`
   - `/remember ...`
   - `/confirm <candidate_id>`
   - 普通 @ 提问触发 `memory.search`
   - `/reject <candidate_id>`
   - 权限失败样例
5. 明确真实 chat_id、open_id、token 只保存在本机环境，不写仓库。
6. 所有真实飞书来源先走 review policy；低重要性安全候选可自动 active，重要/敏感/冲突候选仍需人工确认。

验收命令：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_feishu_listener_singleton.py --planned-listener copilot-lark-cli
python3 -m unittest tests.test_copilot_feishu_live
python3 -m compileall memory_engine scripts
git diff --check
ollama ps
```

完成标准：

- 新机器/新 agent 能按 runbook 启动 staging。
- 权限不足、群聊不在 allowlist、非 reviewer 操作都有明确行为。
- repo 内启动脚本和 direct CLI 都会在启动前做 listener singleton preflight。
- README 和 handoff 不写成全量 Feishu workspace ingestion。

## Phase D：Live Cognee / Ollama Embedding Gate

状态：已完成可复现 live gate，详见 [Phase D handoff](phase-d-live-embedding-handoff.md)。Phase E no-overclaim 审查也已完成，见 [Phase E handoff](phase-e-no-overclaim-handoff.md)。

目标：把 embedding 从 configuration-only warning 推进到可选 live check，并保持可清理。

主要文件：

```text
scripts/check_embedding_provider.py
scripts/check_live_embedding_gate.py
scripts/spike_cognee_local.py
memory_engine/copilot/cognee_adapter.py
memory_engine/copilot/embedding-provider.lock
docs/reference/local-windows-cognee-embedding-setup.md
tests/test_live_embedding_gate.py
```

必须完成：

1. 已完成：明确 live embedding check 与 fallback check 的区别。
2. 已完成：真实运行 provider 检查时执行 `ollama ps`。
3. 已完成：如果拉起 `qwen3-embedding:0.6b-fp16` 或其他本项目模型，验证结束后自动停止，除非文档写明保留原因。
4. 已完成：healthcheck 继续允许 configuration-only，但 productized readiness 有 live embedding gate 的结果。

验收命令：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_live_embedding_gate.py --json
python3 scripts/check_embedding_provider.py
python3 scripts/spike_cognee_local.py --dry-run
ollama ps
git diff --check
```

完成标准：

- 已完成：成功时记录 live provider 维度、模型名、endpoint。
- 已完成：失败时记录 fallback 和原因。
- 已完成：最终 `ollama ps` 无本项目模型驻留，或文档写明为什么保留。

## Phase E：Product QA + No-overclaim 审查

状态：已完成，详见 [Phase E handoff](phase-e-no-overclaim-handoff.md)。后续已完成 `memory.*` first-class OpenClaw 原生工具注册本机证据、OpenClaw Feishu websocket running 本机 staging 证据、一次受控真实 Feishu DM allow-path live E2E 证据、评委/用户主路径脚本、真实 Feishu API review-policy 拉取入口、审计/告警/运维 healthcheck 面和 productized live 长期运行方案；下一步只有在明确继续产品化时，才推进真实 Feishu 样本实测扩样，或从长期运行方案里选择一个 L1/L2 gate 做受控实施。

目标：让所有交付物讲同一个产品故事。

主要文件：

```text
README.md
docs/demo-runbook.md
docs/benchmark-report.md
docs/memory-definition-and-architecture-whitepaper.md
docs/productization/prd-completion-audit-and-gap-tasks.md
docs/productization/full-copilot-next-execution-doc.md
docs/plans/*handoff.md
```

必须检查：

- 已完成：不把 replay 写成 live。
- 已完成：不把 live sandbox 写成生产部署。
- 已完成：不把 limited ingestion 写成全量 workspace ingestion。
- 已完成：不把 configuration-only embedding 写成 live embedding 已通过；当前可说 Phase D live embedding gate 已单独通过。
- 已完成：不把 local bridge 写成真实 OpenClaw runtime；当前可说 Phase B 已有 OpenClaw Agent runtime 受控证据，且后续已补 first-class tool registry 本机插件证据。
- 已完成：不把重要/敏感/冲突候选写成自动 active；只有低重要性安全候选允许 policy 自动确认。

验收命令：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_demo_readiness.py --json
python3 scripts/check_copilot_health.py --json
git diff --check
ollama ps
```

完成标准：

- 已完成：README、runbook、benchmark report、whitepaper、handoff 口径一致。
- 已完成：每个未完成项都有下一步任务入口。
- 已完成：飞书共享看板与 README 顶部任务一致。

## 每轮执行前固定动作

每次新阶段开始前先做：

```bash
date '+%Y-%m-%d %H:%M:%S %Z'
git status --short
python3 scripts/check_openclaw_version.py
```

然后读取：

```text
AGENTS.md
README.md
docs/productization/full-copilot-next-execution-doc.md
docs/productization/prd-completion-audit-and-gap-tasks.md
当前阶段相关 contract / runbook / handoff
```

如果工作树有 `.obsidian/` 或 `docs/pr-reviews/` 未跟踪，默认视为用户/历史产物，不要删除，不要提交，除非用户明确要求。

## 每轮完成后固定动作

每个阶段完成后必须：

1. 更新 README 顶部任务区。
2. 更新当前 handoff 或新增阶段 handoff。
3. 更新飞书共享任务看板：
   - 完成项：`状态=已完成`，`完成情况-程俊豪=true`。
   - 后续项：`状态=待启动`，`完成情况-程俊豪=false`。
4. 运行对应验证命令。
5. 运行 `ollama ps` 并记录清理状态。
6. 提交并推送：

```bash
git status --short
python3 scripts/check_openclaw_version.py
git diff --check
git add <本阶段相关文件>
git commit
git push origin HEAD
```

commit message 必须用 Lore protocol，首行写“为什么做这次变更”，并记录 `Tested:` / `Not-tested:`。

## 可以直接复制给下一轮 agent 的执行提示词

```text
你现在接手 /Users/junhaocheng/feishu_ai_challenge。

当前目标已经从“初赛完成 MVP”升级为“做出完整、可用、可治理、可审计的 Feishu Memory Copilot”。不要重复做 MVP demo，不要回到 CLI-first / Bot-first 主线。

执行前先确认当前日期、git status、OpenClaw 版本：
date '+%Y-%m-%d %H:%M:%S %Z'
git status --short
python3 scripts/check_openclaw_version.py

然后按顺序读取：
AGENTS.md
README.md
docs/README.md
docs/human-product-guide.md
docs/productization/full-copilot-next-execution-doc.md
docs/productization/launch-polish-todo.md
docs/productization/workflow-and-test-process.md
docs/productization/prd-completion-audit-and-gap-tasks.md
docs/productization/complete-product-roadmap-prd.md
docs/productization/complete-product-roadmap-test-spec.md
docs/productization/contracts/storage-contract.md
docs/productization/contracts/permission-contract.md
docs/productization/contracts/audit-observability-contract.md
docs/productization/contracts/openclaw-payload-contract.md
docs/productization/contracts/migration-rfc.md
docs/productization/contracts/negative-permission-test-plan.md
docs/plans/2026-05-08-demo-readiness-handoff.md
docs/productization/phase-a-storage-audit-handoff.md
docs/productization/phase-d-live-embedding-handoff.md
docs/productization/phase-e-no-overclaim-handoff.md

Phase A Storage Migration + Audit Table 已完成。Phase B 真实 OpenClaw Agent Runtime 受控证据也已完成，详见 docs/productization/openclaw-runtime-evidence.md 和 docs/productization/phase-b-openclaw-runtime-handoff.md。Phase D Live Cognee / Ollama Embedding Gate 已完成，详见 docs/productization/phase-d-live-embedding-handoff.md。Phase E Product QA + No-overclaim 审查已完成，详见 docs/productization/phase-e-no-overclaim-handoff.md。

目标：
1. 不要重复执行 Phase E 文档审查；先读取 Phase E handoff 和当前 README 顶部任务。
2. 若用户明确继续产品化，优先补真实权限映射或 Feishu Agent tool routing。
3. 若继续验证 OpenClaw Feishu websocket，先跑单监听检查，保证同一个 bot 只有一个监听入口，再用 `scripts/check_openclaw_feishu_websocket.py` 留下脱敏证据。
4. 若实施 productized live，先从 [productized-live-long-run-plan.md](productized-live-long-run-plan.md) 选择 L1/L2 的单个 gate，不要直接写成已经上线。

必须遵守：
- Copilot Core 是事实源，所有入口必须走 CopilotService / handle_tool_request。
- 真实飞书来源先走 review policy；低重要性安全候选可自动 active，重要/敏感/冲突候选仍需人工确认。
- 缺失或畸形 permission 必须 fail closed。
- 不要把 demo replay、dry-run、测试群 sandbox 写成 productized live。
- 不要改 OpenClaw 版本，保持 2026.4.24。
- 同一个 Feishu Memory Engine bot 只能有一个监听：OpenClaw Feishu websocket、Copilot lark-cli sandbox、legacy fallback 三选一；真实 runtime 验收时不要同时运行 `lark-cli event +subscribe`。

建议文件：
agent_adapters/openclaw/
memory_engine/copilot/tools.py
memory_engine/copilot/service.py
docs/productization/openclaw-runtime-evidence.md
docs/productization/feishu-staging-runbook.md
docs/productization/full-copilot-next-execution-doc.md
docs/productization/phase-e-no-overclaim-handoff.md
docs/productization/prd-completion-audit-and-gap-tasks.md
README.md

验收命令：
python3 scripts/check_openclaw_version.py
python3 scripts/check_demo_readiness.py --json
python3 scripts/check_copilot_health.py --json
git diff --check
ollama ps

完成后：
1. 更新 README 顶部任务区。
2. 更新或新增 handoff。
3. 同步飞书共享任务看板。
4. git status --short 确认只提交相关文件。
5. 用 Lore protocol commit 并 push origin HEAD。
6. 最终报告写清：改了哪些文件、验证结果、Ollama 清理状态、仍未完成的风险。
```
