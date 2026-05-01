# Feishu Memory Copilot

飞书 AI 挑战赛 OpenClaw 赛道项目。

本项目要做的是一个 **OpenClaw-native Feishu Memory Copilot**：让 OpenClaw Agent 在飞书工作流里拥有可治理、可追溯、可审计的企业长程记忆能力。

它不是一个普通聊天 Bot，也不是简单的向量数据库 Demo。核心目标是：**把飞书消息、文档、任务上下文里的长期有效信息，转成带证据、带权限、可确认、可版本化的企业记忆，并通过 OpenClaw 工具给 Agent 使用。**

---

## 1. 当前项目状态

当前状态：**MVP / Demo / Pre-production 闭环已完成，生产级长期运行还未完成。**

状态快照：2026-05-01，以当前代码、`docs/productization/full-copilot-next-execution-doc.md`、`docs/productization/prd-completion-audit-and-gap-tasks.md`、`docs/productization/deep-research-improvement-backlog.md` 和 `docs/productization/user-experience-todo.md` 为准。

### 当前真实 Feishu 使用边界

按当前代码，本项目已经进入“**allowlist 群里的被动候选识别 + @Bot / 私聊主动交互**”阶段，但还不是全量 workspace ingestion。当前稳定边界是：

- `scripts/start_copilot_feishu_live.sh` 默认启动的是 **allowlist 测试群** 的 `copilot-feishu listen` 入口，不是全量 workspace ingestion。
- 不在 allowlist 的 chat 会被直接忽略。
- allowlist 群里：
  - **不 `@Bot`** 的消息会做静默 candidate probe；命中企业级记忆信号时进入 `memory.create_candidate`，再由 review policy 判断低风险自动确认或私聊人工审核，默认不回群消息。
  - **`@Bot`** 的消息仍走主动交互路径：搜索、候选确认、版本解释、prefetch 等。
  - 当用户主动 `@Bot` 创建 candidate 后，创建者自己会收到可点击的确认卡片；创建者按 owner 身份可以直接确认，不必额外进入 reviewer allowlist。
- OpenClaw gateway 旁路脚本已补本地 `route_gateway_message()` 静默筛选入口：allowlist 群里未 `@Bot` 的低信号/问句会静默忽略，命中企业记忆信号才进入 `handle_tool_request("memory.create_candidate")` / `CopilotService`；这仍是本地受控入口，不等于真实 gateway 长期运行已完成。
- 普通问句不会因为命中了“部署 / 负责人 / 截止”这类主题词就自动变成 candidate。
- 真实飞书来源不再“一律 candidate-only”：低重要性、无冲突、无敏感风险的候选可以由 policy 自动确认成 active；项目进展重要、重要角色发言、敏感/高风险或冲突内容仍必须停在 candidate，优先通过 DM/private 定向推给相关 reviewer / owner 确认。当前已完成 publisher 层定向 DM 发送和本地测试；真实飞书长期运行仍不宣称完成。
- 群级设置已有只读卡片入口：`/settings` 或 `/group_settings` 展示 allowlist 静默筛选、审核投递、auto-confirm policy、scope/visibility 和生产边界；当前不提供设置写入动作。
- OpenClaw websocket 下的受控真实 DM 是另一条验收路径；它证明过一次 `fmc_memory_search` allow-path，不等于“所有真实飞书对话都已经稳定进入本项目工具链路”。
- OpenClaw 对外工具名一律使用 `fmc_*`；`memory.*` 只保留为 Python 内部服务名，避免和 OpenClaw 内置 `memory_search` 语义混淆。

### 已完成

