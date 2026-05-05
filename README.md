# Feishu Memory Copilot

飞书 AI 挑战赛 OpenClaw 赛道项目。

本项目要做的是一个 **OpenClaw-native Feishu Memory Copilot**：让 OpenClaw Agent 在飞书工作流里拥有可治理、可追溯、可审计的企业长程记忆能力。

它不是一个普通聊天 Bot，也不是简单的向量数据库 Demo。核心目标是：**把飞书消息、文档、任务上下文里的长期有效信息，转成带证据、带权限、可确认、可版本化的企业记忆，并通过 OpenClaw 工具给 Agent 使用。**

---

## 1. 当前项目状态

当前状态：**MVP / Demo / Pre-production 闭环已完成；limited workspace pilot 可验收；生产级长期运行还没有完成。**

状态快照：2026-05-04。顶层事实以当前代码、`docs/productization/full-copilot-next-execution-doc.md`、`docs/productization/prd-completion-audit-and-gap-tasks.md`、`docs/productization/workspace-ingestion-goal-completion-audit-2026-05-04.md` 和 `docs/productization/workspace-ingestion-architecture-adr.md` 为准。

### 先看这个

当前系统已经能把受控飞书来源接进同一条 Copilot 记忆链路：OpenClaw `fmc_*` 工具进入 `handle_tool_request()`，再到 `CopilotService`，然后统一经过权限、治理、检索、审计和存储。

Workspace ingestion 的主路径是 lark-cli-first：发现 Drive / Wiki / Docx / Sheet / Bitable 资源，按类型读取内容，再送入 `FeishuIngestionSource -> ingest_feishu_source() -> memory.create_candidate -> CopilotService`。低风险、低重要性、无冲突的内容可以自动确认；重要、敏感或冲突内容仍要交给 reviewer / owner。

Controlled readiness 已通过：受控普通 Sheet 读回 `eligible_project_normal_sheet_count=1`，真实 same-fact finder 读回 `same_fact_match_count=1`，strict gate 证明 `feishu_message + lark_sheet` 合并到同一 active evidence，`check_workspace_ingestion_goal_readiness.py` 返回 `goal_complete=true`。2026-05-04 的 bot 单聊回读也能通过 `fmc_memory_search` 找到这条 workspace Sheet 记忆。

这些证据说明 limited workspace pilot 在 pre-production / controlled evidence 边界内可验收；不能写成生产部署、全量企业 workspace 长期扫描、生产 SLO 或 productized live 完成。继续 workspace 方向时，先看 `docs/productization/workspace-ingestion-goal-completion-audit-2026-05-04.md`、`docs/productization/workspace-ingestion-architecture-adr.md` 和 `docs/productization/workspace-ingestion-evidence-collection-runbook.md`。

### 当前真实 Feishu / Workspace 使用边界

按当前代码，本项目已经进入“**allowlist 群 + 已启用群策略的被动候选识别 + @Bot / 私聊主动交互**”阶段，但还不是全量 workspace ingestion。稳定边界是：

- `scripts/start_copilot_feishu_live.sh` 默认启动的是 **allowlist 测试群** 的 `copilot-feishu listen` 入口，不是全量 workspace ingestion。
- 未在 allowlist、也未启用群策略的 chat 只登记最小群节点和 `pending_onboarding` 策略，不记录消息正文，不创建 candidate。
- allowlist 或已启用群策略的群里，未 `@Bot` 的低信号消息会静默忽略；命中企业记忆信号后才进入 `memory.create_candidate`。
- `@Bot` 和私聊仍走主动交互路径：搜索、候选确认、版本解释、prefetch 等。
- OpenClaw gateway 旁路脚本已补本地 `route_gateway_message()` 入口，但它仍是受控入口，不等于真实 gateway 长期运行已完成。
- 普通问句不会因为命中了“部署 / 负责人 / 截止”这类主题词就自动变成 candidate。
- 真实飞书来源不再“一律 candidate-only”：低重要性、无冲突、无敏感风险的候选可以自动 active；项目进展重要、重要角色发言、敏感/高风险或冲突内容仍要 reviewer / owner 确认。
- 群级设置已有受控入口：`/settings` 或 `/group_settings` 展示 allowlist / 当前群策略、审核投递、auto-confirm policy、scope/visibility 和生产边界；`/enable_memory` / `/disable_memory` 可写本地/pre-production 群策略，但要求 reviewer/admin 授权，并写入审计。
- OpenClaw websocket 下的受控真实 DM 已证明 `fmc_memory_search` allow-path，并在 2026-05-04 补过多次 workspace Sheet 记忆回读；它仍不等于“所有真实飞书对话都已经稳定进入本项目工具链路”。
- OpenClaw 对外工具名一律使用 `fmc_*`；`memory.*` 只保留为 Python 内部服务名，避免和 OpenClaw 内置 `memory_search` 语义混淆。

### 已完成索引

下面这张表主要给后续维护和审计用。第一次读项目时，不需要逐行看完；先读上面的状态说明，再按任务去查对应文件。

