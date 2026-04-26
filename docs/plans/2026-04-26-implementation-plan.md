# 2026-04-26 Implementation Plan

阶段：主控切换、Cognee memory core 选型、OpenClaw tool schema、Copilot package skeleton  
主控：`docs/feishu-memory-copilot-implementation-plan.md`  
当天目标：把执行入口从旧 Day 文档切换到 OpenClaw-native Copilot 主线，明确 Cognee 是项目 memory 系统核心，并为第一批 Copilot 代码实现准备清晰边界。

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
6. 后续如果继续执行代码，实现 OpenClaw tool schema、Cognee adapter boundary 和 Copilot package skeleton。

## 需要改/新增的文件

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/README.md`
- `docs/plans/2026-04-26-implementation-plan.md`
- `docs/archive/README.md`
- `docs/reference/README.md`
- `agent_adapters/openclaw/openclaw-version.lock`
- `scripts/check_openclaw_version.py`
- 后续代码执行时新增：`agent_adapters/openclaw/memory_tools.schema.json`
- 后续代码执行时新增：`agent_adapters/openclaw/feishu_memory_copilot.skill.md`
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
3. 你要交付：指出 3 个不清楚的任务描述，或确认没有歧义。
4. 做对的标准：非技术同学也能知道每天要交什么。
5. 遇到问题发我：发文件名和具体段落。

今晚不用做：

- 不用配置 `.env`。
- 不用跑真实飞书 Bot。
- 不用修改 `memory_engine/` 核心代码。