| 能力 | 当前状态 | 主要证据 |
|---|---|---|
| OpenClaw memory 工具 | 已完成本机 first-class tool registry、Agent 本地 `fmc_*` 工具调用验证、OpenClaw gateway 本地静默候选筛选入口，以及一次受控真实 Feishu DM -> `fmc_memory_search` -> `CopilotService` allow-path live E2E 证据 | `agent_adapters/openclaw/plugin/`、`agent_adapters/openclaw/memory_tools.schema.json`、`scripts/openclaw_feishu_remember_router.py`、`tests/test_openclaw_tool_registry.py`、`tests/test_feishu_dm_routing.py`、`tests/test_openclaw_feishu_remember_router.py`、`docs/productization/handoffs/feishu-dm-routing-handoff.md` |
| Copilot Core | 已完成核心服务层 | `memory_engine/copilot/service.py`、`tools.py`、`governance.py`、`retrieval.py` |
| 权限门控 | 已完成 fail-closed 本地闭环 | `memory_engine/copilot/permissions.py`、`tests/test_copilot_permissions.py` |
| 真实飞书权限映射 | 已完成本地权限映射闭环 | `memory_engine/copilot/feishu_live.py`、`memory_engine/copilot/permissions.py`、`docs/productization/handoffs/real-feishu-permission-mapping-handoff.md` |
| 真实飞书可点击卡片 | 已完成受控 sandbox/pre-production 路径：Feishu live interactive 回复使用 typed card，候选审核卡可点击确认、拒绝、要求补证据和标记过期；点击动作重新生成当前 operator 权限上下文并进入 `handle_tool_request()` / `CopilotService` | `memory_engine/copilot/feishu_live.py`、`memory_engine/feishu_events.py`、`memory_engine/feishu_cards.py`、`tests/test_copilot_feishu_live.py`、`docs/productization/handoffs/real-feishu-interactive-cards-handoff.md` |
| 定向审核收件箱、DM 投递与撤销/合并体验 | 已完成本地受控路径：`/review` 默认打开“待我审核”收件箱卡片，只对当前 reviewer/owner 定向可见；定向 interactive card 由 publisher 逐个 `open_id/user_id` 发送 DM，不再回群；收件箱可按 mine/conflicts/high_risk 查看并直接点击确认、拒绝、补证据；冲突候选卡显示旧结论/新结论并提供“确认合并”；`/undo` 和 card action router 可把已确认/拒绝/补证据/过期的候选撤回待审核 | `memory_engine/copilot/review_inbox.py`、`memory_engine/copilot/feishu_live.py`、`memory_engine/feishu_cards.py`、`memory_engine/feishu_events.py`、`memory_engine/feishu_publisher.py`、`scripts/openclaw_feishu_card_action_router.py`、`tests/test_copilot_review_inbox.py`、`tests/test_copilot_feishu_live.py`、`tests/test_feishu_publisher.py`、`tests/test_openclaw_feishu_card_action_router.py` |
| 候选记忆治理 | 已完成 candidate / confirm / reject / conflict / version chain | `memory_engine/copilot/governance.py` |
| 检索链路 | 已完成 L0/L1/L2/L3 分层混合检索 | `memory_engine/copilot/orchestrator.py`、`retrieval.py` |
| 审计表 | 已完成 SQLite 本地审计闭环 | `memory_engine/db.py`、`memory_audit_events` |
| 存储迁移和备份恢复 | 已完成本地 migration dry-run / apply、索引检查，以及 SQLite staging backup / verify / restore drill；这不是生产 PostgreSQL / PITR | `scripts/migrate_copilot_storage.py`、`scripts/backup_copilot_storage.py`、`tests/test_copilot_storage_migration.py`、`tests/test_storage_backup.py` |
| 企业图谱群/用户/消息拓扑 | 已完成本地 Feishu 群节点发现与授权消息拓扑：新群会登记为同企业下的 `feishu_chat` 图谱节点；未在 allowlist 的群只记录 org/chat 最小元数据；授权群会把同一用户建模为 tenant/org 内唯一 `feishu_user` 节点，并用 membership/message 边表达其在不同群里的上下文；消息正文仍只进入 `raw_events` / candidate evidence，不写入图谱节点 | `memory_engine/copilot/graph_context.py`、`memory_engine/copilot/feishu_live.py`、`tests/test_copilot_feishu_live.py`、`docs/productization/handoffs/feishu-group-graph-node-handoff.md` |
| LLM Wiki / Graph Admin | 已完成本地 / staging 后台：active curated memory 编译成 LLM Wiki，Graph tab 展示 storage graph + compiled memory graph，Tenants tab 支持 tenant/org 过滤、readiness、admin-only tenant policy editor 和 `tenant_policy_upserted` 审计；这不是生产 DB、真实企业 IdP SSO 或完整多租户权限后台 | `memory_engine/copilot/admin.py`、`memory_engine/db.py`、`scripts/check_copilot_admin_readiness.py`、`scripts/check_copilot_admin_ui_smoke.py`、`tests/test_copilot_admin.py`、`docs/productization/admin-llm-wiki-launch-runbook.md` |
| Cognee 主路径 | 已完成本地可控同步 / 检索 / fallback 闭环 | `memory_engine/copilot/cognee_adapter.py`、`memory_engine/copilot/retrieval.py`、`tests/test_copilot_cognee_adapter.py`、`docs/productization/cognee-main-path-handoff.md` |
| Feishu live sandbox | 已完成受控测试群联调；当前稳定路径是 allowlist 测试群，群内非 `@Bot` 消息可静默探测 candidate，`@Bot` / 私聊走主动交互 | `memory_engine/copilot/feishu_live.py`、`scripts/start_copilot_feishu_live.sh`、`tests/test_copilot_feishu_live.py` |
| 群级设置卡片 | 已完成只读设置卡：`/settings` / `/group_settings` 展示 allowlist 静默筛选、审核投递、auto-confirm policy、scope/visibility 和 no-overclaim 边界；不提供写入动作 | `memory_engine/copilot/feishu_live.py`、`memory_engine/feishu_cards.py`、`tests/test_copilot_feishu_live.py`、`tests/test_feishu_interactive_cards.py` |
| Limited Feishu ingestion | 已完成本地受控 ingestion 底座，支持文档、任务、会议、Bitable，以及 allowlist 群里被动探测或显式路由到 `memory.create_candidate` 的飞书消息；当前新增 review policy：低重要性安全候选可自动确认，重要/敏感/冲突候选仍需人工确认；这不是被动全量群聊摄入 | `memory_engine/document_ingestion.py`、`memory_engine/copilot/review_policy.py`、`tests/test_document_ingestion.py`、`tests/test_copilot_review_policy.py` |
| 真实 Feishu API 拉取入口 | 已完成任务、会议、Bitable 读取 fetcher、Feishu live `/task` / `/meeting` / `/bitable` 路由和 fetch 前 fail-closed 权限门控；结果进入 `memory.create_candidate` 后由 review policy 决定自动确认或人工审核 | `memory_engine/feishu_task_fetcher.py`、`memory_engine/feishu_meeting_fetcher.py`、`memory_engine/feishu_bitable_fetcher.py`、`memory_engine/copilot/tools.py`、`memory_engine/copilot/review_policy.py`、`tests/test_feishu_fetchers.py`、`tests/test_copilot_review_policy.py` |
| 审计查询、告警和运维面 | 已完成本地审计查询/导出、告警脚本、ingestion failure 显式审计、healthcheck websocket 运维入口、embedding fallback 可观测字段，以及 staging Prometheus alert-rule artifact / verifier；这仍不是生产级 Prometheus/Grafana 长期监控 | `scripts/query_audit_events.py`、`scripts/check_audit_alerts.py`、`scripts/check_prometheus_alert_rules.py`、`deploy/monitoring/copilot-admin-alerts.yml`、`memory_engine/document_ingestion.py`、`memory_engine/copilot/healthcheck.py`、`tests/test_audit_ops_scripts.py`、`tests/test_prometheus_alert_rules.py`、`docs/productization/handoffs/audit-ops-observability-handoff.md` |
| Productized live 长期运行方案 | 已完成方案和上线 gate，覆盖部署拓扑、单监听、存储、监控告警、权限后台、审计 UI、停写回滚和 no-overclaim 边界；尚未实施生产长期运行 | `docs/productization/productized-live-long-run-plan.md`、`docs/productization/handoffs/productized-live-long-run-plan-handoff.md` |
| OpenClaw Feishu websocket staging | 已完成本机 running 证据 | `scripts/check_openclaw_feishu_websocket.py`、`docs/productization/handoffs/openclaw-feishu-websocket-handoff.md` |
| Demo readiness | 已完成一键检查 | `scripts/check_demo_readiness.py` |
| Benchmark | 已完成多类评测样例 | `benchmarks/copilot_*.json`、`docs/benchmark-report.md` |
| Deep research 改进闭环 | 已完成第一轮代码收口：stable memory key / alias 层、score breakdown 输出、stale shadow filter、deterministic embedding fallback、graph review target / prefetch context、conflict/reject benchmark runner 修正、组合式 search 摘要、本地编译型记忆卡册，以及受控真实 Feishu Task fetch -> candidate smoke；最新本地重跑显示 recall 40/40、conflict 35/35、prefetch 20/20 均通过，stale leakage 均为 0.0000；仍保留 productized live 长期运行为后续风险 | `memory_engine/copilot/stable_keys.py`、`memory_engine/copilot/governance.py`、`memory_engine/copilot/review_inbox.py`、`memory_engine/copilot/knowledge_pages.py`、`memory_engine/feishu_task_fetcher.py`、`memory_engine/benchmark.py`、`tests/test_copilot_stable_keys.py`、`tests/test_copilot_review_inbox.py`、`tests/test_copilot_prefetch.py`、`tests/test_feishu_fetchers.py`、`tests/test_copilot_knowledge_pages.py`、`docs/productization/deep-research-improvement-backlog.md` |
| 白皮书 / 答辩材料 | 已完成初稿和 10 分钟评委体验包，放在后半部分查看 | `docs/memory-definition-and-architecture-whitepaper.md`、`docs/demo-runbook.md`、`docs/judge-10-minute-experience.md` |

