# 后续工作流程和测试流程

日期：2026-04-28
阶段：产品后期打磨和上线前优化

## 先看这个

1. 每次只推进一个明确任务，不跨越还没有验收的上线 gate。
2. 当前主线是 OpenClaw-native Feishu Memory Copilot；旧 CLI / Bot 只做 fallback。
3. 真实飞书来源只进入 candidate；confirm / reject 必须走 `CopilotService` / `handle_tool_request()`。
4. 任何真实 embedding / Cognee / Ollama 验证后，都要检查并清理本项目模型驻留。

## 标准工作流

### 0. 开工检查

每次开始前先运行：

```bash
date '+%Y-%m-%d %H:%M:%S %Z'
git status --short
python3 scripts/check_openclaw_version.py
```

然后读取：

```text
AGENTS.md
README.md
docs/README.md
docs/productization/full-copilot-next-execution-doc.md
docs/productization/launch-polish-todo.md
docs/productization/workflow-and-test-process.md
当前任务相关 contract / runbook / handoff
```

如果看到 `.obsidian/`、`docs/pr-reviews/`、`logs/`、`reports/`、`.data/` 之类未跟踪文件，默认不要提交。

### 1. 明确本轮任务边界

每轮任务先写清：

- 本轮做什么。
- 为什么现在做。
- 要改哪些文件。
- 完成标准是什么。
- 本轮不做什么。
- 需要跑哪些验证。

如果任务会改变 README 顶部任务、handoff 或产品化执行文档，完成后必须同步飞书共享任务看板。

### 2. 先补测试或 healthcheck

代码任务默认先补最小测试或 healthcheck 断言。文档任务不用写代码测试，但要跑基础文档验证命令。

常见策略：

- OpenClaw schema / tool：先补 `tests.test_copilot_schemas` 或 `tests.test_copilot_tools`。
- 权限 / 越权：先补 `tests.test_copilot_permissions`。
- Feishu card / Bitable：先补 `tests.test_feishu_interactive_cards` 或 `tests.test_bitable_sync`。
- Feishu live sandbox：先补 `tests.test_copilot_feishu_live`。
- Cognee / retrieval：先补 `tests.test_copilot_cognee_adapter` 或 `tests.test_copilot_retrieval`。
- Benchmark：先补 fixture，再跑对应 benchmark runner。

### 3. 实现时保持事实源单一

新功能优先改：

```text
memory_engine/copilot/
agent_adapters/openclaw/
```

入口层只能调用 Copilot Core：

```text
Feishu / OpenClaw / Bitable / CLI
        -> handle_tool_request()
        -> CopilotService
        -> governance / retrieval / permissions / audit
```

不要让 Feishu card、Bitable、旧 Bot 或 benchmark runner 直接改 active memory。

### 4. 写 handoff 和 no-overclaim 边界

每轮收尾至少写清：

- 已完成什么。
- 如何验证。
- 仍未完成什么。
- 是否触达真实飞书、真实 embedding、真实 OpenClaw runtime。
- 是否清理 Ollama 模型。
- 本轮不能对外声称什么。

### 5. 验证、看板、提交、推送

收尾顺序：

1. 运行对应验证命令。
2. 运行 `ollama ps` 并清理本项目模型。
3. 更新 README / handoff / 看板。
4. `git status --short` 确认只提交相关文件。
5. `git diff --check`。
6. commit message 写清 `Tested:` / `Not-tested:`。
7. `git push origin HEAD`。

## 按改动类型选择验证命令

### 文档-only

适用：只改 README、docs、计划、handoff、白皮书、runbook。

```bash
python3 scripts/check_openclaw_version.py
git diff --check
ollama ps
```

如果文档改了验证命令、依赖锁、OpenClaw/Cognee 约束或 benchmark 口径，再追加对应专项验证。

### Python 代码、脚本、schema、runner

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
git diff --check
ollama ps
```

再按触达范围追加专项测试。

### OpenClaw schema / tools / bridge

```bash
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools tests.test_openclaw_runtime_evidence
python3 scripts/check_copilot_health.py --json
```

如果验证真实 OpenClaw runtime：

```bash
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
openclaw health --json --timeout 5000
```

### 权限、状态机、审计

```bash
python3 -m unittest tests.test_copilot_permissions tests.test_copilot_governance tests.test_copilot_healthcheck
python3 scripts/check_copilot_health.py --json
```

### Feishu live sandbox / card / Bitable

```bash
python3 scripts/check_feishu_listener_singleton.py --planned-listener copilot-lark-cli
python3 -m unittest tests.test_copilot_feishu_live tests.test_feishu_interactive_cards tests.test_bitable_sync
```

如果 OpenClaw websocket 接管 bot，改用：

```bash
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
openclaw health --json --timeout 5000
```

### Cognee / embedding / retrieval

配置级验证：

```bash
python3 scripts/check_copilot_health.py --json
python3 -m unittest tests.test_copilot_cognee_adapter tests.test_copilot_retrieval
```

真实 provider 验证：

```bash
python3 scripts/check_live_embedding_gate.py --json
python3 scripts/check_embedding_provider.py
python3 scripts/spike_cognee_local.py --dry-run
ollama ps
```

如果 `ollama ps` 显示本项目模型仍在运行：

```bash
ollama stop qwen3-embedding:0.6b-fp16
```

### Benchmark / release QA

```bash
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_layer_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
```

完整 release 前再考虑：

```bash
python3 -m unittest discover tests
```

旧 legacy runner 只在触达旧 CLI / Bot / repository / historical benchmark 时运行：

```bash
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine benchmark run benchmarks/day7_anti_interference.json
```

## 上线前总验收清单

进入 productized live 前，至少要满足：

- OpenClaw first-class tool registry 已有证据。
- OpenClaw Feishu websocket `running=true`，且单监听规则通过。
- 真实飞书权限映射接入，不再只靠 demo tenant/org 常量。
- 真实飞书来源 candidate-only，不自动 active。
- confirm / reject / permission deny / ingestion / heartbeat 都有 audit record。
- storage / index / migration / backup / rollback 方案清楚。
- Cognee 主路径或 fallback 边界清楚。
- card / Bitable review surface 真实可操作，且不越权。
- release benchmark 和 no-overclaim claim audit 通过。
- README、docs、handoff、飞书看板口径一致。

## 常见停止条件

遇到下面情况要停下来写清风险，不要硬说完成：

- `openclaw health --json` 的 Feishu channel 仍是 `running=false`。
- `memory.*` 没有出现在 OpenClaw 原生工具列表。
- lark-cli / Feishu API 权限失败，无法写真实空间。
- Cognee 或 Ollama 不可用，只能走 repository fallback。
- 权限上下文缺失或畸形。
- 真实飞书 source 被撤权但系统仍返回明文 evidence。
- 测试通过但文档把 sandbox / dry-run 写成 production live。