| 能力 | 当前状态 | 主要证据 |
|---|---|---|
| OpenClaw memory 工具 | 已完成本机 first-class tool registry、Agent 本地 `fmc_*` 工具调用验证、OpenClaw gateway 本地静默候选筛选和群设置/启停入口，以及受控真实 Feishu/OpenClaw live 证据：2026-04-29 真实 DM -> `fmc_memory_search` -> `CopilotService` allow-path E2E 通过；2026-05-02 `logs/feishu-live-evidence-runs/20260502T085247Z/feishu-live-evidence-packet.json` 已覆盖 `fmc_memory_search`、`fmc_memory_create_candidate`、`fmc_memory_prefetch` 三类 first-class routing success；2026-05-04 修复 OpenClaw `before_dispatch` 的 DM 路由后，真实 bot 单聊 `/recall Workspace ingestion readiness gate Sheet 样本` 被 `fmc_memory_search` 接管并回读 workspace Sheet 记忆，11:47、12:53 和 13:08 自动复测都读回相同 workspace Sheet 记忆卡片和 allow 审计。仍不能写成生产长期运行，也不能写成稳定长期路由 | `agent_adapters/openclaw/plugin/`、`agent_adapters/openclaw/memory_tools.schema.json`、`scripts/check_feishu_dm_routing.py`、`scripts/openclaw_feishu_remember_router.py`、`tests/test_openclaw_tool_registry.py`、`tests/test_feishu_dm_routing.py`、`tests/test_openclaw_feishu_remember_router.py`、`docs/productization/handoffs/feishu-dm-routing-handoff.md` |
| Copilot Core | 已完成核心服务层 | `memory_engine/copilot/service.py`、`tools.py`、`governance.py`、`retrieval.py` |
| 权限门控 | 已完成 fail-closed 本地闭环 | `memory_engine/copilot/permissions.py`、`tests/test_copilot_permissions.py` |
| 真实飞书权限映射 | 已完成本地权限映射闭环 | `memory_engine/copilot/feishu_live.py`、`memory_engine/copilot/permissions.py`、`docs/productization/handoffs/real-feishu-permission-mapping-handoff.md` |
| 真实飞书可点击卡片 | 已完成受控 sandbox/pre-production 路径：Feishu live interactive 回复使用 typed card，候选审核卡可点击确认、拒绝、要求补证据和标记过期；点击动作重新生成当前 operator 权限上下文并进入 `handle_tool_request()` / `CopilotService` | `memory_engine/copilot/feishu_live.py`、`memory_engine/feishu_events.py`、`memory_engine/feishu_cards.py`、`tests/test_copilot_feishu_live.py`、`docs/productization/handoffs/real-feishu-interactive-cards-handoff.md` |
| 定向审核收件箱、DM 投递与撤销/合并体验 | 已完成本地受控路径和一次受控 live E2E 证据：`/review` 默认打开“待我审核”收件箱卡片，只对当前 reviewer/owner 定向可见；定向 interactive card 由 publisher 逐个 `open_id/user_id` 发送 DM，不再回群；收件箱可按 mine/conflicts/high_risk 查看并直接点击确认、拒绝、补证据；冲突候选卡显示旧结论/新结论并提供“确认合并”；`/undo` 和 card action router 可把已确认/拒绝/补证据/过期的候选撤回待审核；2026-05-02 受控 live packet 已让 `check_feishu_review_delivery_gate.py --event-log` 同时看到 private review DM、candidate review card、card action update result 和 review inbox result。仍不能写成生产级长期投递 | `memory_engine/copilot/review_inbox.py`、`memory_engine/copilot/feishu_live.py`、`memory_engine/feishu_cards.py`、`memory_engine/feishu_events.py`、`memory_engine/feishu_publisher.py`、`scripts/openclaw_feishu_card_action_router.py`、`scripts/check_feishu_review_delivery_gate.py`、`tests/test_copilot_review_inbox.py`、`tests/test_copilot_feishu_live.py`、`tests/test_feishu_publisher.py`、`tests/test_openclaw_feishu_card_action_router.py`、`tests/test_feishu_review_delivery_gate.py` |
| 候选记忆治理 | 已完成 candidate / confirm / reject / conflict / version chain | `memory_engine/copilot/governance.py` |
| 检索链路 | 已完成 L0/L1/L2/L3 分层混合检索 | `memory_engine/copilot/orchestrator.py`、`retrieval.py` |
| 审计表 | 已完成 SQLite 本地审计闭环 | `memory_engine/db.py`、`memory_audit_events` |
| 存储迁移和备份恢复 | 已完成本地 migration dry-run / apply、索引检查，以及 SQLite staging backup / verify / restore drill；这不是生产 PostgreSQL / PITR | `scripts/migrate_copilot_storage.py`、`scripts/backup_copilot_storage.py`、`tests/test_copilot_storage_migration.py`、`tests/test_storage_backup.py` |
| 企业图谱群/用户/消息拓扑 | 已完成本地 Feishu 群节点发现与授权消息拓扑：新群会登记为同企业下的 `feishu_chat` 图谱节点；未在 allowlist 的群只记录 org/chat 最小元数据；授权群会把同一用户建模为 tenant/org 内唯一 `feishu_user` 节点，并用 membership/message 边表达其在不同群里的上下文；消息正文仍只进入 `raw_events` / candidate evidence，不写入图谱节点 | `memory_engine/copilot/graph_context.py`、`memory_engine/copilot/feishu_live.py`、`tests/test_copilot_feishu_live.py`、`docs/productization/handoffs/feishu-group-graph-node-handoff.md` |
| LLM Wiki / Graph Admin | 已完成本地 / staging 后台：active curated memory 编译成 LLM Wiki，Graph tab 展示 storage graph + compiled memory graph，Tenants tab 支持 tenant/org 过滤、readiness、admin-only tenant policy editor 和 `tenant_policy_upserted` 审计；Groups tab/API 展示 Feishu 群策略的 pending/active/disabled 与 passive 筛选状态；这不是生产 DB、真实企业 IdP SSO 或完整多租户权限后台 | `memory_engine/copilot/admin.py`、`memory_engine/db.py`、`scripts/check_copilot_admin_readiness.py`、`scripts/check_copilot_admin_ui_smoke.py`、`tests/test_copilot_admin.py`、`docs/productization/admin-llm-wiki-launch-runbook.md` |
| Cognee 主路径 | 已完成本地可控同步 / 检索 / fallback 闭环；当前 SDK metadata-optional / async 形态已兼容；真实 Cognee curated sync gate 已按 `.env.local` provider 配置跑通隔离 store 的 `CopilotService.confirm -> Cognee add -> cognify`，`fallback=null`；已新增持久 store readback gate、embedding health sampler、sampler status gate 和 long-run evidence collector。2026-05-03 复核 `logs/cognee-embedding-long-run/2026-05-02-sampler/cognee-long-run-evidence.json`：sampler status `completion_ready=true`、5 个成功样本、窗口 24.0015h，completion audit item 8 可 pass；这仍是本地/staging 长跑证据，不是生产持久化 Cognee 服务，生产级长期 embedding 服务仍未完成 | `memory_engine/copilot/cognee_adapter.py`、`memory_engine/copilot/retrieval.py`、`scripts/check_cognee_curated_sync_gate.py`、`scripts/check_cognee_persistent_readback.py`、`scripts/sample_cognee_embedding_health.py`、`scripts/check_cognee_embedding_sampler_status.py`、`scripts/collect_cognee_embedding_long_run_evidence.py`、`tests/test_copilot_cognee_adapter.py`、`tests/test_cognee_curated_sync_gate.py`、`tests/test_cognee_persistent_readback.py`、`tests/test_cognee_embedding_health_sampler.py`、`tests/test_cognee_embedding_sampler_status.py`、`tests/test_cognee_embedding_long_run_evidence.py`、`docs/productization/handoffs/cognee-main-path-handoff.md` |
| Feishu live sandbox | 已完成受控测试群联调和本地/pre-production 群策略 onboarding；当前稳定路径是 allowlist 测试群或显式 `/enable_memory` 启用的群，群内非 `@Bot` 消息可静默探测 candidate，`@Bot` / 私聊走主动交互 | `memory_engine/copilot/feishu_live.py`、`scripts/start_copilot_feishu_live.sh`、`tests/test_copilot_feishu_live.py` |
| 群级设置和启停 | 已完成群级设置卡和策略写入：`/settings` / `/group_settings` 展示 allowlist 与当前群策略；`/enable_memory` / `/disable_memory` 需要 reviewer/admin 授权后写 `feishu_group_policies`，并写审计；新群默认 `pending_onboarding`，不会自动记录消息内容 | `memory_engine/copilot/feishu_live.py`、`memory_engine/copilot/group_policies.py`、`memory_engine/feishu_cards.py`、`tests/test_copilot_feishu_live.py`、`tests/test_feishu_interactive_cards.py` |
| Limited Feishu ingestion | 已完成本地受控 ingestion 底座，支持文档、任务、会议、Bitable，以及 allowlist / 已启用群策略中被动探测或显式路由到 `memory.create_candidate` 的飞书消息；当前新增 review policy：低重要性安全候选可自动确认，重要/敏感/冲突候选仍需人工确认；这不是被动全量群聊摄入 | `memory_engine/document_ingestion.py`、`memory_engine/copilot/review_policy.py`、`tests/test_document_ingestion.py`、`tests/test_copilot_review_policy.py` |
| 真实 Feishu API 拉取入口 | 已完成任务、会议、Bitable 读取 fetcher、Feishu live `/task` / `/meeting` / `/bitable` 路由和 fetch 前 fail-closed 权限门控；Bitable fetcher 已兼容当前 lark-cli 1.0.22 的 `tables`、二维 `data`、字段直挂 `record` 输出形状；结果进入 `memory.create_candidate` 后由 review policy 决定自动确认或人工审核 | `memory_engine/feishu_task_fetcher.py`、`memory_engine/feishu_meeting_fetcher.py`、`memory_engine/feishu_bitable_fetcher.py`、`memory_engine/copilot/tools.py`、`memory_engine/copilot/review_policy.py`、`tests/test_feishu_fetchers.py`、`tests/test_copilot_review_policy.py` |
| Workspace ingestion pilot | 已新增 lark-cli-first 的受控 workspace adapter：`drive +search`、Drive folder/root walk、Wiki space walk 和显式 `--resource type:token[:title]` 均可发现 doc/docx/wiki/sheet/bitable 资源，按类型路由到 docs/sheets/base fetcher，再统一进入 `FeishuIngestionSource -> ingest_feishu_source() -> CopilotService` candidate pipeline；已补 SQLite source registry / run registry / discovery cursor，支持 revision 去重、unchanged skip、同 discovery filter 的 stale 标记、fetch failure/revocation、`--resume-cursor`、`--skip-discovery` 和 direct walk `--doc-types`。真实只读 discovery、公开模板 Sheet、项目 docx/Base、真实 chat log + workspace resource、registry skip/stale/failed、mixed-source corroboration、warm-path latency 和真实 lark-cli fetch latency gate 均已跑通。早期 broad search 保留为 organic gap 证据：当前账号没有自然出现的项目 normal Sheet 和同结论样本；用户批准后创建受控 normal Sheet，并由真实 OpenClaw Feishu 群消息复述同一 durable fact。最终受控 readiness 已通过：`eligible_project_normal_sheet_count=1`、`same_fact_match_count=1`、strict source types 为 `feishu_message + lark_sheet`，`check_workspace_ingestion_goal_readiness.py` 返回 `goal_complete=true`、`status=pass`、`failures=[]`。2026-05-04 又补了 bot 单聊 `/recall Workspace ingestion readiness gate Sheet 样本`，通过 `fmc_memory_search` 回读 workspace Sheet 记忆和 `lark_sheet` 证据；11:47、12:53 和 13:08 自动复测都通过。这只是 limited workspace pilot / controlled readiness，不是生产全量 workspace ingestion、长期 crawler、生产 SLO 或 productized live | `memory_engine/feishu_workspace_fetcher.py`、`memory_engine/feishu_workspace_registry.py`、`memory_engine/feishu_bitable_fetcher.py`、`scripts/feishu_workspace_ingest.py`、`scripts/check_feishu_workspace_registry_gate.py`、`scripts/check_workspace_mixed_source_corroboration_gate.py`、`scripts/check_workspace_ingestion_latency_gate.py`、`scripts/check_workspace_real_fetch_latency_gate.py`、`scripts/check_workspace_project_sheet_evidence_gate.py`、`scripts/check_workspace_real_chat_resource_gate.py`、`scripts/check_workspace_real_same_conclusion_gate.py`、`scripts/check_workspace_real_same_conclusion_sample_finder.py`、`scripts/check_workspace_ingestion_goal_readiness.py`、`scripts/check_feishu_dm_routing.py`、`tests/test_feishu_workspace_fetcher.py`、`tests/test_feishu_workspace_registry.py`、`tests/test_workspace_real_fetch_latency_gate.py`、`tests/test_workspace_project_sheet_evidence_gate.py`、`tests/test_workspace_real_chat_resource_gate.py`、`tests/test_workspace_real_same_conclusion_gate.py`、`tests/test_workspace_real_same_conclusion_sample_finder.py`、`tests/test_workspace_ingestion_goal_readiness.py`、`tests/test_feishu_dm_routing.py`、`docs/productization/workspace-ingestion-architecture-adr.md`、`docs/productization/workspace-ingestion-goal-completion-audit-2026-05-04.md` |
| Productized workspace ingestion gate | 已新增严格生产化证据 gate：只有非示例 manifest 同时证明 organic source adapter coverage、workspace surface coverage、scheduler/cursor、rate-limit/backoff、governance、operations 和 24h+ long-run，才允许 `goal_complete=true`。默认示例 manifest 会返回 `status=blocked`，防止把 limited pilot 写成全量 workspace ingestion。2026-05-04 已补一轮非示例 partial manifest：`source_coverage` 覆盖 `document_feishu=6`、`lark_sheet=2`、`lark_bitable=6`，workspace surface 覆盖 `document=2`、`sheet=3`、`bitable=2`、`wiki=1`；`discovery_and_cursoring`、`governance`、`operations`、`rate_limit_and_backoff` 均已 pass。当前唯一 blocker 是 `live_long_run.duration_hours_at_least_24`：4 次非 dry-run schedule execute 成功，但窗口只有 `0.191h`，还不能宣称生产全量 workspace ingestion | `scripts/check_workspace_productized_ingestion_readiness.py`、`deploy/workspace-ingestion.production-evidence.example.json`、`tests/test_workspace_productized_ingestion_readiness.py` |
| Workspace objective completion audit | 已新增 objective-level completion audit，可把用户 1-6 项要求映射到具体 artifact，并把最终完成判定绑定到 productized readiness gate。当前默认 example manifest 下会返回 `goal_complete=false`，说明 artifact 路径齐了，但全量 workspace 接入证据还没齐 | `scripts/check_workspace_ingestion_objective_completion.py`、`tests/test_workspace_ingestion_objective_completion.py` |
| Workspace source coverage collector | 已新增 source coverage evidence collector，可从已有真实 gate / workspace ingest / schedule result 报告里抽取 source adapter 覆盖（`document_feishu`、`lark_sheet`、`lark_bitable`）、workspace surface 覆盖（`document`、`sheet`、`bitable`、`wiki`）、same-conclusion 佐证和 conflict negative 证据，并输出 `production_manifest_patch.source_coverage`。它只归一化已存在的脱敏证据，不运行 ingestion、不证明生产全量完成；当前已修正 sanitized report 同时带 `source_type_counts` 和 `results` 时的重复计数问题，并避免把 Wiki surface 误当成 source type | `scripts/collect_workspace_source_coverage_evidence.py`、`tests/test_workspace_source_coverage_evidence.py` |
| Workspace ops/governance evidence collector | 已新增 ops/governance/rate-limit evidence collector，可把外部已验证的 timeout/backoff/rate-limit、review policy、permission negative、curated-only embedding、audit readback、single listener、monitoring、rollback、retention 和 operator readback 证据整理成 `rate_limit_and_backoff`、`governance`、`operations` 三个 manifest patch section。它只归一化证据，不运行生产 ingestion | `scripts/collect_workspace_ops_governance_evidence.py`、`tests/test_workspace_ops_governance_evidence.py` |
| Workspace productized evidence merger | 已新增 productized evidence patch merger，可把 source coverage、scheduler/long-run、rate-limit、governance、operations 等 collector 输出的 `production_manifest_patch` 合并成非示例 manifest，并立即复用 productized gate 验证；会拒绝未知 section、placeholder 和 secret-like 值。它只降低手工拼 JSON 风险，不替代真实生产证据 | `scripts/merge_workspace_productized_ingestion_evidence.py`、`tests/test_workspace_productized_ingestion_evidence_merge.py` |
| Workspace ingestion schedule runner | 已新增 one-shot schedule runner，可从 JSON schedule 构造 bounded `feishu_workspace_ingest.py` job；默认 plan-only 无外部副作用，显式 `--execute` 才串行执行。非 dry-run job 必须带 actor，command preview 会遮蔽资源 token、actor/user/chat id，并支持 bounded retry/backoff。`--output` 会写脱敏 evidence report；同用 `--json` 时 stdout 也输出脱敏版本，保留资源类型和 source type 统计但移除 token/URL/source id/cursor。它补齐 scheduler 入口和受控执行证据，但还不是 24h+ productized long-run evidence | `scripts/run_workspace_ingestion_schedule.py`、`deploy/workspace-ingestion.schedule.example.json`、`tests/test_workspace_ingestion_schedule.py` |
| Workspace ingestion schedule sampler | 已新增周期采样器，可按 `sample-count` / `interval-seconds` 连续运行 schedule runner，并把每轮脱敏 report、NDJSON index 和 `sampler-status.json` 写到本地证据目录。默认 plan-only；显式 `--execute` 才运行 bounded schedule。2026-05-04 隔离 DB 非 dry-run sampler 跑了 2 次，真实 fetch/candidate pipeline 通过，资源统计为 `bitable=2`、`docx=2`、`sheet=1`；采样窗口只有 0.0129h，仍不能宣称 productized full-workspace readiness | `scripts/sample_workspace_ingestion_schedule.py`、`tests/test_workspace_ingestion_schedule_sampler.py` |
| Workspace ingestion long-run collector | 已新增 schedule long-run collector 和 one-tick runner，可读取多份脱敏 schedule report，计算成功运行次数、时间窗口、资源类型分布和未解决失败，并生成 production manifest patch。2026-05-04 13:38 已安装本机 launchd job `com.feishu-ai-challenge.workspace-ingestion-longrun`，每 4 小时跑一轮受控 non-dry-run schedule，并自动重算 `productized-evidence.active.json`、`workspace-objective-completion.active.json` 和 `workspace-productized-finalization.active.json`。当前 11 次非 dry-run report 已让 `successful_runs_at_least_3` 通过，`revision_skip_proven=true`、`revocation_proven=true`、`stale_marking_proven=true`、`cursor_resume_proven=true`；仍因 `window_hours=1.4839` 未满足 24h+ | `scripts/collect_workspace_ingestion_long_run_evidence.py`、`scripts/run_workspace_ingestion_long_run_tick.py`、`tests/test_workspace_ingestion_long_run_evidence.py`、`tests/test_workspace_ingestion_long_run_tick.py` |
| Workspace productized evidence finalizer | 已新增只读 finalizer，可在 24h 长跑期间或结束后重新跑 productized readiness gate 和 objective completion audit，写出 `workspace-productized-finalization.active.json`。`run_workspace_ingestion_long_run_tick.py` 现在会在每轮 merge 成功后自动写 finalization status，所以 launchd 收集满 24h 后不需要手工拼 finalizer 命令。2026-05-04 当前复跑结果为 `goal_complete=false`，唯一 readiness blocker 仍是 `live_long_run.duration_hours_at_least_24`；最新 active finalization 读回 11 次成功、0 unresolved failure、`window_hours=1.4839`。这个脚本不启动监听、不发送飞书消息、不自动关闭目标 | `scripts/finalize_workspace_ingestion_productized_evidence.py`、`scripts/run_workspace_ingestion_long_run_tick.py`、`tests/test_finalize_workspace_ingestion_productized_evidence.py`、`tests/test_workspace_ingestion_long_run_tick.py` |
| 审计查询、告警和运维面 | 已完成本地审计查询/导出、audit read-only live gate、告警脚本、ingestion failure 显式审计、healthcheck websocket 运维入口、embedding fallback 可观测字段，以及 staging Prometheus alert-rule artifact / verifier；这仍不是生产级 Prometheus/Grafana 长期监控 | `scripts/query_audit_events.py`、`scripts/check_copilot_audit_readonly_gate.py`、`scripts/check_audit_alerts.py`、`scripts/check_prometheus_alert_rules.py`、`deploy/monitoring/copilot-admin-alerts.yml`、`memory_engine/document_ingestion.py`、`memory_engine/copilot/healthcheck.py`、`tests/test_audit_ops_scripts.py`、`tests/test_prometheus_alert_rules.py`、`docs/productization/handoffs/audit-ops-observability-handoff.md` |
| Productized live 长期运行方案 | 已完成方案和上线 gate，覆盖部署拓扑、单监听、存储、监控告警、权限后台、审计 UI、停写回滚和 no-overclaim 边界；尚未实施生产长期运行 | `docs/productization/productized-live-long-run-plan.md`、`docs/productization/handoffs/productized-live-long-run-plan-handoff.md` |
| OpenClaw Feishu websocket staging | 已完成本机 running 证据 | `scripts/check_openclaw_feishu_websocket.py`、`docs/productization/handoffs/openclaw-feishu-websocket-handoff.md` |
| 非 @ 群消息事件 gate | 已新增脱敏事件日志检查脚本，可解析 Feishu 原始 payload、NDJSON wrapper、Copilot listener `raw_line` wrapper 和 OpenClaw channel log；2026-05-02 受控日志证明一条普通非 @ 文本进入 OpenClaw websocket，`feishu-live-evidence-packet.json` 中 `passive_group_message.reason=passive_group_message_seen`。2026-05-03 泛化 read-only preflight 在缺少目标群读权限证明时仍会 fail closed，因此新群/新环境扩样前必须重新跑 event diagnostics 和 target group probe | `scripts/check_feishu_passive_message_event_gate.py`、`scripts/check_feishu_event_subscription_diagnostics.py`、`tests/test_feishu_passive_message_event_gate.py`、`tests/test_feishu_event_subscription_diagnostics.py`、`docs/productization/handoffs/feishu-passive-message-event-gate-handoff.md` |
| 九项 productization completion audit | 已新增总审计 gate，把非 @ live 投递、单监听、first-class routing、权限负例、review DM/card、Dashboard auth、clean demo DB、Cognee/embedding 长跑和 no-overclaim 映射到具体证据；2026-05-03 复核命令 `python3 scripts/check_openclaw_feishu_productization_completion.py --feishu-live-evidence-packet logs/feishu-live-evidence-runs/20260502T085247Z/feishu-live-evidence-packet.json --feishu-event-diagnostics logs/feishu-live-evidence-runs/20260502T085247Z/00-feishu-event-diagnostics.json --cognee-long-run-evidence logs/cognee-embedding-long-run/2026-05-02-sampler/cognee-long-run-evidence.json --json` 返回 `goal_complete=true`。这只证明 demo/pre-production completion gate，不代表生产部署或长期线上运行完成 | `scripts/check_openclaw_feishu_productization_completion.py`、`tests/test_openclaw_feishu_productization_completion.py` |
| Feishu live evidence packet | 已新增脱敏证据包 collector，可把非 @ 群消息、first-class `fmc_*` routing、第二真实用户 deny 和 `/review` DM/card 四类真实日志统一跑 gate 后输出 sanitized packet；completion audit 可用 `--feishu-live-evidence-packet` 读取该 packet，仍要求每个 gate 的 exact pass reason | `scripts/collect_feishu_live_evidence_packet.py`、`tests/test_feishu_live_evidence_packet.py` |
| Feishu live evidence run preflight | 已新增非发送型 live run 预检：检查当前单监听 owner 和 group-message event scope，生成四类日志路径、人工消息步骤、operator checklist、Feishu console remediation guide、packet 命令和 completion audit 命令；2026-05-02 受控 evidence packet 已通过 event diagnostics、target group read probe 和四类 live gate；2026-05-03 未带目标群证明的 read-only run 已写出 `logs/feishu-live-evidence-runs/20260503T111326Z/operator-checklist.md` 并按 schema 缺 group-message scope fail closed。当前机器只看到 `openclaw-gateway`，因此计划 listener 应保持 `openclaw-websocket`，不要再启动 lark-cli listener 抢同一个 bot | `scripts/prepare_feishu_live_evidence_run.py`、`scripts/check_feishu_event_subscription_diagnostics.py`、`tests/test_prepare_feishu_live_evidence_run.py`、`tests/test_feishu_event_subscription_diagnostics.py` |
| Demo readiness | 已完成一键检查 | `scripts/check_demo_readiness.py` |
| Benchmark | 已完成多类评测样例 | `benchmarks/copilot_*.json`、`docs/benchmark-report.md` |
| Deep research 改进闭环 | 已完成第一轮代码收口：stable memory key / alias 层、score breakdown 输出、stale shadow filter、deterministic embedding fallback、graph review target / prefetch context、conflict/reject benchmark runner 修正、组合式 search 摘要、本地编译型记忆卡册，以及受控真实 Feishu Task fetch -> candidate smoke；最新本地重跑显示 recall 40/40、conflict 35/35、prefetch 20/20 均通过，stale leakage 均为 0.0000；仍保留 productized live 长期运行为后续风险 | `memory_engine/copilot/stable_keys.py`、`memory_engine/copilot/governance.py`、`memory_engine/copilot/review_inbox.py`、`memory_engine/copilot/knowledge_pages.py`、`memory_engine/feishu_task_fetcher.py`、`memory_engine/benchmark.py`、`tests/test_copilot_stable_keys.py`、`tests/test_copilot_review_inbox.py`、`tests/test_copilot_prefetch.py`、`tests/test_feishu_fetchers.py`、`tests/test_copilot_knowledge_pages.py`、`docs/productization/deep-research-improvement-backlog.md` |
| 复赛 / 比赛收尾材料 | 已完成叙事收束：方向 B 为主、方向 D 为辅；白皮书、Demo runbook、Benchmark report 和 10 分钟评委体验包已统一成“企业记忆治理层、三幕 Demo、三类赛题证明、no-overclaim 边界” | `docs/productization/finals-closeout-todo.md`、`docs/memory-definition-and-architecture-whitepaper.md`、`docs/demo-runbook.md`、`docs/benchmark-report.md`、`docs/judge-10-minute-experience.md` |
| 白皮书 / 答辩材料 | 已完成初稿和 10 分钟评委体验包，放在后半部分查看 | `docs/memory-definition-and-architecture-whitepaper.md`、`docs/demo-runbook.md`、`docs/judge-10-minute-experience.md` |

