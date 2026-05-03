# 完整可用 Copilot 后续执行文档

日期：2026-04-28  
当前目标：从“初赛 MVP 已完成”升级为“做出完整、可用、可治理、可审计的 Feishu Memory Copilot”。  
适用方式：可以直接复制整份文档给下一轮 Codex / OpenClaw / 执行 agent 使用。

## 一句话目标

我们现在不再满足于“初赛完成 MVP”。接下来要把 Feishu Memory Copilot 做成一个完整可用的产品：OpenClaw Agent 能在真实任务中调用企业记忆，飞书里能完成受控搜索、候选确认、版本解释、任务前上下文预取和提醒候选审核，Copilot Core 有权限、证据、状态机、审计和健康检查闭环。

## 先看这个

1. 今天的真实日期是 2026-04-28；仓库中已有未来日期计划和 handoff，但本轮以当前仓库代码和最新文档为事实源。
2. 2026-05-05 及以前的 implementation plan 已经全部完成，不再需要执行；它们只保留为历史计划、验收证据和风险参考。
3. 初赛 MVP、Benchmark Report、Demo replay、白皮书、受控飞书测试群 live sandbox 已经成型，不要重复做“证明能跑”的 demo。
4. Phase A 已补齐 storage migration + audit table；Phase B 已补真实 OpenClaw Agent runtime 受控证据；Phase D 已补 live Cognee/Ollama embedding gate；Phase E 已完成 no-overclaim 交付物审查；后期打磨 P0 已补 `memory.*` first-class OpenClaw 原生工具注册本机证据、OpenClaw Feishu websocket running 本机 staging 证据、Agent 本地 `fmc_*` 工具调用验证，以及一次受控真实 Feishu DM -> `fmc_memory_search` -> `CopilotService` allow-path live E2E 证据；后期打磨 P1 已补生产存储、索引和迁移方案的本地入口；后期打磨 P0 已补真实飞书权限映射本地闭环；后期打磨 P1 已补 limited Feishu ingestion 本地底座；2026-04-29 已补审计查询、告警和运维 healthcheck 面、productized live 长期运行方案、真实飞书可点击卡片的受控 sandbox/pre-production 路径，以及 Feishu 群/用户/消息作为企业图谱拓扑的本地发现能力；2026-04-30 已补 OpenClaw gateway 本地不 @ 静默候选筛选入口、审核卡片 publisher 层 DM/private 定向投递、以及只读群级设置卡片；2026-05-01 已补任意群 onboarding 的本地/pre-production 群策略：新群默认 pending_onboarding，不记录消息内容，reviewer/admin 显式 `/enable_memory` 后才允许当前群静默候选筛选，并可在 Admin Groups 视图查看策略状态；OpenClaw gateway 本地路由也已补 `/settings`、`/enable_memory`、`/disable_memory`，gateway 抢到群设置事件时不再必然回落旧 agent 路径。2026-05-02 已补九项 productization completion audit gate 和受控 Feishu live evidence packet；2026-05-03 结合 Cognee 24h+ 本地/staging 长跑 evidence 复核，completion audit 返回 `goal_complete=true`。当前最大的后续产品化缺口是：继续扩大真实 Feishu 样本、真实卡片点击和真实 DM 投递实测，以及选择一个长期运行 gate 做受控实施。
5. 所有真实飞书数据仍先进入 `memory.create_candidate` 和 review policy；低重要性、无冲突、无敏感风险内容可以自动确认成 active，项目进展重要、重要角色发言、敏感/高风险或冲突内容必须停在 candidate；confirm/reject/undo 必须走 `CopilotService` / `handle_tool_request()`。
6. 不要把 demo replay、dry-run、测试群 sandbox 写成 production live、全量 Feishu workspace ingestion 或完整多租户后台。

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

如果这些文件与当前代码冲突，以当前代码和本执行文档的产品化目标为准；2026-05-05 及以前日期计划和旧 Day1-Day7 文档只作 reference，不要回到 CLI-first / Bot-first 主线。

