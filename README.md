# Feishu Memory Copilot

面向飞书 / Lark 工作流的 OpenClaw-native 企业记忆 Copilot。

本项目把飞书消息、文档、表格、多维表格和受控 workspace 资源里的长期有效信息，转成可治理的企业记忆：有证据、有权限、可确认、可版本化、可审计，并通过 OpenClaw 工具交给 Agent 使用。

项目用于飞书 AI 挑战赛 OpenClaw 赛道。

## 当前状态

当前阶段：**MVP / 演示 / 预生产**。

已经完成：

- 面向 OpenClaw 的 `fmc_*` 记忆工具。
- 统一入口 `handle_tool_request()` -> `CopilotService`。
- 候选记忆、人工确认、拒绝、冲突合并、版本历史、检索、任务预取和审计。
- 受控飞书 sandbox 流程，包括 review 卡片和权限反例。
- 有限 workspace ingestion 试点和产品化 readiness 证据。
- 演示 replay、readiness 检查、benchmark 报告和评委演示材料。

不声称已经完成：

- 生产部署。
- 全企业飞书 workspace 无限制接入。
- 生产级多租户后台。
- 生产级长期 embedding 服务。
- 所有真实飞书私聊、群聊、workspace 事件的长期稳定路由。

## 解决的问题

团队真正需要的不是简单搜索聊天记录，而是回答这些问题：

- 当前有效的项目规则是什么？
- 这条规则来自哪里，有什么证据？
- 谁有权限查看、确认或修改它？
- 哪条旧规则已经被新规则覆盖？
- Agent 执行任务前应该自动带上哪些上下文？

Feishu Memory Copilot 把“记忆”当成一个可治理对象，而不是一段无来源的 RAG 摘要。

## 核心概念

| 概念 | 含义 |
|---|---|
| `candidate` | 从协作上下文中抽取出的候选记忆，尚未被信任。 |
| `active` | 当前可信记忆，会参与检索和任务预取。 |
| `superseded` | 已被覆盖的旧版本，默认不直接回答，但可用于解释历史。 |
| `evidence` | 来源引用、来源类型、来源 ID、tenant / org / scope 元数据。 |
| `permission` | 通过 `current_context.permission` 携带的 fail-closed 权限判断。 |
| `audit` | 请求 ID、trace ID、操作者、决策和 review/action 元数据。 |

## 架构

```text
飞书 / Workspace 来源
  -> 候选记忆抽取
  -> review policy
  -> CopilotService
  -> permissions / governance / retrieval / audit
  -> SQLite ledger / 可选 Cognee adapter
  -> OpenClaw fmc_* tools
  -> Agent search / versions / prefetch
```

关键目录：

- `agent_adapters/openclaw/`：OpenClaw schema、plugin 和示例。
- `memory_engine/copilot/`：service、tools、permissions、governance、retrieval。
- `memory_engine/`：存储、飞书适配、benchmark 支撑。
- `scripts/`：demo、readiness、证据采集和 workspace 工具。
- `benchmarks/`：benchmark 用例。
- `tests/`：回归测试。

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python3 -m memory_engine init-db
```

运行基础检查：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_copilot_health.py --json
python3 scripts/check_demo_readiness.py --json
```

OpenClaw 版本固定为：

```text
2026.4.24
```

验证本项目时不要升级 OpenClaw。

## 全流程本地部署

下面是一台新机器从零跑通演示 / 预生产链路的完整步骤。它不是生产部署流程。

Agent 自动部署 prompt：请在仓库根目录读取 `docs/productization/agent-auto-deploy-checklist.md`，按“只读检查 -> 隔离部署 -> 验收报告”的顺序执行；未经用户明确授权，不要升级 OpenClaw、不要修改本机 OpenClaw 插件状态、不要启动真实飞书 listener。

### 1. 安装前置依赖

建议使用 Python 3.11+。如果要验证 OpenClaw staging 链路，还需要安装 Node.js/npm，并安装固定版本 OpenClaw：

```bash
npm i -g openclaw@2026.4.24 --no-fund --no-audit
```

### 2. 拉取代码并安装项目

```bash
git clone https://github.com/adjcjh777/lark_ai_challenge_openclaw_longterm_memory.git
cd lark_ai_challenge_openclaw_longterm_memory
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e .
cp .env.example .env
python -m memory_engine init-db
```

Windows PowerShell 激活虚拟环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. 验证本地演示 readiness

```bash
python scripts/check_cross_platform_quick_deploy.py --profile local-demo --json
python scripts/check_openclaw_version.py
python scripts/check_demo_readiness.py --json
python scripts/demo_seed.py --json-output reports/demo_replay.json
```

