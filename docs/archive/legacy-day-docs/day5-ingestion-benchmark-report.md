# Day 5 Ingestion Benchmark Report

日期：2026-04-28

## 目标

验证文档 ingestion 不只是能读取文档，还能从含干扰信息的文档中抽取候选记忆，并在人工确认后保留文档证据链。

## 数据集

Benchmark 文件：`benchmarks/day5_ingestion_cases.json`

输入文档：

- `docs/archive/legacy-day-docs/demo-docs/day5-architecture-decisions.md`
- `docs/archive/legacy-day-docs/demo-docs/day5-weekly-meeting-notes.md`

每份文档包含：

- 5 条可抽取记忆。
- 15 条干扰信息。
- 1 条确认后召回验证。

## 指标

| 指标 | 含义 |
|---|---|
| `candidate_count` | 每份文档抽出的候选记忆数量 |
| `quote_coverage` | 期望 quote 被候选覆盖的比例 |
| `noise_rejection_rate` | 明确干扰 quote 未被抽取的比例 |
| `document_evidence_coverage` | 确认后召回结果是否包含文档标题和 quote |
| `case_pass_rate` | 文档 case 通过率 |

## 运行命令

```bash
python3 -m memory_engine benchmark ingest-doc benchmarks/day5_ingestion_cases.json
```

## 最新结果

```text
case_count = 2
case_pass_rate = 1.0
avg_candidate_count = 5.0
avg_quote_coverage = 1.0
avg_noise_rejection_rate = 1.0
document_evidence_coverage = 1.0
avg_ingestion_latency_ms ~= 3 ms
```

## 结论

Day5 文档 ingestion 已具备初赛所需的自证能力：

- 能从文档或 Markdown 中抽取至少 5 条候选记忆。
- 能拒绝显式干扰信息。
- 候选默认不进入 recall，必须先确认。
- 确认后 recall 能说明来源是文档，并展示原文 quote。

## 剩余风险

- 当前抽取是启发式规则，适合 Demo 和初赛最小闭环；复杂真实文档仍需要人工确认兜底。
- 真实飞书文档创建偶发返回下游错误，重试可恢复；演示时保留 Markdown fallback。