## 当前事实基线

已经完成：

- Phase A Storage Migration + Audit Table：SQLite schema version `3`；`raw_events`、`memories`、`memory_versions`、`memory_evidence` 有 `tenant_id`、`organization_id`、`visibility_policy` 兼容字段；新增 `memory_audit_events`、`knowledge_graph_nodes`、`knowledge_graph_edges`；confirm/reject/permission deny/limited ingestion candidate/heartbeat candidate 写审计记录；healthcheck `storage_schema.status=pass`、`audit_smoke.status=pass`。
- `memory.search`：active-only、Top K、evidence、L0/L1/L2/L3 trace、hybrid retrieval。
- `memory.create_candidate`：候选识别、低价值内容过滤、evidence gate、risk flags。
- `memory.confirm` / `memory.reject`：通过 Copilot governance 状态机处理。
- `memory.explain_versions`：冲突更新、active/superseded 版本链解释。
- `memory.prefetch`：任务前 compact context pack，不带 raw events。
- `heartbeat.review_due`：只生成 reminder candidate，不真实推送，不自动 active。
- OpenClaw schema：`agent_adapters/openclaw/memory_tools.schema.json`，当前 7 个工具。
- Feishu live sandbox：当前稳定路径是 allowlist 测试群，或本地/pre-production 群策略显式启用的群；新群默认 `pending_onboarding`，只登记最小群节点和群策略，不写 raw_events、不创建 candidate。reviewer/admin 在当前群 `@Bot /enable_memory` 后，该群非 `@Bot` 消息才会先做静默 candidate probe，命中企业级记忆信号时进入 `memory.create_candidate` 和 review policy：低重要性安全候选可自动确认，重要/敏感/冲突候选优先通过 DM/private 定向给相关 reviewer / owner 审核，默认不回群消息；`@Bot` / 私聊仍走主动交互路径。普通问句不会因为命中“部署 / 负责人 / 截止”这类主题词就自动变成 candidate。lark-cli live 路径进入 `memory_engine/copilot/feishu_live.py -> handle_tool_request() -> CopilotService`；OpenClaw gateway 旁路已补 `route_gateway_message()` 本地静默筛选入口和群设置/启停入口，命中企业记忆信号时进入 `handle_tool_request("memory.create_candidate")` / `CopilotService`，`/settings`、`/enable_memory`、`/disable_memory` 则进入同一 `feishu_group_policies` 写入/审计路径。这仍不是真实 gateway 长期稳定路由证明。
- 非 @ 群消息 live 投递：`scripts/check_feishu_passive_message_event_gate.py` 已可检查真实 lark-cli/OpenClaw NDJSON/JSON 事件日志，并可解析 Copilot listener `raw_line` wrapper 和 OpenClaw channel log，区分普通非 @ 群文本已到达、只看到 @Bot 消息、只看到 reaction 事件或目标群不匹配；`scripts/check_feishu_event_subscription_diagnostics.py` 可只读检查 lark-cli event status/list/schema，不启动 listener，用来确认 `im.message.receive_v1` EventKey、required console event、bot auth、lark-cli bus 是否与 planned listener 冲突。2026-05-02 12:08 真实龙虾群普通非 @ 文本已进入 OpenClaw websocket，channel log 出现 `received message ... (group)`、正文和 `dispatching to agent`，gate 对 `/tmp/openclaw-feishu-live-after-group-scope.json` 返回 `ok=true`、`reason=passive_group_message_seen`。这只证明 live 投递进入当前单监听入口，不证明长期生产运行。
- Feishu 单监听 preflight：`scripts/check_feishu_listener_singleton.py` 会在 repo 内 lark-cli listener 启动前拦截 legacy / copilot / direct lark-cli / 可识别 OpenClaw websocket 冲突；只看到泛化 `openclaw-gateway` 进程时，repo 内 lark-cli planned listener 也会 fail closed，只有 `--planned-listener openclaw-websocket` 可继续并必须结合 `channels.status` / gateway log 确认 Feishu channel 是否 active。OpenClaw websocket、Copilot lark-cli sandbox、legacy fallback 三选一。
- Phase B OpenClaw Agent runtime evidence：`openclaw agent --agent main` run `b252f11e-b49d-495c-a14f-0b823a888a5e` 通过 `exec` 调用 `scripts/openclaw_runtime_evidence.py`，三条 Copilot flow 全部 `ok=true`，并保留 request_id、trace_id、permission_decision。
- Phase D live embedding gate：`python3 scripts/check_live_embedding_gate.py --json` 已真实调用 `ollama/qwen3-embedding:0.6b-fp16`，返回 1024 维，并确认清理后无本项目 Ollama 模型驻留；healthcheck 仍保留 configuration-only，不把它写成长期 embedding 服务。
- Cognee 主路径本地闭环：`memory.confirm` 成功后会把 curated memory fields 和 ledger metadata 通过 adapter add -> cognify 同步给 Cognee；`memory.reject` 会走 adapter withdrawal；Cognee 不可用或同步失败时返回 repository fallback；retrieval 已过滤未匹配本地 ledger 的 Cognee result。2026-05-01 已补当前 Cognee SDK 的 metadata-optional / async 调用兼容，并新增 `scripts/check_cognee_curated_sync_gate.py --json` 作为隔离真实 Cognee store gate；该 gate 现在按 `process env > .env.local > .env > defaults` 解析 provider/model，避免误用本地默认 Ollama。当前用 `.env.local` 中的 custom LLM 与 OpenAI-compatible embedding 配置已跑通隔离 store，返回 `cognee_sync.status=pass`、`fallback=null`。2026-05-03 复核 `logs/cognee-embedding-long-run/2026-05-02-sampler/cognee-long-run-evidence.json`，本地/staging sampler status `completion_ready=true`、5 个成功样本、窗口 24.0015h，completion audit item 8 可 pass；这仍不是生产长期 embedding 服务或生产持久化 Cognee store。详见 [Cognee 主路径 handoff](handoffs/cognee-main-path-handoff.md)。
- Demo readiness：`python3 scripts/check_demo_readiness.py --json` 已可通过。
- Benchmark：recall、candidate、conflict、layer、prefetch、heartbeat 六类 runner 已有。
- Phase E no-overclaim 审查：README、Demo runbook、Benchmark Report、白皮书、产品化主控和 handoff 口径已对齐；heartbeat 样例数统一为 7；白皮书已更新 Phase B runtime evidence 和 Phase D live embedding gate 的当前事实；后续又补齐 first-class registry 和 websocket staging 证据；仍不宣称生产部署、全量 Feishu workspace ingestion、长期 embedding 服务、完整多租户后台或 productized live。
- First-class OpenClaw 原生工具注册、本地 Agent 调用验证和受控真实 DM allow-path 证据：`agent_adapters/openclaw/plugin/` 已提供 `feishu-memory-copilot` 插件；OpenClaw-facing 工具名使用 `fmc_*`，再由插件和 `tool_registry.py` 翻译到 Python 侧 `memory.*`；`openclaw plugins inspect feishu-memory-copilot --json` 已读回 7 个 `toolNames`；`scripts/check_feishu_dm_routing.py` 和 `tests/test_feishu_dm_routing.py` 验证了本地 Agent 可见工具、runner envelope、bridge metadata 和 `handle_tool_request()` / `CopilotService` 调用链路；2026-04-29 11:04 受控真实 DM 已完成 `fmc_memory_search` allow-path，11:07 飞书机器人回复读回命中 5 条、`request_id=req_feishu_dm_live_20260429_1104`、`trace_id=trace_feishu_dm_live_20260429_1104`、`permission_decision=allow/scope_access_granted`。这个证据仍不等于稳定长期路由或 productized live。
- First-class routing evidence gate：2026-05-02 `scripts/check_feishu_dm_routing.py` 新增 `--event-log` 模式，可审计真实 Feishu/OpenClaw NDJSON / gateway 日志里是否出现 `fmc_*` bridge tool、request_id、trace_id 和 permission_decision。`logs/feishu-live-evidence-runs/20260502T085247Z/02-first-class-routing.ndjson` 已覆盖 `fmc_memory_search`、`fmc_memory_create_candidate`、`fmc_memory_prefetch`，`missing_required_tools=[]`。该 gate 用来防止把内部 `memory.*` 或失败/deny-path 误写成稳定真实 first-class 路由。
- 九项 productization completion audit gate：2026-05-02 新增 `scripts/check_openclaw_feishu_productization_completion.py --json`，把非 @ 群消息 live 投递、单监听、first-class `fmc_*` routing、第二真实用户权限负例、真实 `/review` DM/card、Dashboard auth、clean demo DB、Cognee/embedding long-run 和 no-overclaim 逐项映射到 artifact 或 live evidence gate。2026-05-03 同时传入 `logs/feishu-live-evidence-runs/20260502T085247Z/feishu-live-evidence-packet.json`、`00-feishu-event-diagnostics.json` 和 `logs/cognee-embedding-long-run/2026-05-02-sampler/cognee-long-run-evidence.json` 后返回 `goal_complete=true`、`blockers=[]`。后续真实扩样可先用 `scripts/prepare_feishu_live_evidence_run.py` 生成单监听 preflight 和日志路径，再用 `scripts/collect_feishu_live_evidence_packet.py` 生成 sanitized packet，并通过 `--feishu-live-evidence-packet` 输入 completion audit；该 packet 仍要求每个底层 gate 的 exact pass reason。
- OpenClaw Feishu websocket running 本机 staging 证据：`python3 scripts/check_openclaw_feishu_websocket.py --json --timeout 45` 返回 `ok=true`、`pass=4`、`warning=1`、`fail=0`；`channels_status.channel_running=true`、`account_running=true`、`probe_ok=true`；gateway 日志证明真实 DM 已进入 OpenClaw Agent dispatch；同一时间没有 repo 内 lark-cli listener 冲突。
- 跨平台快速部署入口：`docs/productization/cross-platform-quick-deploy.md` 已给出 macOS / Linux / Windows 三套 demo/pre-production 快速部署步骤；`scripts/check_cross_platform_quick_deploy.py` 提供 `local-demo`、`openclaw-staging`、`embedding` 三个 preflight profile，统一检查 Python、Git、pip/venv、OpenClaw 锁定版本、Node/npm 和可选 Ollama 条件。本机 2026-05-03 运行三个 profile 均 `ok=true`，但 Python 为 3.9.6，因此保留“推荐 Python 3.11+” warning；这只证明新机器快速部署/预检路径，不代表生产部署或 productized live。
- 生产存储、索引和迁移方案：`memory_engine/storage_migration.py` 和 `scripts/migrate_copilot_storage.py` 已提供 dry-run / apply 入口；healthcheck `storage_schema` 已报告 schema version、index status、audit status；文档已写清本地 SQLite 与托管 PostgreSQL 上线试点边界、备份恢复、审计保留和数据删除策略。这不是生产 DB 部署或完整多租户后台。
- 真实飞书权限映射：`memory_engine/copilot/feishu_live.py` 会把真实飞书 sender、chat、tenant、organization、visibility 映射到 `current_context.permission`；`permissions.py` 按目标上下文判断 tenant/org/source context；真实飞书 candidate 会把 tenant/org/visibility 写入本地 ledger。详见 [真实飞书权限映射 handoff](handoffs/real-feishu-permission-mapping-handoff.md)。
- 真实飞书权限负例 gate：2026-05-01 新增 `scripts/check_feishu_permission_negative_gate.py --json`，用于检查第二个非 reviewer 真实用户 `@Bot /enable_memory` 的 live denial result；它要求看到 `copilot.group_enable_memory` 的 `permission_denied` result，单独的 `feishu_group_policy_denied` audit 不算通过。gate 现在可解析 Copilot listener `raw_line` attempt wrapper；available isolated logs 重跑只看到 reviewer/admin allow-path，仍没有第二真实用户 denial result。当前只是可执行 evidence gate；未导入真实第二用户日志前，不能宣称 live 权限负例已完成。
- Limited Feishu ingestion 与真实 API 拉取入口：`memory_engine/document_ingestion.py` 支持 `feishu_message`、`document_feishu` / `lark_doc`、`feishu_task`、`feishu_meeting`、`lark_bitable` 来源文本进入受控记忆流程；但对 `feishu_message` 来说，当前不是被动全量群聊摄入，而是消息先在 `feishu_live.py` 里通过 allowlist 或已启用群策略、是否 `@Bot`、主动交互/静默探测路由和问句过滤判断，再进入 `memory.create_candidate` 和 review policy。低重要性安全候选可自动确认；重要/敏感/冲突候选仍需人工确认。`memory_engine/feishu_task_fetcher.py`、`memory_engine/feishu_meeting_fetcher.py`、`memory_engine/feishu_bitable_fetcher.py` 已提供任务、妙记、Bitable 记录读取入口；`feishu.fetch_task` / `feishu.fetch_meeting` / `feishu.fetch_bitable` 在真实 fetch 前会做 permission 和 source_context fail-closed preflight；Feishu live `/task`、`/meeting`、`/bitable` 会把 source id 写入 `permission.source_context`。详见 [limited Feishu ingestion handoff](handoffs/limited-feishu-ingestion-handoff.md) 和 [Feishu API pull handoff](handoffs/feishu-api-pull-handoff.md)。这不是全量 Feishu workspace ingestion，也不是生产长期运行。
- 审计查询、告警和运维 healthcheck：`scripts/query_audit_events.py` 支持审计查询/导出/summary；`scripts/check_audit_alerts.py` 支持连续 deny、deny rate、显式 `ingestion_failed` 和 audit gap；`memory_engine/document_ingestion.py` 对 permission/source mismatch、Feishu fetch 失败、候选为空写脱敏 `ingestion_failed`；healthcheck 新增默认 skipped 的 `openclaw_websocket` 运维入口和 embedding fallback 可观测字段；search runtime fallback 会写 `embedding_unavailable` ops audit。详见 [audit ops observability handoff](handoffs/audit-ops-observability-handoff.md)。这不是生产级 Prometheus/Grafana，也不是 productized live。
- Productized live 长期运行方案：已新增 [productized-live-long-run-plan.md](productized-live-long-run-plan.md) 和 [productized-live handoff](handoffs/productized-live-long-run-plan-handoff.md)，写清 L0/L1/L2/L3 gate、部署拓扑、单监听、PostgreSQL ledger、监控告警、权限后台、审计 UI、回滚停写和草案文档使用边界。现有 `deployment-runbook.md`、`productized-live-architecture.md`、`monitoring-design.md`、`permission-admin-design.md`、`audit-ui-design.md`、`ops-runbook.md` 均已校准为方案草案，不作为已验证上线 runbook。这不是 productized live 已完成。
- Review surface 可操作写回：Feishu card action 的 confirm / reject 已通过 `handle_tool_request()` / `CopilotService`，Bitable Candidate Review / Reminder Candidate 写回已补稳定 `sync_key`、upsert、失败重试和读回确认。详见 [review surface operability handoff](handoffs/review-surface-operability-handoff.md)。这不是生产级 card action 长期运行。
- 真实飞书可点击卡片受控路径：Feishu live `card_mode=interactive` 不再只把回复文本包成通用卡片，而是按 `memory.search`、`memory.create_candidate`、`memory.explain_versions`、`memory.prefetch` 选择 typed card builder；候选审核卡的确认、拒绝、要求补证据、标记过期会从卡片点击回到当前 operator 权限上下文，再进入 `handle_tool_request()` / `CopilotService`。详见 [真实飞书互动卡片 handoff](handoffs/real-feishu-interactive-cards-handoff.md)。这不是生产级 card action 长期运行。
- 审核收件箱、冲突合并、DM 投递和撤销入口：Feishu live 已新增 `/review` 只读审核收件箱，默认显示“待我审核”，并支持 `/review conflicts`、`/review high_risk`；收件箱卡片可定向 `open_ids`，可见内容不展示内部 ID；publisher 遇到定向卡片时逐个 `open_id/user_id` 发送 DM interactive card，失败 fallback 也只走 DM 文本，timeout ambiguity 不回群；冲突候选卡显示旧结论/新结论并提供“确认合并”，仍走 `memory.confirm`；`/undo` 与 OpenClaw card action router 已可撤销 confirm/reject/needs_evidence/expire 后的状态变更；2026-05-02 受控 live packet 让 `scripts/check_feishu_review_delivery_gate.py --event-log` 同时看到 candidate review card、private review DM、review inbox result 和 card action `update_card` result。当前是本地受控 sandbox/pre-production 路径，不是生产级长期运行或稳定真实 DM 路由。
- 群级设置和启停：Feishu live 已新增 `/settings` / `/group_settings` 入口，展示 allowlist、当前群策略、审核投递、auto-confirm policy、scope/visibility 和生产边界；`/enable_memory` / `/disable_memory` 需要 reviewer/admin 授权后写入本地 `feishu_group_policies` 并记录 audit。新群默认 `pending_onboarding`，不记录消息内容；本入口仍不是生产级企业后台配置。
- Feishu 群/用户/消息图谱拓扑：Feishu live 入口会在 allowlist 判断前把群登记为同 tenant/org 下的 `feishu_chat` 节点，并建立 organization -> chat 边；未在 allowlist 的新群只登记 org/chat 最小元数据，不写 raw_events、不创建 candidate、不回复消息，也不创建用户/消息节点。allowlist 通过且消息可处理后，会登记 tenant/org 内唯一 `feishu_user` 节点、`feishu_message` 事件节点，以及 user -> chat、user -> message、chat -> message 关系边；消息正文不写入图谱节点，仍只通过 raw_events/candidate/evidence 受控保存。详见 [Feishu 群图谱节点 handoff](handoffs/feishu-group-graph-node-handoff.md)。这不是全量 workspace ingestion，也不是生产级长期图谱服务。

