# 后期打磨和上线前待办清单

日期：2026-04-28
阶段：产品后期打磨和上线前优化
负责人：程俊豪；当前实现和文档主要由 Codex 完成

## 先看这个

1. 当前项目已经完成 demo / pre-production 闭环：本地 healthcheck、demo replay、benchmark、受控飞书测试群 sandbox、OpenClaw Agent runtime 受控证据、live embedding gate 和 no-overclaim 审查都已有。
2. 接下来不是继续补旧 MVP，而是把系统打磨到可上线试点：OpenClaw 原生工具、飞书 websocket、真实权限、生产存储、审计和运维。
3. 每个任务必须保持 candidate-only、permission fail-closed、CopilotService 事实源和 no-overclaim 边界。
4. 完成一个任务后，要同步 README 顶部任务区、相关 handoff、飞书共享任务看板，并提交推送。

## 当前完成基线

可以视为已完成的基线：

- `memory.search`、`memory.create_candidate`、`memory.confirm`、`memory.reject`、`memory.explain_versions`、`memory.prefetch`、`heartbeat.review_due` 的 Copilot Core 和 OpenClaw schema 已有。
- `handle_tool_request()` 会统一进入 `CopilotService`，并返回 request / trace / permission metadata。
- Storage migration + audit table 已完成本地 SQLite 闭环。
- 受控 OpenClaw Agent runtime evidence 已完成，但路径仍是 Agent -> `exec` -> evidence script -> Copilot tools。
- Feishu 测试群 live sandbox 已接入新 Copilot path，但不是生产 live。
- Phase D live embedding gate 已证明本机 Ollama provider 可返回 1024 维，但不是长期 embedding 服务。

## 后续任务顺序

### 1. P0：评估并实现 `memory.*` first-class OpenClaw 原生工具注册（已完成本机 registry 证据）

要做什么：让 `memory.search`、`memory.create_candidate`、`memory.confirm`、`memory.reject`、`memory.explain_versions`、`memory.prefetch`、`heartbeat.review_due` 出现在 OpenClaw Agent 原生工具列表，而不是只通过 `exec` 跑仓库证据脚本。

为什么先做：这是产品形态从“OpenClaw 可以间接调用”升级为“Agent 可以自然选择记忆工具”的关键一步。

主要位置：

- `agent_adapters/openclaw/`
- `agent_adapters/openclaw/memory_tools.schema.json`
- `memory_engine/copilot/tools.py`
- `docs/productization/openclaw-runtime-evidence.md`
- `docs/productization/full-copilot-next-execution-doc.md`

完成标准：

- OpenClaw 本机插件清单能看到 `memory.*` 和 `heartbeat.review_due`。
- Agent 可通过 first-class plugin tool 调用 Python runner，再进入 `handle_tool_request()` / `CopilotService`，不再只要求它先用 `exec` 执行证据脚本。
- 每次 tool call 都保留 `request_id`、`trace_id`、`permission_decision`。
- missing / malformed permission 仍 fail closed。
- 文档明确：first-class tool registry 不等于 Feishu production live。

已完成证据：

- 新增 `agent_adapters/openclaw/plugin/`、`agent_adapters/openclaw/tool_registry.py`、`memory_engine/copilot/openclaw_tool_runner.py` 和 `tests/test_openclaw_tool_registry.py`。
- `openclaw plugins install --link --dangerously-force-unsafe-install ./agent_adapters/openclaw/plugin` 通过。因为插件需要用 Node `child_process` 调 Python runner，所以安装时需要 unsafe install override。
- `openclaw plugins enable feishu-memory-copilot` 通过。
- `openclaw plugins inspect feishu-memory-copilot --json` 读回 `toolNames=["memory.search","memory.create_candidate","memory.confirm","memory.reject","memory.explain_versions","memory.prefetch","heartbeat.review_due"]`。

