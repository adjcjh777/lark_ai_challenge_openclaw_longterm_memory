# 2026-04-26 Implementation Plan

阶段：主控切换、P0/P1 调研落盘、OpenClaw tool schema、Copilot package skeleton
主控：`docs/feishu-memory-copilot-implementation-plan.md`  
当天目标：把执行入口从旧 Day 文档切换到 OpenClaw-native Copilot 主线，把正式写代码前的技术调研结论写入总控和后续日期计划，并为第一批 Copilot 代码实现准备清晰边界。

## OpenClaw 版本基线

- 今日已将 OpenClaw CLI 升级并固定为 `2026.4.24`。
- 锁文件：`agent_adapters/openclaw/openclaw-version.lock`。
- 今日及后续 OpenClaw schema、skill、examples、demo flow 都基于该版本，不再跟随 npm `latest` 自动升级。
- 开始 OpenClaw 相关开发前先运行：`python3 scripts/check_openclaw_version.py`。

## 必读上下文

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/feishu-memory-copilot-prd.md`
- `docs/copilot-product-question-log.md`
- `agent_adapters/openclaw/openclaw-version.lock`
- Cognee 官方文档：`https://docs.cognee.ai/core-concepts/overview`
- 当前仓库结构：`memory_engine/`、`benchmarks/`、`tests/`、`docs/`

## 用户白天主线任务

1. 更新 `AGENTS.md`，明确新主控是 `docs/feishu-memory-copilot-implementation-plan.md`，旧主控只作归档参考。
2. 整理 docs 结构：旧 `dayN` 文档归档到 `docs/archive/legacy-day-docs/`，长期参考资料移动到 `docs/reference/`。
3. 创建 `docs/plans/` 并生成 2026-04-26 至 2026-05-07 的每日 implementation plan。
4. 升级并锁定 OpenClaw CLI 到 `2026.4.24`，确保后续开发版本不漂移。
5. 明确 Cognee 是 memory 系统核心，但企业记忆状态机、证据链、OpenClaw tools、Feishu card 和 Benchmark 仍由本项目实现。
6. 把正式写代码前的调研结论转成执行队列，写入总控计划和后续每日计划。
7. 如果继续执行代码，优先实现 OpenClaw tool schema、Cognee adapter boundary 和 Copilot package skeleton。

## 今日做到什么程度

今天结束时必须达到“可以从明天直接写代码”的状态，而不是只完成方向讨论：

- 执行入口已切换：新对话默认读 `AGENTS.md`、主控 implementation plan、当天绝对日期计划。
- OpenClaw 版本已固定：本机版本、锁文件、检查脚本和 AGENTS 规则一致。
- 每日计划已细化：2026-04-26 至 2026-05-07 每天都能看出“做什么、改哪些文件、做到什么程度、怎么验收”。
- D1 代码任务已定义清楚：若继续执行代码，只做 OpenClaw schema、skill examples、Copilot package skeleton，不进入旧 Bot handler 大改。
- 队友晚上能接手检查计划，不需要理解所有底层实现。

## 今日执行清单（按顺序）

| 顺序 | 动作 | 文件/位置 | 做到什么程度 | 验收证据 |
|---|---|---|---|---|
| 1 | 确认执行契约 | `AGENTS.md` | 新主控、OpenClaw-first、Cognee 边界、版本锁定都写清楚 | `rg "主控|OpenClaw 版本锁定|Cognee" AGENTS.md` 有结果 |
| 2 | 固定 OpenClaw 版本 | `agent_adapters/openclaw/openclaw-version.lock`、`scripts/check_openclaw_version.py` | 锁定 `2026.4.24`，后续禁止自动跟随 latest | `python3 scripts/check_openclaw_version.py` 通过 |
| 3 | 细化总控计划 | `docs/feishu-memory-copilot-implementation-plan.md` | 明确 2026-04-26 至 2026-05-02 MVP，2026-05-03 至 2026-05-07 收尾 | 文档包含每日排期、模块边界、测试/benchmark |
| 4 | 细化每日计划 | `docs/plans/*.md` | 每天有完成定义、文件级任务、验收标准、队友补位任务 | `docs/plans/README.md` 索引能找到每一天 |
| 5 | 明确 D1 代码边界 | `2026-04-26-implementation-plan.md` | 只准备 schema/skeleton，不实现完整 retrieval/governance | 文档写明“后续代码执行时新增”的文件和范围 |
| 6 | 保留旧资产 | `docs/archive/`、`docs/reference/` | 旧 day 文档和参考资料不删除、不作为主控 | 目录存在，README 说明用途 |
| 7 | 基础验证 | 本地命令 | 文档改动不破坏旧可复现基线 | compileall 和 day1 benchmark 通过 |
| 8 | 提交推送 | Git | 关键执行契约进入远程仓库 | `git log -1 --oneline` 可见本次提交 |

