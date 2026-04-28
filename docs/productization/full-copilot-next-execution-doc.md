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
4. Phase A 已补齐 storage migration + audit table；Phase B 已补真实 OpenClaw Agent runtime 受控证据；Phase D 已补 live Cognee/Ollama embedding gate；Phase E 已完成 no-overclaim 交付物审查；后期打磨 P0 已补 `memory.*` first-class OpenClaw 原生工具注册本机证据、OpenClaw Feishu websocket running 本机 staging 证据和首批真实飞书权限映射。当前最大的后续产品化缺口是：真实 Feishu DM 到本项目 first-class `memory.*` 工具路由、完整企业权限后台和 productized live。
5. 所有真实飞书数据仍先进入 candidate（待确认记忆），不能自动 active；confirm/reject 必须走 `CopilotService` / `handle_tool_request()`。
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

- Phase A Storage Migration + Audit Table：SQLite schema version `2`；`raw_events`、`memories`、`memory_versions`、`memory_evidence` 有 `tenant_id`、`organization_id`、`visibility_policy` 兼容字段；新增 `memory_audit_events`；confirm/reject/permission deny/limited ingestion candidate/heartbeat candidate 写审计记录；healthcheck `storage_schema.status=pass`、`audit_smoke.status=pass`。
- `memory.search`：active-only、Top K、evidence、L0/L1/L2/L3 trace、hybrid retrieval。
- `memory.create_candidate`：候选识别、低价值内容过滤、evidence gate、risk flags。
- `memory.confirm` / `memory.reject`：通过 Copilot governance 状态机处理。
- `memory.explain_versions`：冲突更新、active/superseded 版本链解释。
- `memory.prefetch`：任务前 compact context pack，不带 raw events。
- `heartbeat.review_due`：只生成 reminder candidate，不真实推送，不自动 active。
- OpenClaw schema：`agent_adapters/openclaw/memory_tools.schema.json`，当前 7 个工具。
- Feishu live sandbox：真实测试群消息进入 `memory_engine/copilot/feishu_live.py -> handle_tool_request() -> CopilotService`。
- Feishu 单监听 preflight：`scripts/check_feishu_listener_singleton.py` 会在 repo 内 lark-cli listener 启动前拦截 legacy / copilot / direct lark-cli / 可识别 OpenClaw websocket 冲突；OpenClaw websocket、Copilot lark-cli sandbox、legacy fallback 三选一。
- Phase B OpenClaw Agent runtime evidence：`openclaw agent --agent main` run `b252f11e-b49d-495c-a14f-0b823a888a5e` 通过 `exec` 调用 `scripts/openclaw_runtime_evidence.py`，三条 Copilot flow 全部 `ok=true`，并保留 request_id、trace_id、permission_decision。
- Phase D live embedding gate：`python3 scripts/check_live_embedding_gate.py --json` 已真实调用 `ollama/qwen3-embedding:0.6b-fp16`，返回 1024 维，并确认清理后无本项目 Ollama 模型驻留；healthcheck 仍保留 configuration-only，不把它写成长期 embedding 服务。
- Demo readiness：`python3 scripts/check_demo_readiness.py --json` 已可通过。
- Benchmark：recall、candidate、conflict、layer、prefetch、heartbeat 六类 runner 已有。
- Phase E no-overclaim 审查：README、Demo runbook、Benchmark Report、白皮书、产品化主控和 handoff 口径已对齐；heartbeat 样例数统一为 7；白皮书已更新 Phase B runtime evidence 和 Phase D live embedding gate 的当前事实；后续又补齐 first-class registry 和 websocket staging 证据；仍不宣称生产部署、全量 Feishu workspace ingestion、长期 embedding 服务、完整多租户后台或 productized live。
- First-class OpenClaw 原生工具注册：`agent_adapters/openclaw/plugin/` 已提供 `feishu-memory-copilot` 插件；`openclaw plugins inspect feishu-memory-copilot --json` 已读回 7 个 `toolNames`；插件调用 `memory_engine.copilot.openclaw_tool_runner` 后进入 `handle_tool_request()` / `CopilotService`。
- OpenClaw Feishu websocket running 本机 staging 证据：`python3 scripts/check_openclaw_feishu_websocket.py --json --timeout 45` 返回 `ok=true`、`pass=4`、`warning=1`、`fail=0`；`channels_status.channel_running=true`、`account_running=true`、`probe_ok=true`；gateway 日志证明真实 DM 已进入 OpenClaw Agent dispatch；同一时间没有 repo 内 lark-cli listener 冲突。
- 首批真实飞书权限映射：`memory_engine/copilot/feishu_live.py` 可按 sender open_id 映射 tenant / organization；`memory_engine/copilot/permissions.py` 会接受项目配置里的真实 Feishu tenant / org，并对 chat / document source_context mismatch fail closed；`memory_engine/copilot/retrieval.py` 会按 memory 行的 tenant / organization / visibility / source context 过滤；拒绝响应不展示 `current_value`、`summary`、`evidence`。这不是完整企业权限后台，也没有接真实文档 ACL 或长期权限缓存。

仍未完成：

- Feishu Agent tool routing：真实 Feishu DM 当前触发的是 OpenClaw 内置 `memory_search`，还不是本项目 first-class `memory.search` runner；后续要让真实飞书消息稳定进入 `handle_tool_request()` / `CopilotService`。
- 完整企业权限后台：首批本机 staging 映射已完成；真实通讯录 / 组织架构解析、文档 ACL、群聊成员权限和长期权限缓存仍未完成。
- OpenClaw health running 字段一致性：OpenClaw 2026.4.24 的 `openclaw health --json` 总览仍把 Feishu running 报为 `false`，但 `openclaw channels status --probe --json` 和 gateway 日志显示 running；当前作为 warning 记录。
- productized live：没有生产部署、长期运行监控、完整多租户后台。

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
- 真实飞书来源只进 candidate，不自动 active。
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
2. 已完成：真实 runtime 验收前先运行 `python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket`，确认没有 legacy `memory_engine feishu listen`、repo 内 `copilot-feishu listen` 或直接 `lark-cli event +subscribe` 同时消费同一个 bot。
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
- 已完成：验收记录能证明同一时间没有 repo 内 lark-cli listener 冲突；如果后续 OpenClaw websocket owns the bot，仍不得同时运行 lark-cli event listener。

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
6. 所有真实飞书来源仍 candidate-only，不自动 active。

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

状态：已完成，详见 [Phase E handoff](phase-e-no-overclaim-handoff.md)。后续已完成 `memory.*` first-class OpenClaw 原生工具注册本机证据和 OpenClaw Feishu websocket running 本机 staging 证据；下一步只有在明确继续产品化时，才推进真实权限映射、Feishu Agent tool routing 和 productized live。

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
- 已完成：不把 candidate-only 写成自动 active。

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
4. 若做 productized live 方案，先写部署、监控、回滚、权限后台、审计 UI 和运维边界，不要直接写成已经上线。

必须遵守：
- Copilot Core 是事实源，所有入口必须走 CopilotService / handle_tool_request。
- 真实飞书来源只进入 candidate，不能自动 active。
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
