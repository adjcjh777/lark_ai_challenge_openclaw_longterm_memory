# 2026-04-29 Implementation Plan

阶段：hybrid retrieval、Cognee recall/search fallback、curated memory embedding
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

实现本地轻量 hybrid retrieval：先结构化过滤，再 keyword / FTS，再 curated memory vector similarity，最后 merge 和 rerank。Cognee recall/search 可以作为一个召回通道，但 provenance 不完整时必须由 Copilot 自己补 evidence；embedding 只覆盖 curated memory，不向量化 raw events。

## 必读上下文

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/2026-04-29-implementation-plan.md`
- `memory_engine/copilot/cognee_adapter.py`
- `memory_engine/repository.py`
- `memory_engine/benchmark.py`

## 用户白天主线任务

1. 在 `retrieval.py` 中实现 scope / status / layer / type 结构化过滤。
2. 实现 keyword 或 FTS 召回，优先匹配 subject、current_value、summary、evidence quote。
3. 新增 `embeddings.py`，实现 curated memory embedding 接口和本地轻量 fallback。
4. 把 `CogneeAdapter.search()` 或 `recall()` 接成可选召回通道，结果统一转成 `MemoryResult`。
5. 对 Cognee 返回缺少 source/provenance 的情况，用 Copilot ledger 里的 evidence metadata 补齐。
6. 实现 merge + rerank，纳入 importance、recency、confidence、version freshness、layer、evidence completeness。
7. 扩展 `memory_engine/benchmark.py`，至少支持 `benchmarks/copilot_recall_cases.json` 的 Recall@3 和 Evidence Coverage。
8. 扩展 `benchmarks/copilot_recall_cases.json`，保持 5-10 条最小可读样例先跑通。

## 需要改/新增的文件

- `memory_engine/copilot/retrieval.py`
- `memory_engine/copilot/embeddings.py`
- `memory_engine/copilot/cognee_adapter.py`
- `memory_engine/copilot/schemas.py`
- `memory_engine/benchmark.py`
- `tests/test_copilot_retrieval.py`
- `tests/test_copilot_cognee_adapter.py`
- `benchmarks/copilot_recall_cases.json`

## 测试

```bash
python3 scripts/check_openclaw_version.py
python3 -m unittest tests.test_copilot_retrieval
python3 -m unittest tests.test_copilot_cognee_adapter
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
```

如果 `copilot_recall_cases.json` runner 尚未实现，则先把最后一条命令标记为当天缺口，并补 runner task，不要假装已验证 Recall@3。

## 验收标准

- retrieval trace 能看到 structured / keyword / vector / cognee / rerank。
- 不 embed 全量 raw events。
- Recall@3 >= 60% 的第一版目标可测。
- Evidence Coverage >= 80% 的统计入口成型。
- evidence 缺失结果不能成为正式 Top 1。
- Cognee 不可用时，keyword + repository fallback 仍能跑通测试。

## 队友晚上补位任务

给队友先看这个：

1. 今天主要把“查得到”和“能证明查得到”接起来，不要求你安装 Cognee。
2. 人工检查 recall 失败样例，重点看问题是否像真实飞书群里的问法。
3. 按 `keyword_miss`、`vector_miss`、`wrong_subject_normalization`、`evidence_missing` 标注失败原因。
4. 把失败样例补回 benchmark 备注，每条写一句“应该命中哪条记忆”。
5. 遇到问题发我：case_id、query、期望 evidence 和实际 Top 3。

今晚不用做：

- 不用引入新依赖。
- 不用上分布式向量服务。
- 不用把 raw events 全量做 embedding。