### 不能 overclaim

不能说已经完成：

- 生产部署。
- 全量接入飞书 workspace。
- 多租户企业后台。
- 长期 embedding 服务。
- 真实 Feishu DM 长期稳定路由到本项目 first-class `fmc_*` / `memory.*` 工具链路。
- productized live 长期运行。

### 当前最重要的后续项

- 扩大真实飞书样本：继续覆盖 Meeting、Bitable、更多真实表达和权限负例。
- 扩大 workspace pilot：从受控 Sheet 扩到更多 organic Docx、Sheet、Base/Bitable、Wiki space，并保留失败和审计证据。
- 补足 productized workspace ingestion：当前 production/full-workspace gate 的主要 blocker 仍是 24h+ long-run evidence。
- 维护评委材料和用户体验：只在证据变化时更新白皮书、Demo、Benchmark 和 10 分钟评委包。

---

## 2. 快速开始

最小验收：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_copilot_health.py --json
python3 scripts/check_demo_readiness.py --json
```

如果要在另一台机器上快速部署到 demo / pre-production 可验收状态，先按 [跨平台快速部署 Runbook](docs/productization/cross-platform-quick-deploy.md) 走；它覆盖 macOS、Linux 和 Windows，并提供统一 preflight：

```bash
python scripts/check_cross_platform_quick_deploy.py --profile local-demo --json
python scripts/check_cross_platform_quick_deploy.py --profile openclaw-staging --json
```

这个 preflight 只证明新机器具备本地 demo / staging 条件，不代表生产部署、全量 Feishu workspace ingestion 或 productized live 长期运行完成。

如果要人工确认自动测试背后的真实体验，按 [手动测试指南](docs/manual-testing-guide.md) 走：它覆盖本地 replay、OpenClaw `fmc_*` 工具、受控 Feishu DM、review policy、权限负例、审计读回和截图记录。

### 2.1 初始化环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2.2 初始化本地数据库

```bash
python3 -m memory_engine init-db
```

默认数据库路径：

```text
data/memory.sqlite
```

也可以通过环境变量指定：

```bash
export MEMORY_DB_PATH=/tmp/memory.sqlite
```

### 2.3 配置 Cognee（可选）

Cognee 是可选 recall channel。默认 demo / benchmark 可以走 repository fallback；只有要验证真实 Cognee 同步、检索或 embedding provider 时才需要配置。

复制 `.env.example` 到 `.env`：

```bash
cp .env.example .env
```

然后配置这些关键变量：

```text
# LLM 配置（Cognee 推理需要）
LLM_PROVIDER=custom
LLM_MODEL=gpt-5.3-codex-high
LLM_ENDPOINT=https://right.codes/codex/v1
LLM_API_KEY=your_rightcode_api_key_here  # 必填