到这里，本地 replay 演示已经可以运行。

### 4. 启用 OpenClaw plugin 链路

```bash
openclaw plugins install --link --dangerously-force-unsafe-install ./agent_adapters/openclaw/plugin
openclaw plugins enable feishu-memory-copilot
openclaw plugins inspect feishu-memory-copilot --json
python scripts/check_cross_platform_quick_deploy.py --profile openclaw-staging --json
python scripts/check_feishu_dm_routing.py --json
```

`plugins inspect` 输出里应该能看到 `fmc_*` 记忆工具。

### 5. 启动本地管理后台（可选）

```bash
python scripts/check_copilot_admin_readiness.py --db-path data/memory.sqlite
python scripts/start_copilot_admin.py --db-path data/memory.sqlite --host 127.0.0.1 --port 8765
```

浏览器打开：

```text
http://127.0.0.1:8765
```

### 6. 接入受控飞书 sandbox（可选）

只有在 `lark-cli` 已配置、并且明确只启用一个飞书监听入口时才执行这一步。不要让 legacy listener 和 OpenClaw websocket 同时消费同一个 bot。

```bash
python scripts/check_feishu_listener_singleton.py --planned-listener copilot-lark-cli
export LARK_CLI_PROFILE=feishu-ai-challenge
export COPILOT_FEISHU_ALLOWED_CHAT_IDS="<controlled_test_chat_id>"
export COPILOT_FEISHU_REVIEWER_OPEN_IDS="<reviewer_open_id>"
bash scripts/start_copilot_feishu_live.sh
```

如果由 OpenClaw websocket 接管飞书事件，则保持本仓库 listener 停止，并使用：

```bash
python scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
openclaw channels status --probe --json
```

### 7. 可选 embedding / Cognee 预验证

核心演示不依赖实时 embedding provider。要验证本地 embedding 路径，可以运行：

```bash
ollama pull qwen3-embedding:0.6b-fp16
python scripts/check_embedding_provider.py --model ollama/qwen3-embedding:0.6b-fp16 --dimensions 1024
python scripts/check_cross_platform_quick_deploy.py --profile embedding --json
```

不同系统的更细安装说明见：

- `docs/productization/cross-platform-quick-deploy.md`

## 演示

运行固定演示 replay：

```bash
python3 scripts/demo_seed.py --json-output reports/demo_replay.json
```

Replay 覆盖：

- 搜索当前有效决策。
- 冲突更新和版本解释。
- 任务预取上下文包。
- 受控 reminder candidate。
- 演示 / 预生产 readiness 证据。

评委演示脚本见：

- `docs/judge-10-minute-experience.md`
- `docs/demo-runbook.md`
- `docs/productization/expanded-demo-showcase-plan.md`

## 基准测试

Benchmark 用例位于 `benchmarks/copilot_*.json`，覆盖记忆召回、旧值过滤、冲突处理、候选治理、任务预取、heartbeat reminder candidate 和真实飞书表达。

结果和解释见：

- `docs/benchmark-report.md`

## 飞书 / Workspace 边界

当前飞书链路是受控的：

- 新群默认是 `pending_onboarding`。
- 静默候选筛选只对 allowlist 或显式启用的群生效。
- 重要、敏感或冲突事实会停留在 candidate，等待 reviewer 或 owner 确认。
- Workspace ingestion 已证明为有限 / 产品化 readiness 试点，不是无限制企业级 crawler。

Workspace 相关文档：

- `docs/productization/workspace-ingestion-architecture-adr.md`
- `docs/productization/workspace-ingestion-goal-completion-audit-2026-05-04.md`
- `docs/productization/workspace-ingestion-evidence-collection-runbook.md`

## 文档入口

建议从这里开始读：

- `docs/human-product-guide.md`：面向人的产品说明。
- `docs/README.md`：文档地图。
- `docs/demo-runbook.md`：demo 脚本。
- `docs/benchmark-report.md`：benchmark 报告。
- `docs/productization/full-copilot-next-execution-doc.md`：当前执行事实源。

历史计划和 handoff 位于 `docs/archive/` 和 `docs/productization/handoffs/`。它们是证据，不是当前默认执行入口。

## 开发检查

提交前至少运行：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
git diff --check
```

如果修改 Python、schema、tool 或 benchmark 相关内容，请根据 `AGENTS.md` 和 `docs/productization/agent-execution-contract.md` 追加对应单元测试。

## 许可证

比赛原型。作为公开生产项目使用前，请补充正式 License。
