# 2026-04-29 Implementation Plan

> **历史状态更新（2026-04-28）**：本文件对应的 2026-05-05 及以前任务已经完成，保留为历史计划/交接证据，不再作为后续执行入口。新的执行入口是 `docs/productization/full-copilot-next-execution-doc.md`，下一步优先 Phase A：Storage Migration + Audit Table。

阶段：hybrid retrieval、Cognee recall/search fallback、curated memory embedding
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

实现本地轻量 hybrid retrieval：先结构化过滤，再 keyword / FTS，再 curated memory vector similarity，最后 merge 和 rerank。Cognee recall/search 可以作为一个召回通道，但 provenance 不完整时必须由 Copilot 自己补 evidence；embedding 只覆盖 curated memory，不向量化 raw events。

## MemPalace 转换落点

今天只借鉴 MemPalace 的 closet 思路，不接入 MemPalace 依赖，也不新增 ChromaDB。对应转换为本项目自己的 `RecallIndexEntry`：把每条 active curated memory 压成一条短索引文本，索引文本只包含 `type`、`subject`、`current_value`、`summary` 和 `evidence.quote`，再用 `memory_id` / `evidence_id` 指回 Copilot 自己的记忆和证据。

今天要坚持两条边界：

- RecallIndex 只能作为召回和排序信号，不能挡住 repository fallback 或 Cognee 通道命中的 active memory。
- raw events、完整聊天记录、真实日志不进入 embedding；只允许通过 evidence pointer 被追溯。

## 必读上下文

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/2026-04-29-implementation-plan.md`
- `memory_engine/copilot/cognee_adapter.py`
- `memory_engine/repository.py`
- `memory_engine/benchmark.py`

## 用户白天主线任务

1. 在 `retrieval.py` 中实现 scope / status / layer / type 结构化过滤。
2. 在 `retrieval.py` 中新增 `RecallIndexEntry` 或等价内部结构，构造 `index_text` 和 evidence pointer。
3. 实现 keyword 或 FTS 召回，优先匹配 subject、current_value、summary、evidence quote。
4. 新增 `embeddings.py`，实现 curated memory embedding 接口和本地轻量 fallback。
5. 把 `CogneeAdapter.search()` 或 `recall()` 接成可选召回通道，结果统一转成 `MemoryResult`。
6. 对 Cognee 返回缺少 source/provenance 的情况，用 Copilot ledger 里的 evidence metadata 补齐。
7. 实现 merge + rerank，纳入 importance、recency、confidence、version freshness、layer、evidence completeness。
8. 扩展 `memory_engine/benchmark.py`，至少支持 `benchmarks/copilot_recall_cases.json` 的 Recall@3 和 Evidence Coverage。
9. 扩展 `benchmarks/copilot_recall_cases.json`，保持 5-10 条最小可读样例先跑通。

## 今日做到什么程度

今天结束时 retrieval 要能证明“不是把所有东西丢进向量库”：

- 检索顺序固定为 structured filter -> keyword/FTS -> vector similarity -> merge -> rerank。
- embedding 只处理 curated memory 的 `subject`、`current_value`、`summary`、`evidence.quote`。
- raw events、完整聊天记录、真实日志不进入 embedding。
- Cognee 是召回通道之一，不是 governance 和 evidence 的 source of truth。
- Recall@3 和 Evidence Coverage 至少能在本地 runner 或等价测试里计算。

## 今日执行清单（按顺序）

| 顺序 | 动作 | 文件/位置 | 做到什么程度 | 验收证据 |
|---|---|---|---|---|
| 1 | 实现结构化过滤 | `retrieval.py` | scope/status/layer/type 过滤先执行，默认 active | 单测验证 rejected/superseded 不返回 |
| 2 | 构造短索引 | `retrieval.py` | 新增 `RecallIndexEntry` 或等价结构，`index_text` 只来自 curated memory 字段 | 单测验证 raw_event 字段不参与 index |
| 3 | 实现 keyword/FTS 召回 | `retrieval.py` | 匹配 subject/current_value/summary/evidence quote，输出 `matched_via=keyword_index` | keyword 命中 case 通过 |
| 4 | 新增 embedding 接口 | `embeddings.py` | 本地轻量实现可 deterministic；字段范围写死为 curated memory | 单测验证 raw_event 字段不参与 embedding |
| 5 | 接入 Cognee 可选通道 | `cognee_adapter.py`、`retrieval.py` | Cognee 可用则纳入候选，不可用不影响 keyword fallback | fake adapter 单测覆盖 unavailable |
| 6 | evidence 补齐 | `retrieval.py`、`service.py` | 缺 evidence 的结果降权或不进正式 Top 1 | evidence_missing 测试通过 |
| 7 | merge + rerank | `retrieval.py` | 合并重复 memory，综合 importance/recency/confidence/layer/evidence，输出 `why_ranked` | trace 展示各分数来源 |
| 8 | 扩展 benchmark runner | `memory_engine/benchmark.py` | 支持 `copilot_recall_cases.json` 的 Recall@3、Evidence Coverage | 命令能输出 summary |
| 9 | 扩展 recall 样例 | `benchmarks/copilot_recall_cases.json` | 增加 keyword-only、vector-only、stale-conflict 三类样例 | benchmark 能跑或缺口写清 |

## 今日不做

- 不引入复杂向量数据库或分布式向量服务。
- 不向量化全量 raw events。
- 不为了指标临时绕过 evidence requirement。
- 不把 Cognee 返回结果未经 Copilot 统一 schema 直接给 OpenClaw。

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
- trace 能看到 `matched_via` 和 `why_ranked`，至少区分 `keyword_index`、`cognee`、`repository_fallback`。
- 不 embed 全量 raw events。
- Recall@3 >= 60% 的第一版目标可测。
- Evidence Coverage >= 80% 的统计入口成型。
- evidence 缺失结果不能成为正式 Top 1。
- Cognee 不可用时，keyword + repository fallback 仍能跑通测试。

## 我的补充任务

先看这个：

1. 今天主要把“查得到”和“能证明查得到”接起来，不要求额外安装 Cognee。
2. 人工检查 recall 失败样例，重点看问题是否像真实飞书群里的问法。
3. 按 `keyword_miss`、`vector_miss`、`wrong_subject_normalization`、`evidence_missing` 标注失败原因。
4. 把失败样例补回 benchmark 备注，每条写一句“应该命中哪条记忆”。
5. 遇到问题记录：case_id、query、期望 evidence 和实际 Top 3。

本阶段不用做：

- 不用引入新依赖。
- 不用上分布式向量服务。
- 不用把 raw events 全量做 embedding。
