# AGENTS.md

这个文件是给 Codex / 自动执行代理看的入口地图。详细规则不要堆在这里；按 harness engineering 的做法，`AGENTS.md` 只回答“先看哪里、当前边界是什么、哪些检查必须跑”。

当前项目是飞书 AI 挑战赛 OpenClaw 赛道项目：**OpenClaw-native Feishu Memory Copilot**。目标是把飞书工作流里的长期有效信息，转成带证据、带权限、可确认、可版本化、可审计的企业记忆，并通过 OpenClaw 工具给 Agent 使用。

核心链路：

```text
OpenClaw Agent
  -> fmc_* / memory.* tools
  -> handle_tool_request()
  -> CopilotService
  -> permissions / governance / retrieval / audit
  -> SQLite / Cognee adapter / Feishu / Bitable
```

---

## 1. 先读顺序

每次开始新任务，先读：

```text
AGENTS.md
README.md
docs/harness/README.md
docs/productization/agent-execution-contract.md
docs/productization/full-copilot-next-execution-doc.md
docs/productization/prd-completion-audit-and-gap-tasks.md
docs/productization/complete-product-roadmap-prd.md
docs/productization/complete-product-roadmap-test-spec.md
```

如果任务涉及 productization、评委材料、handoff、真实 Feishu/OpenClaw 验收或上线边界，再读：

```text
docs/README.md
docs/human-product-guide.md
docs/productization/workflow-and-test-process.md
docs/productization/launch-polish-todo.md
docs/productization/contracts/
```

只有用户明确要求执行某个绝对日期任务时，才读取 `docs/plans/YYYY-MM-DD-implementation-plan.md` 和 `docs/plans/YYYY-MM-DD-handoff.md`。`docs/archive/` 只作为 reference / fallback。

---

## 2. 当前事实源优先级

1. 用户当前最新指令。
2. 当前代码状态。
3. `README.md` 顶部当前状态。
4. `docs/productization/full-copilot-next-execution-doc.md`
5. `docs/productization/prd-completion-audit-and-gap-tasks.md`
6. 相关 productization contract / runbook / handoff。
7. 历史日期计划和归档文档。

如果历史文档和当前代码冲突，以当前代码和最新产品化文档为准。

---

## 3. 当前主线

主线只做：

```text
OpenClaw-native Feishu Memory Copilot
```

新能力优先进入：

```text
memory_engine/copilot/
agent_adapters/openclaw/
docs/productization/
tests/test_copilot_*.py
benchmarks/copilot_*.json
```

旧实现只能作为 fallback：

```text
memory_engine/repository.py
memory_engine/feishu_runtime.py
legacy CLI commands
docs/archive/
benchmarks/day*.json
```

除非任务明确要求修 legacy，否则不要从旧 Bot / 旧 CLI 主线开始。

---

## 4. 不能 overclaim

可以说：MVP / Demo / Pre-production 本地闭环已完成；OpenClaw tool schema、本地 bridge、`CopilotService` 权限门控、候选记忆、版本链、审计、检索、受控飞书测试群 live sandbox、benchmark、demo readiness、first-class OpenClaw tool registry、本机 websocket staging 证据、storage migration dry-run / apply 与生产存储试点方案已完成。

不能说：生产部署已完成、全量接入飞书 workspace、多租户企业后台已完成、长期 embedding 服务已完成、真实 Feishu DM 已稳定路由到本项目 first-class `memory.*` 工具、productized live 长期运行已完成。

所有 README、handoff、commit message、看板备注都必须遵守这个边界。完整表述见 `docs/productization/agent-execution-contract.md`。

---

## 5. Copilot-first 硬规则

- OpenClaw 工具变更先看 `agent_adapters/openclaw/memory_tools.schema.json`。
- 服务入口必须统一到 `handle_tool_request()` / `CopilotService`。
- `memory.*` 工具必须带 `current_context.permission`，缺失、畸形、scope / tenant / org mismatch 都 fail closed。
- 真实飞书来源必须先进入 review policy 判定：低风险、低重要性、无冲突内容可以自动确认成 active；项目进展重要、重要角色发言、敏感/高风险或冲突内容必须停在 candidate 并经过 reviewer/owner 人工确认。
- 默认只对 curated memory 做 embedding，不向量化全部 raw events。
- Cognee 是当前选定 memory / knowledge engine，只能通过 `memory_engine/copilot/cognee_adapter.py` 窄 adapter 接入。
- OpenClaw 固定版本 `2026.4.24`，禁止主动 `openclaw update` 或安装 latest。
- Feishu websocket、Copilot lark-cli sandbox、legacy listener 三选一，不要多个监听消费同一个 bot。

---

## 6. 必跑验证

所有提交前都跑：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
git diff --check
```

改 Python、脚本、schema、benchmark runner 时追加：

```bash
python3 -m compileall memory_engine scripts
```

改 Copilot schema / tools / service 时追加：

```bash
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools
```

改权限、治理、候选记忆时追加：

```bash
python3 -m unittest tests.test_copilot_permissions tests.test_copilot_governance
```

改 harness、AGENTS 或执行规则时追加：

```bash
python3 -m unittest tests.test_agent_harness
```

更多专项验证规则见 `docs/productization/agent-execution-contract.md`。

---

## 7. 提交和同步

每完成一个可运行闭环、阶段交付或关键文档更新后，需要提交并推送。只提交当前任务相关文件，不回退或覆盖无关改动，不提交 `.env`、`.omx/`、`data/*.sqlite`、`logs/`、临时报告、缓存、真实群聊 ID / 用户 ID / token。

README 顶部当前任务变化、handoff 更新、产品化执行文档更新、开始或完成新阶段时，需要同步飞书任务看板并读回确认。看板操作流程见 `docs/productization/agent-execution-contract.md`。