建议验证：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_demo_readiness.py --json
python3 scripts/check_copilot_health.py --json
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools tests.test_openclaw_runtime_evidence
git diff --check
ollama ps
```

### 2. P0：补 OpenClaw Feishu websocket running 证据（已完成本机 staging 证据）

要做什么：让 OpenClaw Feishu websocket 单独接管 `Feishu Memory Engine bot`，并证明没有 lark-cli sandbox 或 legacy listener 同时消费同一个 bot。

为什么要做：上线前必须证明真实飞书消息能走 OpenClaw Agent runtime，并且同一个 bot 没有被 lark-cli sandbox 或 legacy listener 同时消费。

主要位置：

- `docs/productization/feishu-staging-runbook.md`
- `docs/productization/openclaw-runtime-evidence.md`
- `scripts/check_feishu_listener_singleton.py`
- `memory_engine/feishu_listener_guard.py`

完成标准：

- `python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket` 通过。
- `openclaw channels status --probe --json` 显示 Feishu channel 和 default account `running=true`。
- gateway 日志能看到 websocket start、真实 inbound message、dispatching to agent、dispatch complete。
- 真实测试消息进入 OpenClaw Agent；如果 Agent 没有自然调用本项目 first-class `memory.*` 工具，要记录为后续 routing 风险。
- 同一时间没有 `copilot-feishu listen`、legacy `feishu listen` 或 direct `lark-cli event +subscribe` 冲突。
- 真实 chat_id、open_id、token 不写入仓库。

已完成证据：

- 新增 `scripts/check_openclaw_feishu_websocket.py`，聚合单监听检查、`openclaw channels status --probe --json`、`openclaw health --json --timeout 5000` 和 Feishu channel 日志，输出脱敏后的 staging 证据。
- 新增 `tests/test_openclaw_feishu_websocket_evidence.py`，覆盖 `channels.status` running、`health` running 字段不一致时的 warning、以及飞书 ID 脱敏。
- `python3 scripts/check_openclaw_feishu_websocket.py --json --timeout 45` 返回 `ok=true`，`pass=4`，`warning=1`，`fail=0`；`channels_status.channel_running=true`、`account_running=true`、`probe_ok=true`。
- 真实 DM 进入 OpenClaw Feishu session，gateway 日志显示 `received message`、`dispatching to agent`、`dispatch complete`。
- 边界：OpenClaw 2026.4.24 的 `openclaw health --json` 总览仍把 Feishu running 报为 `false`，本阶段以 `channels.status` 和 gateway 日志作为 running 证据，并把不一致写为 warning。
- 边界：真实 DM 当前触发的是 OpenClaw 内置 `memory_search`，不是本项目 first-class `memory.search` runner；后续另开 Feishu Agent tool routing 任务。

建议验证：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
python3 scripts/check_openclaw_feishu_websocket.py --json --timeout 45
python3 -m unittest tests.test_openclaw_feishu_websocket_evidence tests.test_feishu_listener_guard
git diff --check
ollama ps
```

### 3. P0：把 demo 权限模型升级为真实飞书权限映射（已完成首批本机 staging 映射）

要做什么：把当前 `tenant:demo` / `org:demo` 常量式权限检查，升级为从飞书用户、群聊、文档、组织和角色解析出的真实 permission context。

为什么要做：上线前最重要的风险不是召回不准，而是越权召回和证据泄露。

主要位置：

- `memory_engine/copilot/permissions.py`
- `memory_engine/copilot/schemas.py`
- `memory_engine/copilot/service.py`
- `memory_engine/copilot/feishu_live.py`
- `docs/productization/contracts/permission-contract.md`
- `docs/productization/contracts/negative-permission-test-plan.md`

完成标准：

- 已完成首批：permission context 能按飞书 sender open_id 映射真实 actor、tenant、organization，并带上 chat source_context。
- 已完成首批：tenant mismatch、organization mismatch、private non-owner、chat / document source context mismatch 会 fail closed。
- 已完成首批：deny response 不返回 `current_value`、`summary`、`evidence` 明文。
- 已完成首批：confirm / reject 仍要求 reviewer / owner / admin。
- 已完成首批：真实 Feishu doc fetch 前必须先通过 permission gate；document source context mismatch 已在现有 ingestion 测试里覆盖。
- 后续仍未完成：飞书通讯录 / 组织架构 API 自动解析、真实文档 ACL、群聊成员权限和长期权限缓存。

已完成证据：

- 新增 [真实飞书权限映射 handoff](real-feishu-permission-mapping-handoff.md)。
- `memory_engine/copilot/feishu_live.py` 支持 `COPILOT_FEISHU_ACTOR_TENANT_MAP` 和 `COPILOT_FEISHU_ACTOR_ORGANIZATION_MAP`。
- `memory_engine/copilot/permissions.py` 接受项目配置里的真实 Feishu tenant / organization，并继续拒绝未配置的 tenant / organization。
- `memory_engine/copilot/retrieval.py` 会按 memory 行上的 tenant / organization / visibility / source context 做搜索过滤，真实 actor 不会因为通过入口校验就读到其他租户记录。
- `tests/test_copilot_permissions.py` 覆盖真实 Feishu tenant/org allow、chat source_context mismatch deny。
- `tests/test_copilot_feishu_live.py` 覆盖 sender open_id 到 tenant/org 的映射。