# Embedding 配置（本地 Ollama）
EMBEDDING_MODEL=ollama/qwen3-embedding:0.6b-fp16
EMBEDDING_ENDPOINT=http://localhost:11434
EMBEDDING_DIMENSIONS=1024
```

如果使用本地 Ollama embedding，确保服务和模型存在：

```bash
ollama serve
ollama pull qwen3-embedding:0.6b-fp16
```

验证 Cognee 配置：

```bash
python3 scripts/spike_cognee_local.py --dry-run
python3 scripts/spike_cognee_local.py --scope project:feishu_ai_challenge --query "测试查询"
```

当前 `CogneeMemoryAdapter` 已兼容 SDK 的 metadata-optional / async 调用形态。`scripts/check_cognee_curated_sync_gate.py --json` 会在隔离 store 上跑 `CopilotService.confirm -> Cognee add -> cognify`，并按 `process env > .env.local > .env > defaults` 解析 provider/model，避免误用本地默认 Ollama。

长期证据相关脚本只采集和规范 evidence，不创建长期服务：`scripts/check_cognee_persistent_readback.py`、`scripts/sample_cognee_embedding_health.py`、`scripts/collect_cognee_embedding_long_run_evidence.py`。这里的 Cognee gate 仍是本地/staging 证据，不是生产持久化 Cognee store。

配置字段说明：

- `LLM_PROVIDER`：使用 `custom` 配合 RightCode 服务。
- `LLM_API_KEY`：RightCode API 密钥。
- `EMBEDDING_MODEL`：默认本地 Ollama `qwen3-embedding:0.6b-fp16`。
- `EMBEDDING_ENDPOINT`：Ollama 服务地址，默认 `http://localhost:11434`。

