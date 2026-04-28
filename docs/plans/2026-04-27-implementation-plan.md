# 2026-04-27 Implementation Plan

> **历史状态更新（2026-04-28）**：本文件对应的 2026-05-05 及以前任务已经完成，保留为历史计划/交接证据，不再作为后续执行入口。新的执行入口是 `docs/productization/full-copilot-next-execution-doc.md`，下一步优先 Phase A：Storage Migration + Audit Table。

阶段：Cognee local spike、adapter contract、Copilot schemas、`memory.search` 最小 fallback
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

确认 Cognee 在本机的最小可跑路径，并把它封装在 `CogneeAdapter` 后面；同时定义 Copilot-owned schema，让 `memory.search` 的最小 fallback 路径能返回 Top K active memory with evidence。今天不追求完整 hybrid retrieval，重点是“接口稳定、可调试、可 fallback”。

## 必读上下文

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/2026-04-27-implementation-plan.md`
- `docs/feishu-memory-copilot-prd.md`
- 旧 repository fallback：`memory_engine/repository.py`
- 旧基线测试：`benchmarks/day1_cases.json`
- Cognee 官方安装和本地配置文档

## 用户白天主线任务

1. 新增 `memory_engine/copilot/schemas.py`，定义 `Evidence`、`MemoryResult`、`CandidateMemory`、`RecallTrace`、`ToolError`、search input/output。
2. 新增 `scripts/spike_cognee_local.py`，支持真实 Cognee SDK 闭环和 `--dry-run` 两种模式。
3. 在 `.gitignore` 中确保 `.data/` 或 `.data/cognee/` 不进入提交。
4. 新增 `memory_engine/copilot/cognee_adapter.py`，定义窄接口：`add_raw_event`、`cognify_scope`、`remember_candidate_text`、`recall`、`search`、`delete_scope(dry_run=True)`。
5. 新增 `tests/test_copilot_cognee_adapter.py`，用 fake adapter 锁住 dataset 命名、evidence metadata、不可用 fallback、状态不被 Cognee 改写。
6. 新增 `memory_engine/copilot/permissions.py`，先实现同 scope 访问的最小校验和错误格式。
7. 新增 `memory_engine/copilot/service.py` 和 `tools.py`，让 `memory.search` 第一版复用旧 `MemoryRepository.recall_candidates()`，但不把业务逻辑写进 CLI 或 Feishu handler。
8. 创建或补充 `agent_adapters/openclaw/memory_tools.schema.json`，至少覆盖 `memory.search` 和统一错误格式。

## 今日做到什么程度

今天结束时必须有一条“能 import、能 dry-run、能用旧 repository fallback 查 active memory”的最小链路：

- `memory_engine/copilot/` 目录存在，schema、adapter、service、tools 都能被 Python import。
- Cognee 是否真实可用要有结论：真实跑通、dry-run 跑通、或 blocked 原因写在命令输出/文档里。
- `memory.search` 的工具契约不再停留在口头：schema 文件至少有 search 输入、输出和统一错误格式。
- `CopilotService.search()` 可以先走旧 repository fallback，但输出必须是 Copilot-owned schema。
- 今天不追求召回效果，只锁接口、错误格式、evidence 字段和 fallback 行为。

## 今日执行清单（按顺序）

| 顺序 | 动作 | 文件/位置 | 做到什么程度 | 验收证据 |
|---|---|---|---|---|
| 1 | 创建 Copilot 包骨架 | `memory_engine/copilot/__init__.py` | 包可 import，不暴露旧 CLI 逻辑 | `python3 -m compileall memory_engine scripts` 通过 |
| 2 | 定义核心 schema | `schemas.py` | 至少覆盖 `Evidence`、`MemoryResult`、`CandidateMemory`、`RecallTrace`、`ToolError`、search request/response | `tests/test_copilot_schemas.py` 通过 |
| 3 | 写 Cognee spike | `scripts/spike_cognee_local.py` | `--dry-run` 必须可跑；真实 SDK 可用则跑真实闭环 | dry-run 输出明确 `ok/dry_run/blocked` |
| 4 | 锁 Cognee adapter 边界 | `cognee_adapter.py` | 只有 adapter 文件允许直接接触 Cognee；返回 Copilot schema，不返回 Cognee 原始对象 | `tests/test_copilot_cognee_adapter.py` fake adapter 通过 |
| 5 | 写权限最小门控 | `permissions.py` | 缺 scope、scope 不匹配时返回统一错误 | `tests/test_copilot_tools.py` 覆盖错误格式 |
| 6 | 实现 search fallback | `service.py`、`tools.py` | `memory.search` 可调用旧 repository fallback，默认只查 active | 工具测试能拿到 Top K with evidence |
| 7 | 冻结 search schema | `agent_adapters/openclaw/memory_tools.schema.json` | 至少包含 `memory.search` 输入/输出/error 结构 | JSON 可解析，字段名和 `tools.py` 对齐 |
| 8 | 保持旧基线 | benchmark | 不破坏 Day1 本地 memory 闭环 | `day1_cases.json` pass rate 仍为 1.0 |

## 今日不做

- 不实现 L0/L1/L2/L3 完整 cascade。
- 不实现 hybrid retrieval 和 embedding。
- 不让业务代码直接 `import cognee`。
- 不接真实 Feishu Bot、Bitable 或 OpenClaw gateway。

## 需要改/新增的文件

- `.gitignore`
- `agent_adapters/openclaw/memory_tools.schema.json`
- `memory_engine/copilot/__init__.py`
- `memory_engine/copilot/schemas.py`
- `memory_engine/copilot/cognee_adapter.py`
- `memory_engine/copilot/service.py`
- `memory_engine/copilot/tools.py`
- `memory_engine/copilot/permissions.py`
- `scripts/spike_cognee_local.py`
- `tests/test_copilot_schemas.py`
- `tests/test_copilot_tools.py`
- `tests/test_copilot_cognee_adapter.py`

## 测试

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/spike_cognee_local.py --dry-run
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools tests.test_copilot_cognee_adapter
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

如果 Cognee 已安装并配置本地 provider，再追加：

```bash
python3 scripts/spike_cognee_local.py
```

## 验收标准

- `scripts/spike_cognee_local.py` 能清楚输出真实跑通、dry-run 或 blocked 的状态。
- Cognee 本地数据目录固定在项目内 `.data/cognee/`，不会污染系统环境，也不会进入提交。
- `CogneeAdapter` 是唯一直接接触 Cognee 的文件；`service.py` 不直接 `import cognee`。
- Adapter contract tests 覆盖 evidence metadata、dataset/scope 映射、fallback 和 dry-run。
- `memory.search` 对 active memory 返回 Top K 结果。
- 每条结果包含 `memory_id`、`type`、`subject`、`current_value`、`status`、`version`、`score`、`evidence`。
- 缺 scope、无结果、权限不足时返回统一错误结构。
- 默认不返回 candidate / rejected / superseded。

## 执行记录：Cognee / RightCode 中间结论

- 已安装并锁定 `cognee==0.1.20`；为兼容该版本依赖的 OpenAI SDK/httpx 调用形态，额外锁定 `httpx==0.27.2`，避免 `httpx 0.28.x` 的 `proxies` 参数不兼容问题。
- `scripts/spike_cognee_local.py --dry-run` 已跑通；Cognee 本地数据目录固定在项目内 `.data/cognee/`，由 `.gitignore` 排除。
- RightCode custom provider 的文本模型通路可用：使用 `gpt-5.3-codex-high` 发起最小 chat completion 可以返回 `ok`。
- 初次真实 SDK 路径曾是“部分跑通”：`add` 阶段成功，`cognify` 阶段进入 LiteLLM embedding 调用后被 RightCode embedding provider 阻断，`search` 因 `cognify` 未完成被跳过。
- 直接调用 RightCode `/embeddings` 的 `text-embedding-3-large` 也返回 `PermissionDeniedError: Your request was blocked.`，因此当时 blocker 是 embedding provider 不可用，不是本地 adapter、数据目录或 OpenClaw 版本问题。
- 该 blocker 已由后续“本地 embedding 方案”解除：默认使用 Ollama `qwen3-embedding:0.6b-fp16`，并已复测 Cognee 真实 `add -> cognify -> search` 三阶段闭环。
- MVP 的 `memory.search` 仍保持旧 repository fallback；Cognee 继续只通过 `CogneeAdapter` 窄边界接入，避免产品代码直接依赖 Cognee 原始对象。

## 执行记录：本地 embedding 方案

- 参考 MTEB / C-MTEB 分数和 Ollama 包体后，默认 embedding 从备选 `bge-m3:567m` 调整为 `qwen3-embedding:0.6b-fp16`。
- 选择原因：`qwen3-embedding:0.6b-fp16` 为 1024 维，官方 Ollama 包体约 1.2GB，适合 16GB Mac mini；Qwen3-Embedding 模型卡列出的 multilingual MTEB 为 64.33、C-MTEB 为 66.33，高于同体量 BGE-M3 的 multilingual MTEB 59.56。
- `qwen3-embedding:4b-fp16` 虽然质量更高，但官方 Ollama F16 包体约 8GB；考虑 Cognee 批处理和 Windows 备用环境复现稳定性，暂不作为默认。
- 已新增 `memory_engine/copilot/embedding-provider.lock` 锁定 provider、model、endpoint、dimensions，并新增 `.env.example`、`scripts/check_embedding_provider.py`、Windows/macOS Ollama setup 脚本和本地复现文档。
- 切换 embedding 维度后，旧 `.data/cognee/` 里可能残留 3072 维 LanceDB schema；`scripts/spike_cognee_local.py --reset-local-data` 用于安全删除项目内 `.data/cognee/` 后重建本地 Cognee 数据。
- 本机已验证 `ollama pull qwen3-embedding:0.6b-fp16`、`python3 scripts/check_embedding_provider.py`、以及 `RightCode gpt-5.3-codex-high + Ollama qwen3-embedding:0.6b-fp16` 的 Cognee 真实 `add -> cognify -> search` 三阶段闭环。

## 我的补充任务

先看这个：

1. 今天会先验证 Cognee（本地记忆引擎）能不能在本机最小跑通；如果没装好，也要有 dry-run 输出说明原因。
2. 我需要准备 10 条真实项目协作问题，写入 `benchmarks/copilot_recall_cases.json` 草稿。
3. 每条问题写清正确答案、应该出现的来源证据关键词，以及为什么这是项目长期记忆。
4. 检查 `scripts/spike_cognee_local.py` 输出说明是否能看出“真实跑通 / dry-run / blocked”的区别。
5. 遇到问题记录：具体 case_id、问题句子和不清楚的字段。

本阶段不用做：

- 不用配置真实 OpenClaw runtime。
- 不用接真实飞书权限。
- 不用改旧 `memory_engine/repository.py`。