建议验证：

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_permissions tests.test_document_ingestion tests.test_copilot_tools
git diff --check
ollama ps
```

### 4. P1：生产存储、索引和迁移方案

要做什么：从本地 SQLite 产品化迁移，推进到可上线试点的生产存储设计和迁移流程。

为什么要做：当前 schema 和 audit table 已经有，但仍是本地 SQLite；可上线产品需要备份、恢复、索引、迁移、数据清理和长期运行方案。

主要位置：

- `memory_engine/db.py`
- `memory_engine/repository.py`
- `memory_engine/copilot/healthcheck.py`
- `docs/productization/contracts/storage-contract.md`
- `docs/productization/contracts/migration-rfc.md`
- 新增后续 storage handoff

完成标准：

- 明确生产 DB 选择和本地 SQLite 的边界。
- migration 支持 dry-run、rollback、重复执行安全。
- 全文索引、结构化索引、向量索引职责清楚。
- audit retention、备份恢复、数据删除策略写入文档。
- healthcheck 能报告 schema version、index status、audit status。

建议验证：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_copilot_health.py --json
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_healthcheck tests.test_copilot_permissions
git diff --check
ollama ps
```

### 5. P1：扩大真实 Feishu ingestion 范围

要做什么：把受控测试群和指定文档的 candidate-only 能力，扩展到更多真实飞书来源：群聊、文档、任务、会议、Bitable。

为什么要做：产品价值来自办公上下文，不只是一个测试群里的 `/remember`。

主要位置：

- `memory_engine/copilot/feishu_live.py`
- `memory_engine/document_ingestion.py`
- `memory_engine/bitable_sync.py`
- `memory_engine/feishu_cards.py`
- `docs/productization/feishu-staging-runbook.md`
- `docs/reference/local-lark-cli-setup.md`

完成标准：

- 每类来源都有 source metadata、evidence quote、去重策略和权限 gate。
- 所有真实来源只进入 candidate，不自动 active。
- source 删除或权限撤销后，recall 降级、隐藏或标记 stale。
- lark-cli / OpenAPI 失败时有明确 fallback，不冒称 live 成功。
- 增加真实测试群消息样本的人工复核集。

建议验证：

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_document_ingestion tests.test_copilot_feishu_live tests.test_bitable_sync tests.test_feishu_interactive_cards
git diff --check
ollama ps
```

### 6. P1：让 Cognee 真正进入主路径

要做什么：把 Cognee 从可用 adapter / live gate，推进为可控、可回退、可观测的 memory substrate。

为什么要做：PRD 架构里 Cognee 是 Knowledge Engine；目前 benchmark 主证据仍是 Copilot Core + repository fallback。

主要位置：

- `memory_engine/copilot/cognee_adapter.py`
- `memory_engine/copilot/retrieval.py`
- `memory_engine/copilot/embedding-provider.lock`
- `scripts/check_live_embedding_gate.py`
- `scripts/spike_cognee_local.py`

完成标准：

- dataset 命名、add/cognify/search、增量更新、删除和撤权同步有固定流程。
- Cognee result 必须能匹配本地 ledger；未匹配结果不能进入正式 answer。
- Cognee 不可用时 repository fallback 清楚可见。
- live embedding gate 和 healthcheck 的边界清楚：配置检查、真实 provider 检查、长期服务三者不混用。

建议验证：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_live_embedding_gate.py --json
python3 scripts/check_embedding_provider.py
python3 scripts/spike_cognee_local.py --dry-run
python3 -m unittest tests.test_copilot_cognee_adapter tests.test_copilot_retrieval
git diff --check
ollama ps
```

运行真实 embedding 验证后必须确认无本项目模型驻留；如有则只停止本项目模型：

```bash
ollama stop qwen3-embedding:0.6b-fp16
```

### 7. P1：把 review surface 接成真实可操作界面

要做什么：让 Feishu card / Bitable review surface 从 dry-run payload 走到真实可操作、可追踪、可回滚。

为什么要做：可上线产品必须让人能审候选、看版本、拒绝错误记忆，而不是只看 JSON payload。

主要位置：