仍未完成：

- Feishu Agent live DM routing：本地 Agent 到 `fmc_*` 插件工具、再到 Python 侧 `memory.*` / `CopilotService` 的调用验证已补；2026-04-29 已补一次受控真实 DM `fmc_memory_search` allow-path live E2E 和飞书回复读回证据；2026-04-30 已补 OpenClaw gateway 本地静默候选筛选入口。后续仍要扩大到真实 gateway/live 下的 `prefetch` / `create_candidate` 等关键动作、读回 DM 定向卡片投递，并验证长期稳定性；不能把单次或本地证据写成稳定长期路由。
- 真实 Feishu 样本实测扩样：任务、会议、Bitable 读取入口和 review-policy 路径已补；后续仍可用受控真实资源 ID 继续扩样，但不能冒称全量 workspace ingestion 或生产 live。
- 用户体验产品化：7 个 UX 缺口已单独进入 [用户体验产品化 TODO 清单](user-experience-todo.md)，包括飞书主路径、记忆卡片、解释层、审核队列、可控提醒、真实表达样本和 10 分钟评委体验包；当前已完成受控 UX 路径，但仍不能写成 production live、全量 workspace 接入或长期稳定线上运行。
- OpenClaw health running 字段一致性：OpenClaw 2026.4.24 的 `openclaw health --json` 总览仍把 Feishu running 报为 `false`，但 `openclaw channels status --probe --json` 和 gateway 日志显示 running；当前作为 warning 记录。
- productized live：长期运行方案已完成，本地/pre-production LLM Wiki / Graph Admin 已有 admin-only tenant policy editor；但没有生产 DB 部署、生产级 Prometheus/Grafana 长期监控、真实企业目录/IdP/RBAC 接入，也没有长期线上运行证据。

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