## 今日不做

- 不实现完整 `memory.search`、retrieval、governance、heartbeat。
- 不大改 `memory_engine/repository.py`、`memory_engine/feishu_runtime.py` 或旧 CLI。
- 不把真实飞书 Bot / Bitable / OpenClaw gateway 作为今日阻塞。
- 不引入新依赖；Cognee 真实安装和 adapter contract 放到 2026-04-27。

## 调研落盘任务

本节把“最高优先级”和“下一优先级前两项”调研转成后续计划，避免只停留在聊天记录里。

| 任务 | 安排到 | 说明 |
|---|---|---|
| Cognee 本地最小可跑 spike | 2026-04-27 | 先走 Python SDK，本地 `.data/cognee/`，不先起 server / Docker |
| Cognee adapter contract | 2026-04-27 | 只允许 `cognee_adapter.py` 直接接触 Cognee |
| OpenClaw schema + examples | 2026-04-26 至 2026-05-02 | runtime 不稳时用 examples + CLI/dry-run 证明工具契约 |
| 旧模块复用映射 | 2026-04-27 至 2026-05-02 | repository 是 ledger/fallback，card/Bitable 是 review surface |
| Benchmark 指标和样例集 | 2026-04-27 至 2026-05-03 | 先 recall/candidate/conflict，再补 layer/prefetch/heartbeat |
| Feishu Card / Bitable 审核流 | 2026-05-01 至 2026-05-03 | 展示 evidence、版本链、candidate review、reminder candidate |

## 需要改/新增的文件

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/README.md`
- `docs/plans/2026-04-26-implementation-plan.md`
- 后续日期计划：`docs/plans/2026-04-27-implementation-plan.md` 至 `docs/plans/2026-05-07-implementation-plan.md`
- `docs/archive/README.md`
- `docs/reference/README.md`
- `agent_adapters/openclaw/openclaw-version.lock`
- `scripts/check_openclaw_version.py`
- 后续代码执行时新增：`agent_adapters/openclaw/memory_tools.schema.json`
- 后续代码执行时新增：`agent_adapters/openclaw/feishu_memory_copilot.skill.md`
- 后续代码执行时新增：`agent_adapters/openclaw/examples/*.json`
- 后续代码执行时新增：`scripts/spike_cognee_local.py`
- 后续代码执行时新增：`memory_engine/copilot/__init__.py`
- 后续代码执行时新增：`memory_engine/copilot/schemas.py`
- 后续代码执行时新增：`memory_engine/copilot/cognee_adapter.py`
- 后续代码执行时新增：`memory_engine/copilot/tools.py`
- 后续代码执行时新增：`tests/test_copilot_schemas.py`

## 测试

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

如果开始写 Copilot skeleton，再追加：

```bash
python3 -m unittest tests.test_copilot_schemas
```

## 验收标准

- `AGENTS.md` 不再把旧 `competition-master-execution-plan.md` 作为默认主控。
- 总控计划包含调研转执行任务总表。
- 后续每日计划能看出 Cognee spike、adapter contract、OpenClaw schema/examples、benchmark 样例、Card/Bitable review 的落地日期。
- 文档明确 Cognee 是 memory 系统核心，且 Cognee 只承担本地开源知识/记忆引擎能力。
- 文档明确 Copilot 自研层仍负责 candidate/active/superseded 状态机、evidence、versions、permissions、OpenClaw tools、Feishu review surface 和 Benchmark。
- 新日期计划全部使用 `YYYY-MM-DD-implementation-plan.md` 命名。
- 旧文档被归档但未删除，后续仍可按需查阅。
- `python3 scripts/check_openclaw_version.py` 输出 `OpenClaw version OK: 2026.4.24`。
- 基础验证命令通过。

## 队友晚上补位任务

给队友先看这个：

1. 今天主要完成主控切换和计划拆分，不要求你改核心代码。
2. 你从 `docs/plans/README.md` 开始看，确认每天任务是否能看懂。
3. 你重点看 `docs/plans/2026-04-27-implementation-plan.md` 和 `docs/plans/2026-04-28-implementation-plan.md`，确认明后两天能从哪里开始。
4. 你要交付：指出 3 个不清楚的任务描述，或确认没有歧义。
5. 做对的标准：非技术同学也能知道每天要交什么；遇到问题发我文件名和具体段落。

今晚不用做：

- 不用配置 `.env`。
- 不用安装 Cognee。
- 不用跑真实飞书 Bot。
- 不用修改 `memory_engine/` 核心代码。