### 不能 overclaim

不能说已经完成：

- 生产部署。
- 全量接入飞书 workspace。
- 多租户企业后台。
- 长期 embedding 服务。
- 真实 Feishu DM 稳定路由到本项目 first-class `fmc_*` / `memory.*` 工具链路。
- productized live 长期运行。

### 当前最重要的未完成项

| 优先级 | 任务 | 完成标准 |
|---|---|---|
| P1 | 扩大真实飞书样本实测 | 已完成 1 条受控真实 Feishu Task fetch -> candidate smoke；后续继续扩到 Meeting / Bitable 和更多真实表达样本，保留 review-policy gate、失败 fallback 和 no-overclaim |
| P1 | 扩大真实飞书可点击卡片实测 | 在受控测试群里用真实卡片点击覆盖 `确认保存`、`拒绝候选`、`要求补证据`、`标记过期`，并读回审计；不把一次 sandbox 点击写成生产长期运行 |
| P1 | 扩大真实飞书审核收件箱实测 | 在受控测试群里用 `/review`、`/review conflicts`、`确认合并` 和 `/undo` 覆盖真实卡片点击与审计读回；当前只完成本地受控路径，不宣称真实 DM/群长期稳定运行 |
| P1 | 扩大真实 DM 定向投递实测 | 在 lark-cli 认证可用后，用受控 reviewer/owner open_id 读回 DM 卡片投递和失败 fallback；当前完成 publisher 本地测试，不宣称生产长期运行 |
| P2 | 继续推进 productized live gate | 已完成本地 tenant policy editor；后续从 L1 internal pilot、PostgreSQL pilot、真实企业 IdP SSO 验收、审计 read-only view 中选一个小 gate 实施；仍不宣称 productized live 完成 |
| P2 | 收敛评委版文档入口 | README 顶部保持简洁，把答辩、白皮书、详细计划放到后半段 |

