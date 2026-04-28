# Feishu Memory Copilot

飞书 AI 挑战赛 OpenClaw 赛道项目。

本项目要做的是一个 **OpenClaw-native Feishu Memory Copilot**：让 OpenClaw Agent 在飞书工作流里拥有可治理、可追溯、可审计的企业长程记忆能力。

它不是一个普通聊天 Bot，也不是简单的向量数据库 Demo。核心目标是：**把飞书消息、文档、任务上下文里的长期有效信息，转成带证据、带权限、可确认、可版本化的企业记忆，并通过 OpenClaw 工具给 Agent 使用。**

---

## 1. 当前项目状态

当前状态：**MVP / Demo / Pre-production 闭环已完成，生产级长期运行还未完成。**

状态快照：2026-04-28，以当前代码、`docs/productization/full-copilot-next-execution-doc.md` 和 `docs/productization/prd-completion-audit-and-gap-tasks.md` 为准。

### 已完成

| 能力 | 当前状态 | 主要证据 |
|---|---|---|
| OpenClaw memory 工具 | 已完成本机 first-class tool registry | `agent_adapters/openclaw/plugin/`、`agent_adapters/openclaw/memory_tools.schema.json`、`tests/test_openclaw_tool_registry.py` |
| Copilot Core | 已完成核心服务层 | `memory_engine/copilot/service.py`、`tools.py`、`governance.py`、`retrieval.py` |
| 权限门控 | 已完成 fail-closed 本地闭环 | `memory_engine/copilot/permissions.py`、`tests/test_copilot_permissions.py` |
| 真实飞书权限映射 | 已完成本地权限映射闭环 | `memory_engine/copilot/feishu_live.py`、`memory_engine/copilot/permissions.py`、`docs/productization/real-feishu-permission-mapping-handoff.md` |
| 候选记忆治理 | 已完成 candidate / confirm / reject / conflict / version chain | `memory_engine/copilot/governance.py` |
| 检索链路 | 已完成 L0/L1/L2/L3 分层混合检索 | `memory_engine/copilot/orchestrator.py`、`retrieval.py` |
| 审计表 | 已完成 SQLite 本地审计闭环 | `memory_engine/db.py`、`memory_audit_events` |
| 存储迁移方案 | 已完成本地 migration dry-run / apply 和索引检查 | `scripts/migrate_copilot_storage.py`、`tests/test_copilot_storage_migration.py` |
| Cognee 主路径 | 已完成本地可控同步 / 检索 / fallback 闭环 | `memory_engine/copilot/cognee_adapter.py`、`memory_engine/copilot/retrieval.py`、`tests/test_copilot_cognee_adapter.py`、`docs/productization/cognee-main-path-handoff.md` |
| Feishu live sandbox | 已完成受控测试群联调 | `memory_engine/copilot/feishu_live.py`、`scripts/start_copilot_feishu_live.sh` |
| Limited Feishu ingestion | 已完成本地 candidate-only 底座，支持群聊、文档、任务、会议、Bitable 来源文本 | `memory_engine/document_ingestion.py`、`tests/test_document_ingestion.py`、`docs/productization/limited-feishu-ingestion-handoff.md` |
| OpenClaw Feishu websocket staging | 已完成本机 running 证据 | `scripts/check_openclaw_feishu_websocket.py`、`docs/productization/openclaw-feishu-websocket-handoff.md` |
| Demo readiness | 已完成一键检查 | `scripts/check_demo_readiness.py` |
| Benchmark | 已完成多类评测样例 | `benchmarks/copilot_*.json`、`docs/benchmark-report.md` |
| 白皮书 / 答辩材料 | 已完成初稿，放在后半部分查看 | `docs/memory-definition-and-architecture-whitepaper.md`、`docs/demo-runbook.md` |

### 不能 overclaim

不能说已经完成：

- 生产部署。
- 全量接入飞书 workspace。
- 多租户企业后台。
- 长期 embedding 服务。
- 真实 Feishu DM 稳定路由到本项目 first-class `memory.*` 工具。
- productized live 长期运行。

### 当前最重要的未完成项

| 优先级 | 任务 | 完成标准 |
|---|---|---|
| P1 | 打通真实 Feishu DM 到本项目 first-class `memory.*` tool routing | 真实飞书 DM 进入 OpenClaw Agent 后，自然选择本项目 `memory.search` / `memory.prefetch` / `memory.create_candidate` 等工具，并进入 `handle_tool_request()` / `CopilotService` |
| P1 | 接真实 Feishu API 拉取与扩充人工复核样本 | 在 limited ingestion 底座之上，接任务、会议、Bitable 等真实 API 拉取，并保留失败 fallback 和 candidate-only 边界 |
| P2 | 设计 productized live 长期运行方案 | 写清部署、监控、回滚、权限后台、审计 UI 和运维边界 |
| P2 | 收敛评委版文档入口 | README 顶部保持简洁，把答辩、白皮书、详细计划放到后半段 |

---

## 2. 快速开始

最小验收：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_copilot_health.py --json
python3 scripts/check_demo_readiness.py --json
```

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

### 2.4 运行 Demo readiness

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

3. **真实飞书来源只能进入 candidate。**
   不能自动变成 active memory，必须经过 reviewer 确认。

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
- 真实飞书消息默认进入 candidate，不会自动 active。
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
| Feishu websocket handoff | `docs/productization/openclaw-feishu-websocket-handoff.md` | Feishu websocket staging 证据 |
| Storage migration handoff | `docs/productization/storage-migration-productization-handoff.md` | 存储迁移和生产存储试点方案 |
| Review surface handoff | `docs/productization/review-surface-operability-handoff.md` | Bitable review 写回幂等和读回确认 |

答辩时可以用这句话概括：

> 我们做的不是一个会记笔记的 Bot，而是一个 OpenClaw-native 的企业记忆治理层。它把飞书里的长期有效信息转成候选记忆，通过权限门控、证据链、版本链和审计表治理后，再以 `memory.*` 工具的形式提供给 OpenClaw Agent 使用。

---

## 9. 当前主线任务

当前优先级最高的后续任务：

| 任务 | 位置 | 完成标准 |
|---|---|---|
| 打通真实 Feishu DM 到 first-class `memory.*` tool routing | `agent_adapters/openclaw/plugin/`、`memory_engine/copilot/openclaw_tool_runner.py`、`docs/productization/openclaw-feishu-websocket-handoff.md` | 真实 Feishu DM 进入 OpenClaw Agent 后自然选择本项目 memory 工具 |
| 扩大真实 Feishu ingestion 范围 | `memory_engine/document_ingestion.py`、`memory_engine/copilot/feishu_live.py`、`docs/productization/full-copilot-next-execution-doc.md` | 真实飞书来源继续 candidate-only，权限和审计可检查 |
| 补审计、监控和运维面 | `memory_engine/copilot/healthcheck.py`、`memory_engine/db.py`、`docs/productization/contracts/audit-observability-contract.md` | audit 可查询、healthcheck 能看到 deny / failure / redaction 等运维指标 |
| 设计 productized live 长期运行方案 | `docs/productization/full-copilot-next-execution-doc.md` | 写清部署、监控、回滚、权限后台、审计 UI 和运维边界 |
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
- 长期监控、告警、回滚。
- 真实 Feishu DM 稳定路由到本项目 first-class `memory.*` 工具。