如需使用其他 embedding 模型，可参考 `docs/reference/local-windows-cognee-embedding-setup.md` 中的备选方案。

### 2.4 运行本地健康检查

```bash
python3 scripts/check_copilot_health.py
python3 scripts/check_copilot_health.py --json
```

健康检查会覆盖：

- OpenClaw 版本。
- CopilotService 初始化。
- OpenClaw tool schema。
- SQLite storage schema。
- permission fail-closed。
- search smoke test。
- candidate review smoke test。
- audit smoke test。
- Cognee adapter 状态（检查 SDK 可用性、配置有效性、是否已注入客户端）。
- Embedding provider 状态（检查配置和本地 Ollama 服务）。
- first-class OpenClaw tool registry 状态。

#### Cognee Adapter 状态说明

健康检查中 `cognee_adapter` 的状态含义：

- **pass**: Cognee SDK 已安装，配置有效，客户端已注入，可正常使用。
- **warning**: Cognee SDK 已安装，配置有效，但客户端未自动注入（需要在代码中显式初始化）。
- **fallback_used**: Cognee SDK 未安装或配置无效，使用 repository 回退。
- **fail**: Cognee adapter 导入或初始化失败。

如需真实 Cognee 运行，请确保：

1. Cognee SDK 已安装（`pip install cognee`）
2. `.env` 文件中配置了有效的 `LLM_API_KEY`
3. Ollama 服务正在运行并已拉取 embedding 模型

#### Embedding Provider 状态说明

健康检查中 `embedding_provider` 的状态含义：

- **pass**: OllamaEmbeddingProvider 已配置并可用，可生成真实语义向量。
- **warning**: litellm 已安装但 Ollama 服务不可用，使用 DeterministicEmbeddingProvider 作为 fallback。
- **not_configured**: litellm 未安装，无法使用真实 embedding。

验证 embedding 服务：

```bash
# 检查 embedding 提供者状态
python3 scripts/check_embedding_provider.py --timeout 60

# 运行完整的 live embedding gate 测试
python3 scripts/check_live_embedding_gate.py --json

# 运行带有 live embedding check 的健康检查
python3 scripts/check_copilot_health.py --json --live-embedding-check
```

Embedding 配置参数（在 `memory_engine/copilot/embedding-provider.lock` 中）：

| 参数 | 默认值 | 说明 |
|---|---|---|
| provider | ollama | Embedding 提供者 |
| model | qwen3-embedding:0.6b-fp16 | Ollama 模型名称 |
| litellm_model | ollama/qwen3-embedding:0.6b-fp16 | litellm 模型标识 |
| endpoint | http://localhost:11434 | Ollama 服务地址 |
| dimensions | 1024 | 向量维度 |

### 2.5 本地 LLM Wiki / 知识图谱后台

Dashboard 不是单独的产品服务。它提供本地 LLM Wiki、知识图谱、tenant readiness、memory ledger、audit 和 schema table 视图，用于把 active curated memory 编译成可展示的企业知识资产，同时观察 Feishu 群/用户/消息图谱拓扑。Graph tab 会展示节点/边详情和 Relationship Focus 邻接路径，便于从 active memory 追到 evidence source。Wiki / Graph / Ledger / Audit 仍是只读知识面；Tenants tab 已有 admin-only 的本地/pre-production 租户策略编辑入口，可配置默认 visibility、reviewer roles、admin users、SSO allowed domains、低风险 auto-confirm 和冲突人工审核开关。Wiki / Graph / Tenants / Ledger / Audit 支持按 `tenant_id` 和 `organization_id` 收敛展示；这仍不等于生产 DB、真实企业 IdP SSO 验收或 productized live。Feishu live listener 默认会随 runtime 启动；OpenClaw 插件侧为避免工具加载副作用，必须显式 opt-in：

- OpenClaw 加载 `feishu-memory-copilot` 插件时，只有 `FEISHU_MEMORY_COPILOT_ADMIN_ENABLED=1` 或 `COPILOT_ADMIN_ENABLED=1` 才会尝试启动本地 dashboard。
- 仓库内 `python3 -m memory_engine copilot-feishu listen` / `scripts/start_copilot_feishu_live.sh` 启动时，也会带起 dashboard。

默认访问地址：

```text
http://127.0.0.1:8765
```

可用环境变量：

```bash
export FEISHU_MEMORY_COPILOT_ADMIN_ENABLED=1
export FEISHU_MEMORY_COPILOT_ADMIN_HOST=127.0.0.1
export FEISHU_MEMORY_COPILOT_ADMIN_PORT=8765
export FEISHU_MEMORY_COPILOT_ADMIN_TOKEN=change-me-local-token
export FEISHU_MEMORY_COPILOT_ADMIN_VIEWER_TOKEN=change-me-readonly-token
# Optional reverse-proxy SSO gate; keep backend bound to 127.0.0.1.
export FEISHU_MEMORY_COPILOT_ADMIN_SSO_ENABLED=1
export FEISHU_MEMORY_COPILOT_ADMIN_SSO_ADMIN_USERS=admin@example.com
export FEISHU_MEMORY_COPILOT_ADMIN_SSO_ALLOWED_DOMAINS=example.com
```