---

## 2. 快速开始

最小验收：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_copilot_health.py --json
python3 scripts/check_demo_readiness.py --json
```

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

### 2.3 配置 Cognee（可选，用于真实 Cognee 运行）

Cognee 是可选的 recall channel，用于增强记忆检索能力。如需使用真实 Cognee 运行：

#### 2.3.1 配置环境变量

复制 `.env.example` 到 `.env`，并配置必要的环境变量：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置以下关键变量：

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

#### 2.3.2 确保 Ollama 服务运行

```bash
# 启动 Ollama 服务（如果未运行）
ollama serve

# 拉取 embedding 模型
ollama pull qwen3-embedding:0.6b-fp16
```

#### 2.3.3 验证 Cognee 配置

```bash
# 运行 dry-run 测试
python3 scripts/spike_cognee_local.py --dry-run

# 运行真实 Cognee spike 测试
python3 scripts/spike_cognee_local.py --scope project:feishu_ai_challenge --query "测试查询"
```

#### 2.3.4 Cognee 配置说明

- **LLM_PROVIDER**: 使用 `custom` 配合 RightCode 服务
- **LLM_API_KEY**: 必填，RightCode API 密钥
- **EMBEDDING_MODEL**: 默认使用本地 Ollama 的 `qwen3-embedding:0.6b-fp16`
- **EMBEDDING_ENDPOINT**: Ollama 服务地址，默认 `http://localhost:11434`

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

