# 2026-04-29 Implementation Plan

阶段：hybrid retrieval + curated memory embedding  
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

实现本地轻量 hybrid retrieval：先结构化过滤，再 keyword / FTS，再 curated memory vector similarity，最后 merge 和 rerank。只 embed curated memory，不向量化 raw events。

## 用户白天主线任务

1. 在 `retrieval.py` 中实现 scope / status / layer / type 结构化过滤。
2. 实现 keyword 或 FTS 召回，优先匹配 subject、current_value、evidence quote。
3. 新增 `embeddings.py`，实现 curated memory embedding 接口和本地轻量 fallback。
4. 实现 merge + rerank，纳入 importance、recency、confidence、version freshness、layer、evidence completeness。
5. 扩展 `benchmarks/copilot_recall_cases.json`。

## 需要改/新增的文件

- `memory_engine/copilot/retrieval.py`
- `memory_engine/copilot/embeddings.py`
- `memory_engine/copilot/schemas.py`
- `tests/test_copilot_retrieval.py`
- `benchmarks/copilot_recall_cases.json`

## 测试

```bash
python3 -m unittest tests.test_copilot_retrieval
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
```

如果 `copilot_recall_cases.json` runner 尚未实现，则先把最后一条命令标记为当天缺口，并补 runner task。

## 验收标准

- retrieval trace 能看到 structured / keyword / vector / rerank。
- 不 embed 全量 raw events。
- Recall@3 >= 60% 的第一版目标可测。
- evidence 缺失结果不能成为正式 Top 1。

## 队友晚上补位任务

1. 人工检查 recall 失败样例。
2. 按 `keyword_miss`、`vector_miss`、`wrong_subject_normalization`、`evidence_missing` 标注失败原因。
3. 把失败样例补回 benchmark 备注。

今晚不用做：

- 不用引入新依赖。
- 不用上分布式向量服务。