如果只是本机调试，不启动 OpenClaw / Feishu listener，也可以手动运行 fallback 脚本。SSO header gate 只用于本机反向代理转发场景，直接远程绑定仍需要 bearer token 或会被启动脚本拒绝：

```bash
python3 scripts/start_copilot_admin.py
```

后台默认读取 `data/memory.sqlite`，也可以指定数据库和端口：

```bash
python3 scripts/start_copilot_admin.py --db-path /path/to/memory.sqlite --port 8766
```

如果绑定到非本机地址，必须设置 `FEISHU_MEMORY_COPILOT_ADMIN_TOKEN` / `FEISHU_MEMORY_COPILOT_ADMIN_VIEWER_TOKEN`，或传 `--admin-token` / `--viewer-token`；否则启动脚本会拒绝运行。admin token 可读取 `/api/*`、导出 Wiki Markdown 并保存 `/api/tenant-policies`；viewer token 只能读取 `/api/*`，访问 `/api/wiki/export` 或提交租户策略会返回 `403`。页面会在首次加载数据时提示输入 token。

主要 API：

```text
/api/wiki                active curated memory 编译视图，不包含 raw events，不写飞书
/api/wiki/export?scope=  指定 scope 的 Markdown Wiki 导出，只接受 admin token，仍只读 SQLite
/api/graph               知识图谱节点/关系视图
/api/graph-quality       图谱质量 gate：compiled memory graph、边端点、tenant 覆盖、孤立节点和敏感字段泄漏
/api/tenants             ledger + tenant policy 派生的 tenant / organization readiness 概览
/api/tenant-policies     GET 读取租户策略；POST 仅 admin 可 upsert 本地/pre-production 租户策略
/api/memories            memory ledger 和 evidence
/api/audit               权限、治理和工具调用审计
/api/launch-readiness   staging gate、生产 blocker 和上线证据摘要
/api/production-evidence 生产证据 manifest gate 读回；默认 production_ready=false
/api/health              带认证的后台 readiness 摘要
/metrics                 Prometheus text metrics；共享环境下需要 admin/viewer token 或 SSO
/healthz                 不含敏感数据的进程 liveness 探活
```

`/api/wiki`、`/api/graph`、`/api/tenants`、`/api/memories`、`/api/audit` 都接受 `tenant_id` / `organization_id` 查询参数，用于受控 staging 下按企业租户边界检查后台展示结果。

上线前或共享给评委/队友前，先跑后台 readiness gate：

```bash
python3 scripts/check_copilot_admin_readiness.py --db-path data/memory.sqlite
python3 scripts/check_copilot_admin_readiness.py --db-path data/memory.sqlite --host 0.0.0.0 --admin-token "$FEISHU_MEMORY_COPILOT_ADMIN_TOKEN" --viewer-token "$FEISHU_MEMORY_COPILOT_ADMIN_VIEWER_TOKEN" --strict --min-wiki-cards 1
python3 scripts/check_copilot_admin_env_file.py --expect-example --json
python3 scripts/check_copilot_admin_deploy_bundle.py --json
python3 scripts/check_copilot_admin_sso_gate.py --json
python3 scripts/check_copilot_audit_readonly_gate.py --json
python3 scripts/export_copilot_admin_launch_evidence.py --db-path data/memory.sqlite --output-dir /tmp/copilot-admin-launch-evidence --scope project:feishu_ai_challenge --tenant-id tenant:demo --organization-id org:demo --audit-min-events 1 --json
python3 scripts/check_copilot_admin_production_evidence.py --json
python3 scripts/check_copilot_knowledge_site_export.py --json
python3 scripts/check_copilot_graph_quality.py --json
python3 scripts/check_llm_wiki_enterprise_site_completion.py --json
python3 scripts/check_copilot_admin_ui_smoke.py --db-path data/memory.sqlite --scope project:feishu_ai_challenge --output-dir /tmp/copilot-admin-ui-smoke --json
python3 scripts/check_prometheus_alert_rules.py --json
```

`check_copilot_admin_sso_gate.py` 会在 loopback 上启动临时 admin server，验证无 header 拒绝、allowed-domain viewer 只读、admin SSO 身份可导出 Wiki、`/metrics` 需要认证、`/api/health` 报告 SSO policy。它只证明反向代理 header gate 的 staging 行为，不等于真实企业 IdP / Feishu SSO 生产验收。

`check_copilot_admin_env_file.py` 默认校验 `deploy/copilot-admin.env.example` 是否保持安全占位符；传 `--env-file /etc/feishu-memory-copilot/admin.env --expect-runtime --json` 可校验本机真实 runtime env 是否替换 token、端口合法、远程绑定有 token、SSO 配置完整。报告只输出 redacted state，不输出 token 明文。

`check_copilot_admin_deploy_bundle.py` 会检查 systemd / Nginx / TLS 模板、SSO header 边界、DB / IdP / TLS / monitoring live probe、monitoring alert artifact、backup gate、readiness gate 和 completion audit gate；当前预期输出是 `staging_bundle_ok=true` 且 `production_blocked=true`。

`check_openclaw_feishu_productization_completion.py` 会把本轮九项 productization completion gate 映射到真实 gate 和 artifact：非 @ 群文本、first-class `fmc_*` 成功结果、第二真实用户 deny、真实 `/review` DM/update-card，以及 Cognee/embedding 持久 long-run 证据。2026-05-03 复核时，传入 `logs/feishu-live-evidence-runs/20260502T085247Z/feishu-live-evidence-packet.json`、同目录 `00-feishu-event-diagnostics.json` 和 `logs/cognee-embedding-long-run/2026-05-02-sampler/cognee-long-run-evidence.json` 后返回 `goal_complete=true`。传 `--output /path/to/audit.json` 可以保存完整 JSON，供 handoff 或证据包归档。注意：这个结果只证明 demo/pre-production gate 齐备，不代表生产部署、全量 workspace ingestion 或 productized live 长期运行。

`collect_feishu_live_evidence_packet.py` 会把四类 Feishu/OpenClaw live log 统一跑 gate，生成不含 raw 消息正文的 sanitized evidence packet。真实扩样时先用它生成 packet，再运行 `check_openclaw_feishu_productization_completion.py --feishu-live-evidence-packet <packet> --feishu-event-diagnostics <diag.json> --cognee-sampler-status <sampler-status.json> --cognee-long-run-evidence <json>`；packet 只是证据汇总，不能替代真实日志采集。

`prepare_feishu_live_evidence_run.py` 会在真实扩样前做单监听和 Feishu group-message access preflight，并生成一次 run 的日志路径、人工消息步骤、packet 命令和 completion audit 命令。带 `--create-dirs` 时还会写出 `operator-checklist.md`，方便测试者逐项执行并保留 no-overclaim 边界。它不会发送飞书消息或点击卡片；如果只看到泛化 `openclaw-gateway`，只有 `--planned-listener openclaw-websocket` 会通过，repo 内 lark-cli listener 应继续 fail closed；如果 scope metadata 还没列出 `im:message.group_msg`，但 bot 身份已经能读目标群，诊断会允许继续真实非 @ 群文本取证并保留 stale metadata warning，最终仍以 event log gate 为准。

`export_copilot_admin_launch_evidence.py` 会导出一个固定 JSON evidence bundle，包含 summary、Wiki、Graph、Graph Quality、Audit、Audit read-only gate、Launch readiness、deploy bundle、production evidence 和 completion audit。它只生成本地/staging launch evidence，manifest 仍会保留 `goal_complete=false` 和 production blockers，不代表生产上线完成。

`check_copilot_admin_production_evidence.py` 默认检查 `deploy/copilot-admin.production-evidence.example.json` 的结构和密钥脱敏，预期 `ok=true`、`production_ready=false`；真实上线时传入已填好的 manifest 并加 `--require-production-ready`，才会要求生产 DB、真实 IdP SSO、域名/TLS、生产监控和 24 小时 long-run 证据全部通过。