Dashboard 不是单独的产品服务。它提供本地 LLM Wiki、知识图谱、tenant readiness、memory ledger、audit 和 schema table 视图，用于把 active curated memory 编译成可展示的企业知识资产，同时观察 Feishu 群/用户/消息图谱拓扑。Wiki / Graph / Ledger / Audit 仍是只读知识面；Tenants tab 已有 admin-only 的本地/pre-production 租户策略编辑入口，可配置默认 visibility、reviewer roles、admin users、SSO allowed domains、低风险 auto-confirm 和冲突人工审核开关。Wiki / Graph / Tenants / Ledger / Audit 支持按 `tenant_id` 和 `organization_id` 收敛展示；这仍不等于生产 DB、真实企业 IdP SSO 验收或 productized live。Feishu live listener 默认会随 runtime 启动；OpenClaw 插件侧为避免工具加载副作用，必须显式 opt-in：

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
python3 scripts/check_copilot_admin_production_evidence.py --json
python3 scripts/check_copilot_knowledge_site_export.py --json
python3 scripts/check_llm_wiki_enterprise_site_completion.py --json
python3 scripts/check_copilot_admin_ui_smoke.py --db-path data/memory.sqlite --scope project:feishu_ai_challenge --output-dir /tmp/copilot-admin-ui-smoke --json
python3 scripts/check_prometheus_alert_rules.py --json
```

`check_copilot_admin_sso_gate.py` 会在 loopback 上启动临时 admin server，验证无 header 拒绝、allowed-domain viewer 只读、admin SSO 身份可导出 Wiki、`/metrics` 需要认证、`/api/health` 报告 SSO policy。它只证明反向代理 header gate 的 staging 行为，不等于真实企业 IdP / Feishu SSO 生产验收。

`check_copilot_admin_env_file.py` 默认校验 `deploy/copilot-admin.env.example` 是否保持安全占位符；传 `--env-file /etc/feishu-memory-copilot/admin.env --expect-runtime --json` 可校验本机真实 runtime env 是否替换 token、端口合法、远程绑定有 token、SSO 配置完整。报告只输出 redacted state，不输出 token 明文。

`check_copilot_admin_deploy_bundle.py` 会检查 systemd / Nginx / TLS 模板、SSO header 边界、monitoring alert artifact、backup gate、readiness gate 和 completion audit gate；当前预期输出是 `staging_bundle_ok=true` 且 `production_blocked=true`。

`check_copilot_admin_production_evidence.py` 默认检查 `deploy/copilot-admin.production-evidence.example.json` 的结构和密钥脱敏，预期 `ok=true`、`production_ready=false`；真实上线时传入已填好的 manifest 并加 `--require-production-ready`，才会要求生产 DB、真实 IdP SSO、域名/TLS、生产监控和 24 小时 long-run 证据全部通过。

`check_copilot_knowledge_site_export.py` 会导出一个临时静态知识站，并校验 `index.html`、`data/manifest.json`、`data/wiki.json`、`data/graph.json`、`wiki/*.md`、Graph detail UI、read-only boundary 和 secret-like 文本脱敏。

`check_copilot_admin_ui_smoke.py` 会启动本机 admin、导出静态站并截图，除桌面/移动端 Graph、Tenants、Launch 和静态站 DOM 断言外，还会对截图做像素级非空白、色彩多样性、主色占比和文件大小检查。

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

答辩材料放在这里：

| 材料 | 路径 | 用途 |
|---|---|---|
| Demo runbook | `docs/demo-runbook.md` | 5 分钟演示脚本 |
| Benchmark report | `docs/benchmark-report.md` | 指标和评测证据 |
| Memory 白皮书 | `docs/memory-definition-and-architecture-whitepaper.md` | Define it / Build it / Prove it |
| PRD 完成度审计 | `docs/productization/prd-completion-audit-and-gap-tasks.md` | 当前完成度和未完成边界 |
| 产品化执行文档 | `docs/productization/full-copilot-next-execution-doc.md` | 后续执行主线 |
| OpenClaw runtime evidence | `docs/productization/openclaw-runtime-evidence.md` | OpenClaw Agent 受控验收证据 |
| Feishu websocket handoff | `docs/productization/handoffs/openclaw-feishu-websocket-handoff.md` | Feishu websocket staging 证据 |
| Storage migration handoff | `docs/productization/storage-migration-productization-handoff.md` | 存储迁移和生产存储试点方案 |
| Review surface handoff | `docs/productization/handoffs/review-surface-operability-handoff.md` | Bitable review 写回幂等和读回确认 |
| Audit ops handoff | `docs/productization/handoffs/audit-ops-observability-handoff.md` | 审计查询、告警和运维 healthcheck 补齐 |

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
git diff --check
```

Python / Copilot 代码改动：

```bash
python3 scripts/check_openclaw_version.py
git diff --check
python3 -m compileall memory_engine scripts
python3 -m unittest discover tests
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

Cognee 相关验证：

```bash
# 检查 Cognee SDK 可用性
python3 -c "import cognee; print('Cognee SDK available')"

# 运行 Cognee dry-run 测试
python3 scripts/spike_cognee_local.py --dry-run

# 运行真实 Cognee spike 测试
python3 scripts/spike_cognee_local.py --scope project:feishu_ai_challenge --query "生产部署参数"

# 检查 embedding 服务状态
python3 scripts/check_embedding_provider.py
```

Benchmark：

```bash
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_layer_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
```

---

## 11. 项目边界

本项目当前是比赛项目和产品化原型，不是完整生产系统。

当前已经证明：

- 本地可复现。
- Demo 可演示。
- Benchmark 可运行。
- OpenClaw tool contract 可检查。
- 飞书测试群 sandbox 可联调。
- 权限、证据、版本、审计有本地闭环。
- 存储迁移和索引检查有本地 dry-run / apply 入口。

当前尚未完成：

- 生产部署。
- 全量飞书 workspace ingestion。
- 多租户企业后台。
- 真实权限后台。
- 生产级长期在线 embedding 服务（本地 Ollama 已集成，非生产级）。
- 生产级 Prometheus/Grafana 长期监控、告警投递和自动回滚；当前只有 `/metrics`、staging alert rules artifact 和本地 verifier。
- 真实 Feishu DM 稳定路由到本项目 first-class `fmc_*` / `memory.*` 工具链路；当前只有一次受控 DM allow-path live E2E 证据。