- `memory_engine/feishu_cards.py`
- `memory_engine/bitable_sync.py`
- `memory_engine/feishu_runtime.py`
- `memory_engine/copilot/feishu_live.py`
- `tests/test_feishu_interactive_cards.py`
- `tests/test_bitable_sync.py`

完成标准：

- Candidate Review card、Version Chain card、Reminder Candidate card 都能真实触发 action。
- confirm / reject / view versions 只通过 `CopilotService` / `handle_tool_request()`。
- non-reviewer 操作被拒绝，且 candidate 状态不变。
- Bitable 写回有幂等、失败重试和读回确认。
- card / Bitable 不展示未授权 evidence/current_value。

建议验证：

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_feishu_interactive_cards tests.test_bitable_sync tests.test_copilot_tools
git diff --check
ollama ps
```

### 8. P1：审计、监控和运维面

要做什么：把 `memory_audit_events` 从 smoke test 表升级为可查询、可告警、可复盘的运维面。

为什么要做：上线后必须回答谁创建、确认、拒绝、越权请求、提醒生成和 ingestion 失败。

主要位置：

- `memory_engine/copilot/service.py`
- `memory_engine/copilot/healthcheck.py`
- `memory_engine/db.py`
- `docs/productization/contracts/audit-observability-contract.md`
- 新增后续 observability handoff

完成标准：

- audit query 或导出入口可用。
- healthcheck 能看到 audit event 数、最近失败、权限 deny、redaction 计数。
- 日志不泄露 token、secret、raw private memory。
- 有告警边界：连续 permission deny、ingestion 失败、websocket down、embedding unavailable。
- 有回滚和停机流程。

建议验证：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_copilot_health.py --json
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_healthcheck tests.test_copilot_permissions
git diff --check
ollama ps
```

### 9. P2：真实样本评测和 release QA

要做什么：把 fixture benchmark 扩展为真实飞书测试群表达、真实文档、真实任务语境下的评测集。

为什么要做：当前指标证明核心逻辑能跑；上线前还要证明真实用户表达下不会误记、误召回、泄露或乱提醒。

主要位置：

- `benchmarks/`
- `memory_engine/benchmark.py`
- `docs/benchmark-report.md`
- `docs/productization/prd-completion-audit-and-gap-tasks.md`
- `docs/productization/phase-e-no-overclaim-handoff.md`

完成标准：

- 保留现有 recall / candidate / conflict / layer / prefetch / heartbeat runner。
- 新增真实样本时不删除失败样例；失败要分类和解释。
- 指标至少保留 Recall@3、Evidence Coverage、Conflict Accuracy、Candidate Precision、Context Use、Sensitive Reminder Leakage。
- release 前做 no-overclaim claim audit。

建议验证：

```bash
python3 scripts/check_openclaw_version.py
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_layer_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
git diff --check
ollama ps
```

### 10. P2：体验和旧入口收敛

要做什么：减少命令感，让 Agent 自然判断何时 search、prefetch、create candidate；同时把旧 CLI / Bot handler 收敛为 fallback，不让双轨逻辑长期分叉。

为什么要做：用户要的是办公 Copilot，不是记忆命令集合。

主要位置：

- `memory_engine/copilot/feishu_live.py`
- `memory_engine/feishu_runtime.py`
- `memory_engine/cli.py`
- `docs/demo-runbook.md`
- `README.md`

完成标准：

- 普通自然语言能触发合适的 memory tool。
- 回复里能说明当前结论、证据、版本、边界和下一步动作。
- 旧 Bot/CLI 文档明确 fallback，不再作为主入口。
- onboarding 文档能让新用户在 10 分钟内理解产品并跑通 demo。

建议验证：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_demo_readiness.py --json
python3 -m unittest tests.test_copilot_feishu_live tests.test_demo_seed tests.test_demo_readiness
git diff --check
ollama ps
```

## 每个任务完成后的交付物

每完成上面任一任务，必须留下这些证据：

1. README 顶部任务区更新。
2. 对应 handoff 或 productization 文档更新。
3. 飞书共享任务看板同步并读回确认。
4. 验证命令和结果摘要。
5. Ollama 清理状态。
6. commit + push。

## 当前不要做

- 不要把测试群 sandbox 写成 production live。
- 不要在真实飞书来源上自动 active。
- 不要绕过 `CopilotService` 直接改 repository 状态。
- 不要升级 OpenClaw 版本。
- 不要把 Cognee 不可用时的 fallback 说成真实 Cognee 主路径。
