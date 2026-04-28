# 2026-04-28 Implementation Plan

> **历史状态更新（2026-04-28）**：本文件对应的 2026-05-05 及以前任务已经完成，保留为历史计划/交接证据，不再作为后续执行入口。新的执行入口是 `docs/productization/full-copilot-next-execution-doc.md`，下一步优先 Phase A：Storage Migration + Audit Table。

阶段：`memory.search` service contract、L0/L1/L2/L3 数据模型和 query cascade
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

让 Copilot Core 具备第一条完整 search contract：OpenClaw 工具输入进入 `tools.py`，再到 `CopilotService.search()`，再由 orchestrator 决定 L0 -> L1 -> L2 -> L3 的最小召回顺序。今天重点是 trace、状态过滤和 fallback 路径，不做复杂向量效果冲刺。

## 必读上下文

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/2026-04-28-implementation-plan.md`
- `docs/plans/2026-04-27-handoff.md`
- `docs/feishu-memory-copilot-prd.md` 的 Multi-Level Memory 章节
- `memory_engine/copilot/cognee_adapter.py`
- `memory_engine/repository.py`

## 前置状态

2026-04-26 和 2026-04-27 已完成 OpenClaw schema、Copilot skeleton、Cognee adapter contract、`memory.search` repository fallback、Cognee local spike、RightCode 文本模型验证和本地 Ollama embedding 基线。进入今天任务时，应先把这些作为已完成前提，不要重新选型或重做旧 Bot 主线。

## 用户白天主线任务

1. 在 `schemas.py` 中补 `WorkingContext`、`MemoryLayer`、`RetrievalTrace`。
2. 完整实现 `CopilotService.search()` 和 `tools.memory_search()`，保持工具层只是薄封装。
3. 新增 `memory_engine/copilot/orchestrator.py`，实现 L0 -> L1 -> L2 -> L3 -> merge -> rerank -> Top K 的编排骨架。
4. 新增 `memory_engine/copilot/retrieval.py`，先提供 layer-aware search 接口。
5. 通过 adapter 或 lightweight migration 支持 `layer` 字段，不直接大改旧 repository。
6. 让 search trace 显示 backend：`cognee`、`repository_fallback` 或 `dry_run`。
7. 新增 `benchmarks/copilot_recall_cases.json` 和 `benchmarks/copilot_layer_cases.json` 草稿。

## 今日做到什么程度

今天结束时 `memory.search` 要从“能查”变成“能解释怎么查”：

- OpenClaw tool request 进入 `tools.py` 后，只做校验和错误包装，核心逻辑在 `CopilotService.search()`。
- search trace 至少能描述 L0、L1、L2、L3 哪些层被查过，哪些层命中，最终为什么选 Top K。
- 默认 search 只返回 active；superseded、archived、raw events 不作为当前答案。
- L1 hot set 可以先用单机结构或 SQLite 标记，不需要复杂缓存。
- benchmark 样例先少而精，至少能覆盖 active、旧版本、不同 layer 三类行为。

## 今日执行清单（按顺序）

| 顺序 | 动作 | 文件/位置 | 做到什么程度 | 验收证据 |
|---|---|---|---|---|
| 1 | 扩展上下文 schema | `schemas.py` | 增加 `WorkingContext`、`MemoryLayer`、`RetrievalTrace`，字段含 session/chat/task/scope | schema 单测覆盖必填和默认值 |
| 2 | 薄化工具层 | `tools.py` | `memory_search()` 只做参数校验、调用 service、包装 error | tools 单测验证 service 可替换 |
| 3 | 完整 service contract | `service.py` | `search()` 接收 query/scope/top_k/filters/current_context，返回统一 response | `tests/test_copilot_tools.py` 覆盖成功和错误 |
| 4 | 新增 orchestrator | `orchestrator.py` | 编排 L0 -> L1 -> L2 -> L3 -> merge -> rerank -> Top K 的骨架 | trace 中能看到每层步骤 |
| 5 | 新增 retrieval facade | `retrieval.py` | 提供 layer-aware search 接口，内部可先走 repository fallback | `tests/test_copilot_retrieval.py` 通过 |
| 6 | 处理状态过滤 | `retrieval.py` | 默认 `status=active`，只有 explain/deep trace 能看旧值 | stale/superseded 不泄漏测试通过 |
| 7 | 建最小 benchmark | `copilot_recall_cases.json`、`copilot_layer_cases.json` | recall 至少 5 条，layer 至少覆盖 L1/L2/L3 各 1 条 | JSON 可被 runner 或人工校验读取 |
| 8 | 延迟风险记录 | 当日 plan 或 handoff | 如果 layer 字段只能 adapter 模拟，写清不改旧 repository 的原因 | final/handoff 记录缺口 |

## 今日不做

- 不做复杂向量召回效果优化。
- 不把 raw events 加入默认 search。
- 不为 L1 引入分布式缓存。
- 不迁移旧 repository schema 的大结构。

## 需要改/新增的文件

- `memory_engine/copilot/schemas.py`
- `memory_engine/copilot/service.py`
- `memory_engine/copilot/tools.py`
- `memory_engine/copilot/orchestrator.py`
- `memory_engine/copilot/retrieval.py`
- `memory_engine/copilot/permissions.py`
- `tests/test_copilot_tools.py`
- `tests/test_copilot_retrieval.py`
- `benchmarks/copilot_recall_cases.json`
- `benchmarks/copilot_layer_cases.json`

## 测试

```bash
python3 scripts/check_openclaw_version.py
python3 -m unittest tests.test_copilot_tools tests.test_copilot_retrieval
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

如果 `copilot_recall_cases.json` runner 已实现，再追加：

```bash
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
```

## 验收标准

- `memory.search` 输出包含 `memory_id`、`type`、`subject`、`current_value`、`status`、`version`、`score`、`evidence`、`trace`。
- search trace 能显示至少 L1 / L2 fallback。
- L1 命中 p95 <= 100ms 的本地测试路径成型。
- L3 raw events 不直接作为默认答案。
- superseded / archived 只进入 explain 或 deep trace。
- `benchmarks/copilot_recall_cases.json` 至少有 5 条可读样例。

## 我的补充任务

先看这个：

1. 今天主要让“查询历史决策”这条工具链完整走通。
2. 我需要给 `benchmarks/copilot_layer_cases.json` 补 15 条分层场景：常用规则、最近讨论、旧版本、归档证据。
3. 每条用中文备注为什么属于 Hot / Warm / Cold。Hot 是最常用的记忆，Warm 是最近或待处理记忆，Cold 是历史或归档证据。
4. 顺手检查 `copilot_recall_cases.json` 是否像真实飞书项目群问题。
5. 遇到问题记录：case_id、应该命中的记忆、实际看起来可能命中的记忆。

本阶段不用做：

- 不用实现复杂向量库。
- 不用改 Feishu Bot handler。
- 不用做完整权限后台。
