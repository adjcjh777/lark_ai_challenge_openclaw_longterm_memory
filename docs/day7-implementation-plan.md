# Day 7 Implementation Plan

日期：2026-04-25  
目标日期：2026-04-30  
主题：Benchmark 扩容，抗干扰测试成型

说明：这是提前执行 D7。以当前代码库为事实源，D1/D6 文档仅作为验收标准和上下文。

## 读取范围

- `AGENTS.md`
- `docs/competition-master-execution-plan.md` 的 D7 段落
- `docs/day6-handoff.md`
- `docs/day1-handoff.md`
- `docs/day1-execution-plan.md`
- `docs/hermes-agent-reference-notes.md`
- `.reference/hermes-agent/website/docs/user-guide/features/memory.md`

Hermes 只吸收 persistent memory 与 session search 的分层机制，不复制源码，不引入 Hermes runtime。

## P0 范围

1. 扩展 benchmark runner，支持一个 benchmark spec 中批量注入：
   - curated memories
   - noise/raw events
   - recall queries
2. 新增 D7 抗干扰数据集：
   - 50 条关键记忆
   - 1000 条干扰对话
   - 50 条查询
3. 输出指标：
   - Recall@1
   - Recall@3
   - MRR
   - 平均延迟
4. 生成 `docs/benchmark-report.md` 初稿。
5. 报告解释三层数据：
   - raw events
   - curated memories
   - recall logs

## P1 加码

1. 干扰规模从 P0 的 500 条提升到 1000 条。
2. 增加按 type 和 subject 的分项指标。
3. 支持导出 CSV/JSON 机器可读结果。
4. 给 benchmark 临时库增加 FTS5 raw event 检索，用于失败样例定位；该检索只做诊断，不替代 active memory 召回。

## 预计改动

- `memory_engine/repository.py`
  - 增加 top-k recall candidates。
- `memory_engine/benchmark.py`
  - 保持 Day1 case runner 兼容。
  - 增加 D7 anti-interference benchmark spec runner。
  - 增加 Markdown/CSV/JSON 输出。
- `memory_engine/cli.py`
  - 给 `benchmark run` 增加可选输出路径。
- `benchmarks/day7_anti_interference.json`
  - 新增 D7 数据集。
- `tests/test_benchmark_day7.py`
  - 锁定 D7 三层数据、指标和输出格式。
- `docs/benchmark-report.md`
  - 生成 D7 报告初稿。
- `docs/day7-handoff.md`
  - 记录验收、验证和后续风险。

## 验收标准

- `python3 -m memory_engine benchmark run benchmarks/day7_anti_interference.json` 可一键运行。
- 输出 summary 包含 `recall_at_1`、`recall_at_3`、`mrr`、`avg_latency_ms`。
- `docs/benchmark-report.md` 有指标表和三层数据解释。
- `python3 -m compileall memory_engine scripts` 通过。
- `python3 -m memory_engine benchmark run benchmarks/day1_cases.json` 通过。
- 全量单测通过。
