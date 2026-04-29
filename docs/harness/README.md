# Agent Harness

日期：2026-04-29  
参考：OpenAI《Harness engineering for building reliable agents》。

## 1. 这次重构要解决什么

这个仓库已经有很多 Copilot 能力、测试、handoff 和 productization 文档。问题不是“缺少文字”，而是代理执行时容易被过长入口、历史计划、旧 Bot fallback 和新产品化主线混在一起。

Harness engineering 在本项目里的含义是：把仓库改造成代理可读、可执行、可验证的工作环境。入口要短，事实源要清楚，约束要能被脚本检查，长期技术债要定期清理。

## 2. 本仓库采用的 harness 原则

| 原则 | 本项目落点 | 检查方式 |
|---|---|---|
| Map, not manual | `AGENTS.md` 只保留入口地图；详细规则沉到 `docs/productization/agent-execution-contract.md` | `scripts/check_agent_harness.py` 检查行数和必需入口 |
| Docs as system of record | 产品化状态、边界、handoff、contracts 写入 `docs/productization/` | 本文列出 facts、contracts、runbooks 的读取顺序 |
| Custom lints and structural tests | 用仓库脚本检查 agent harness，而不是只靠口头约定 | `tests/test_agent_harness.py` 和 `scripts/check_agent_harness.py` |
| Keep the agent in the local loop | 所有改动都要有本地命令验证；不要只写计划 | `AGENTS.md` 和 execution contract 的验证矩阵 |
| Garbage collect technical debt | 技术债有专门清单和停用规则，不让旧路径继续抢主线 | `docs/harness/TECH_DEBT_GARBAGE_COLLECTION.md` |
| Quality score, not vibes | 用固定维度记录当前 harness 成熟度 | `docs/harness/QUALITY_SCORE.md` |

## 3. 必读索引

执行代理读取顺序：

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

产品化 / 交付物任务追加：

```text
docs/README.md
docs/human-product-guide.md
docs/productization/workflow-and-test-process.md
docs/productization/launch-polish-todo.md
docs/productization/contracts/
```

## 4. 结构约束

当前主线仍是：

```text
OpenClaw-native Feishu Memory Copilot
```

新增能力优先进入：

```text
memory_engine/copilot/
agent_adapters/openclaw/
docs/productization/
tests/test_copilot_*.py
benchmarks/copilot_*.json
```

不要把新能力继续塞进旧 Bot handler。旧 CLI / Bot / day benchmark 只作为 fallback 或 reference。

## 5. 本地 harness 检查

每次改 agent harness、执行契约、OpenClaw/Cognee 规则、目录边界或验证口径时运行：

```bash
python3 scripts/check_agent_harness.py
python3 -m unittest tests.test_agent_harness
```

提交前仍要跑：

```bash
python3 scripts/check_openclaw_version.py
git diff --check
```

## 6. 本阶段不做

本阶段不用把所有业务代码重写成新框架，也不把项目改成另一个 memory substrate。本阶段先完成 harness 底座：短入口、详细 contract、结构检查、质量分数、技术债回收清单。后续每一轮再按这个 harness 做更深的代码层重构。