`collect_copilot_production_db_evidence.py` 会把真实 PostgreSQL / managed PostgreSQL 迁移、PITR 和恢复演练证据规范成 production evidence manifest 的 `production_db` patch；它只校验 evidence ref、时间戳和报告摘要，不创建或连接生产数据库。

`check_copilot_production_db_probe.py` 会从 `DATABASE_URL` 或显式 `--dsn-env` 指定的环境变量读取生产 PostgreSQL DSN，使用 `pg_isready` 和只读 `psql` 查询验证已存在端点可达、可认证和版本满足 PostgreSQL 15+，并输出可合并进 `production_db` 的 manifest patch；它不会打印 DSN，不创建数据库、不迁移、不启用 PITR、不备份或恢复，也不证明长期 live。

`collect_copilot_external_production_evidence.py` 会把真实企业 IdP / SSO、生产域名 TLS、Prometheus/Grafana/Alertmanager 投递证据规范成 production evidence manifest patch；它不执行真实登录、证书签发、Prometheus scrape 或告警投递。

`check_copilot_admin_idp_probe.py` 会对已经运行的生产 Admin URL 做 unauthenticated entrypoint probe，确认未登录访问 `/api/summary` 不会直接公开，并把真实 IdP 登录、admin 通过、viewer 导出拒绝、allowed domain 和证据 ref 规范成 `enterprise_idp_sso` manifest patch；它不执行交互式 IdP 登录，也不证明 DB、TLS、监控或长期 live。

`check_copilot_admin_tls_probe.py` 会对已经运行的生产 HTTPS URL 做 live probe，校验证书主机名、证书有效期和 `Strict-Transport-Security` header，并输出可合并进 `production_domain_tls` 的 manifest patch；它不签发证书、不配置 DNS，也不证明 IdP、监控、DB 或 24 小时 productized live。

`check_copilot_admin_monitoring_probe.py` 会对已经运行的生产 Admin URL 拉取 `/metrics`，校验核心 Copilot metrics、Grafana dashboard URL、Alertmanager route、告警投递测试时间和证据 ref，并输出可合并进 `production_monitoring` 的 manifest patch；它不配置 Prometheus/Grafana/Alertmanager，也不证明 DB、IdP、TLS 或长期 live。

`collect_copilot_admin_long_run_evidence.py` 会探测运行中的 Admin 后台 `/healthz`、`/api/health`、`/api/launch-readiness`、`/api/graph-quality` 和 `/metrics`，生成可合并到 production evidence manifest 的 `productized_live_long_run` patch；短跑 smoke 只证明采集器可用，不代表 productized live 长期运行完成。

`merge_copilot_production_evidence.py` 会把各 collector 输出的 `production_manifest_patch` 合并成 production evidence manifest，并立即复用 `check_copilot_admin_production_evidence.py` 验证；它只降低手工拼 JSON 的风险，不创建真实 DB、IdP、TLS、监控或长期运行证据。

`check_copilot_knowledge_site_export.py` 会导出一个临时静态知识站，并校验 `index.html`、`data/manifest.json`、`data/wiki.json`、`data/graph.json`、`data/graph-quality.json`、`wiki/*.md`、Graph detail / Relationship Focus / Graph quality UI、read-only boundary 和 secret-like 文本脱敏。

`check_copilot_graph_quality.py` 会检查本地/staging 知识图谱 workspace 是否有 `memory -> grounded_by -> evidence_source` 编译图谱、边端点完整性、tenant/org 覆盖、孤立节点比例和敏感字符串泄漏；它是图谱质量 gate，不代表生产级图谱治理后台。

`check_copilot_admin_design_system.py` 会检查 Admin 与静态知识站的 `data-design-system` 标记、共享 UI token，并拒绝旧米色/单一 palette 回流；它是本地/staging 设计一致性 gate，不代表完整设计系统组件库。

`check_copilot_admin_ui_smoke.py` 会启动本机 admin、导出静态站并截图，除桌面/移动端 Admin Graph、静态站 Relationship Focus、Tenants、Launch 和静态站 DOM 断言外，还会对截图做像素级非空白、色彩多样性、主色占比和文件大小检查。Admin 与静态知识站也带有 `data-design-system` 标记和共享 UI token，用于把本地/staging 后台维持在同一套中性企业后台视觉语言内。需要固定视觉基线时，先用 `--visual-baseline-dir reports/admin-ui-baseline --update-visual-baseline` 生成 `visual-baseline.json` 和 PNG 基线；后续传同一个 `--visual-baseline-dir` 会按截图逐张做采样 pixel diff，并用脚本内阈值阻断明显 UI 回归。这仍只证明本地/staging UI 回归，不代表生产上线。

`check_llm_wiki_enterprise_site_completion.py` 会把 LLM Wiki、知识图谱后台、UI smoke、上线 gate 和 no-overclaim 边界映射到具体 artifact；当前预期输出是 `staging_ok=true` 且 `goal_complete=false`，因为生产 DB、真实 IdP SSO、域名证书、生产监控和 productized live 长期运行仍未完成。

如需生成可放到受控内网或反向代理后的静态知识站包：

```bash
python3 scripts/export_copilot_knowledge_site.py --db-path data/memory.sqlite --output-dir reports/copilot-knowledge-site --scope project:feishu_ai_challenge --json
open reports/copilot-knowledge-site/index.html
```

导出包固定包含 `index.html`、`data/manifest.json`、`data/wiki.json`、`data/graph.json` 和 `wiki/*.md`。`index.html` 提供 LLM Wiki、Knowledge Graph、搜索过滤和节点/边详情面板；它只读取 active curated memory、evidence 和知识图谱视图，不读取全部 raw events，也不写 SQLite / Feishu / Bitable。

详细启动、探活、验收和回滚步骤见 [LLM Wiki / Graph Admin Launch Runbook](docs/productization/admin-llm-wiki-launch-runbook.md)。
当前目标完成度、证据清单和生产缺口见 [LLM Wiki Enterprise Knowledge Site Completion Audit](docs/productization/llm-wiki-enterprise-site-completion-audit.md)。
受控 systemd 模板见 `deploy/copilot-admin.service.example`，env 示例见 `deploy/copilot-admin.env.example`，Nginx 反向代理模板见 `deploy/copilot-admin.nginx.example`，staging Prometheus alert rules 见 `deploy/monitoring/copilot-admin-alerts.yml`；需要先把真实 token 写入本机 `/etc/feishu-memory-copilot/admin.env`，不要提交。

这个后台的知识视图只读；唯一写接口是 admin-only 的 `/api/tenant-policies`，用于本地/pre-production 租户策略配置和审计。它是本机运维/调试入口，不代表生产部署、真实企业 IdP SSO 验收、生产 DB 运维或 productized live。

### 2.6 运行 Demo readiness

```bash
python3 scripts/check_demo_readiness.py
python3 scripts/check_demo_readiness.py --json
```

Demo readiness 用来确认本地演示是否可复现。

---

## 3. 核心演示流程

### 3.1 运行固定 Demo replay

```bash
python3 scripts/demo_seed.py
python3 scripts/demo_seed.py --json-output reports/demo_replay.json
```

这个脚本会演示：

1. 创建带证据的长期记忆。
2. 搜索当前 active memory。
3. 处理冲突更新。
4. 解释版本链。
5. 生成 Agent 任务前上下文包。
6. 生成 heartbeat reminder candidate。

如果真实飞书 live 测试已经在默认库里写入测试 memory、群策略或 audit，可以先生成隔离的干净评委 demo 库：

```bash
python3 scripts/prepare_clean_demo_db.py --source-db data/memory.sqlite --output-db data/demo_clean.sqlite --force --json
python3 scripts/demo_seed.py --db-path data/demo_clean.sqlite --json-output reports/demo_replay.json
```

这个脚本只检查 source DB 的噪声计数并创建新的 demo DB，不删除 live/staging 证据；它不代表生产数据保留或删除策略。

### 3.2 运行 Benchmark

```bash
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_layer_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
```

Benchmark 覆盖：

| 评测方向 | 说明 |
|---|---|
| recall | 能不能在 Top 3 找到正确长期记忆 |
| candidate | 能不能识别该记的内容，不乱记闲聊 |
| conflict | 新旧结论冲突时能不能生成候选版本 |
| layer | L1/L2/L3 分层检索是否符合预期 |
| prefetch | Agent 任务前是否能带入正确上下文 |
| heartbeat | 主动提醒候选是否泄露敏感内容 |

