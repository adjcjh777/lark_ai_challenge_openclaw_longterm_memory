# 2026-04-28 Implementation Plan

阶段：L0/L1/L2/L3 数据模型和 query cascade  
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

让 Copilot Core 具备 Multi-Level Memory 的最小形态：L0 当前上下文、L1 Hot Memory、L2 Warm Memory、L3 Cold Memory，并让 search trace 能展示 query cascade。

## 必读上下文

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/2026-04-28-implementation-plan.md`
- `docs/feishu-memory-copilot-prd.md` 的 Multi-Level Memory 章节

## 用户白天主线任务

1. 在 `schemas.py` 中补 `WorkingContext`、`MemoryLayer`、`RetrievalTrace`。
2. 新增 `memory_engine/copilot/orchestrator.py`，实现 L0 -> L1 -> L2 -> L3 -> merge -> rerank -> Top K 的编排骨架。
3. 新增 `memory_engine/copilot/retrieval.py`，先提供 layer-aware search 接口。
4. 通过 adapter 或 lightweight migration 支持 `layer` 字段，不直接大改旧 repository。
5. 新增 `benchmarks/copilot_layer_cases.json` 草稿。

## 需要改/新增的文件

- `memory_engine/copilot/schemas.py`
- `memory_engine/copilot/orchestrator.py`
- `memory_engine/copilot/retrieval.py`
- `memory_engine/copilot/service.py`
- `tests/test_copilot_retrieval.py`
- `benchmarks/copilot_layer_cases.json`

## 测试

```bash
python3 -m unittest tests.test_copilot_retrieval
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

## 验收标准

- search trace 能显示至少 L1 / L2 fallback。
- L1 命中 p95 <= 100ms 的本地测试路径成型。
- L3 raw events 不直接作为默认答案。
- superseded / archived 只进入 explain 或 deep trace。

## 队友晚上补位任务

1. 给 `benchmarks/copilot_layer_cases.json` 补 15 条 layer 场景。
2. 每条用中文备注为什么属于 Hot / Warm / Cold。
3. 检查“旧版本”和“归档证据”是否不会被误写成当前答案。

今晚不用做：

- 不用实现复杂向量库。
- 不用改 Feishu Bot handler。