---

## 4. 项目架构

```text
Feishu / OpenClaw
      |
      v
OpenClaw memory.* tools
      |
      v
agent_adapters/openclaw/
      |
      v
memory_engine/copilot/tools.py
      |
      v
CopilotService
      |
      +--> permissions.py       权限门控，默认 fail closed
      +--> governance.py        candidate / confirm / reject / version chain
      +--> orchestrator.py      L0/L1/L2/L3 检索编排
      +--> retrieval.py         keyword + vector + Cognee optional merge/rerank
      +--> heartbeat.py         reminder candidate
      |
      v
MemoryRepository / SQLite
      |
      +--> raw_events
      +--> memories
      +--> memory_versions
      +--> memory_evidence
      +--> memory_audit_events
```

核心原则：

1. **OpenClaw 是主入口。**
   `memory.*` 工具是 Agent 使用记忆的正式接口。

2. **CopilotService 是唯一业务服务层。**
   CLI、Feishu live sandbox、OpenClaw runner 都应该进入同一套 `CopilotService`。

3. **真实飞书来源必须先经过 review policy。**
   低重要性、无冲突、无敏感风险的候选可以自动确认成 active；项目进展重要、重要角色发言、敏感/高风险或冲突内容必须停在 candidate，并优先私聊相关 reviewer / owner 确认。

4. **默认只召回 active memory。**
   candidate、superseded、rejected、raw events 不会默认出现在搜索结果里。

5. **每条长期记忆必须有证据。**
   search / prefetch 返回结果必须带 evidence 和 trace。

6. **权限缺失时拒绝。**
   `current_context.permission` 缺失、畸形、scope 不匹配、tenant/org 不匹配时，全部 fail closed。

---

## 5. 关键目录

```text
agent_adapters/openclaw/
  memory_tools.schema.json       OpenClaw memory 工具契约
  plugin/                        first-class OpenClaw plugin
  examples/                      OpenClaw 工具调用样例

memory_engine/copilot/
  service.py                     Copilot 应用服务层
  tools.py                       OpenClaw 工具桥接入口
  schemas.py                     请求/响应模型
  permissions.py                 权限门控和敏感内容识别
  governance.py                  candidate、confirm、reject、version chain
  orchestrator.py                L0/L1/L2/L3 检索编排
  retrieval.py                   keyword/vector/Cognee 混合检索
  heartbeat.py                   reminder candidate
  feishu_live.py                 飞书测试群 live sandbox
  healthcheck.py                 Copilot 健康检查

memory_engine/
  db.py                          SQLite schema 和 migration
  repository.py                  本地存储访问层
  cli.py                         memory CLI 入口
  document_ingestion.py          文档摄取
  feishu_runtime.py              legacy Feishu runtime fallback
  bitable_sync.py                Bitable dry-run / sync

scripts/
  check_copilot_health.py        Copilot healthcheck
  check_demo_readiness.py        Demo readiness
  demo_seed.py                   固定 Demo replay
  prepare_clean_demo_db.py       隔离生成干净评委 Demo SQLite
  check_openclaw_version.py      OpenClaw 版本检查
  check_live_embedding_gate.py   live embedding gate
  migrate_copilot_storage.py     存储迁移 dry-run / apply
  backup_copilot_storage.py      SQLite staging 备份 / 校验 / 恢复演练
  start_copilot_feishu_live.sh   飞书测试群 sandbox 启动脚本

benchmarks/
  copilot_*.json                 Copilot benchmark cases

docs/
  demo-runbook.md
  benchmark-report.md
  memory-definition-and-architecture-whitepaper.md
  productization/
  plans/
```

---

## 6. OpenClaw 版本

当前锁定版本：

```text
OpenClaw 2026.4.24
```

锁文件：

```text
agent_adapters/openclaw/openclaw-version.lock
```

检查命令：

```bash
python3 scripts/check_openclaw_version.py
```

除非明确要升级并重新锁定版本，不要运行：

```bash
openclaw update
npm update -g openclaw
npm install -g openclaw@latest
```

---

## 7. Feishu live sandbox

新的飞书测试群入口是：

```bash
python3 -m memory_engine copilot-feishu listen
```

该命令会同时启动本地只读 dashboard，默认地址是 `http://127.0.0.1:8765`。如需关闭：

```bash
python3 -m memory_engine copilot-feishu listen --no-admin
```

或：

```bash
scripts/start_copilot_feishu_live.sh
```

支持的飞书消息示例：

```text
/help
/health
/search 生产部署 region 是什么？
/remember 规则：生产部署必须加 --canary
/confirm <candidate_id>
/reject <candidate_id>
/versions <memory_id>
/prefetch 今天上线前检查清单
/heartbeat
```

边界说明：

- 这是受控测试群 sandbox。
- 不是生产部署。
- 不是全量飞书 workspace ingestion。
- 真实飞书消息默认先进入 review policy：低重要性安全内容可自动 active，重要/敏感/冲突内容仍需人工确认。
- reviewer 配置不能默认使用 `*`，真实 ID 不写入仓库。

---

## 8. 答辩和提交材料

答辩优先看四份材料：`docs/judge-10-minute-experience.md`、`docs/demo-runbook.md`、`docs/benchmark-report.md`、`docs/memory-definition-and-architecture-whitepaper.md`。

如果要核对完成度和边界，再看 `docs/productization/prd-completion-audit-and-gap-tasks.md`、`docs/productization/workspace-ingestion-goal-completion-audit-2026-05-04.md` 和 `docs/productization/full-copilot-next-execution-doc.md`。更细的运行证据放在 `docs/productization/handoffs/`。

答辩时可以用这句话概括：

> 我们做的不是一个会记笔记的 Bot，而是一个 OpenClaw-native 的企业记忆治理层。它把飞书里的长期有效信息转成候选记忆，通过权限门控、证据链、版本链和审计表治理后，再以 `memory.*` 工具的形式提供给 OpenClaw Agent 使用。

---

## 9. 当前主线任务

当前优先级最高的后续任务：

| 任务 | 位置 | 完成标准 |
|---|---|---|
| 继续推进 productized live gate | `docs/productization/productized-live-long-run-plan.md` | 已完成本地 tenant policy editor；下一步在 L1 internal pilot、PostgreSQL pilot、真实企业 IdP SSO 验收、审计 read-only view 中选一项实施并验证 |
| 保持 no-overclaim 文档口径 | README、白皮书、Demo runbook、Benchmark report | 不把 demo、dry-run、sandbox、staging 写成 production live |

---

## 10. 开发验证命令

文档改动：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
git diff --check
```

Python / Copilot 代码改动：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
git diff --check
python3 -m compileall memory_engine scripts
```

Copilot 核心专项：

```bash
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools
python3 -m unittest tests.test_copilot_permissions tests.test_copilot_governance
python3 -m unittest tests.test_copilot_retrieval tests.test_copilot_benchmark
```

Demo / healthcheck：

```bash
python3 scripts/check_copilot_health.py --json
python3 scripts/check_demo_readiness.py --json
```

Cognee 相关验证按任务选择，不要默认全跑：

```bash
python3 scripts/check_cognee_curated_sync_gate.py --json
python3 scripts/check_cognee_embedding_sampler_status.py --embedding-sample-log <samples.ndjson> --pid-file <sampler.pid> --json
python3 scripts/collect_cognee_embedding_long_run_evidence.py --help
```

Benchmark：

```bash
for f in benchmarks/copilot_*.json; do python3 -m memory_engine benchmark run "$f"; done
```

---

## 11. 项目边界

本项目当前是比赛项目和产品化原型，不是完整生产系统。已经证明的是本地可复现、Demo 可演示、Benchmark 可运行、OpenClaw tool contract 可检查、飞书测试群 sandbox 可联调，以及权限、证据、版本、审计的本地闭环。

尚未完成的是生产部署、全量飞书 workspace ingestion、完整多租户企业后台、真实企业权限后台、生产级长期 embedding 服务、生产级监控告警自动回滚，以及真实 Feishu DM 长期稳定路由。详细边界以上方“不能 overclaim”和 `docs/productization/agent-execution-contract.md` 为准。
