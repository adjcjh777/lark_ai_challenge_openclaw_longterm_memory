# 2026-05-03 Implementation Plan

阶段：Benchmark expansion  
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

把 Copilot MVP 的 recall、candidate、conflict、layer、prefetch、heartbeat 指标纳入 benchmark runner，生成机器可读结果和评委可读报告。

## 用户白天主线任务

1. 扩展 `memory_engine/benchmark.py`，支持 `copilot_*_cases.json`。
2. 补齐 `benchmarks/copilot_recall_cases.json`、`copilot_candidate_cases.json`、`copilot_conflict_cases.json`、`copilot_layer_cases.json`、`copilot_prefetch_cases.json`、`copilot_heartbeat_cases.json`。
3. 将指标统一写入 JSON / CSV / Markdown。
4. 更新 `docs/benchmark-report.md`，突出 PRD 指标映射。
5. 记录失败分类和 recommended fix。

## 需要改/新增的文件

- `memory_engine/benchmark.py`
- `benchmarks/copilot_recall_cases.json`
- `benchmarks/copilot_candidate_cases.json`
- `benchmarks/copilot_conflict_cases.json`
- `benchmarks/copilot_layer_cases.json`
- `benchmarks/copilot_prefetch_cases.json`
- `benchmarks/copilot_heartbeat_cases.json`
- `docs/benchmark-report.md`

## 测试

```bash
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
```

## 验收标准

- Benchmark Report 包含 Recall@3、Conflict Update Accuracy、Evidence Coverage、Candidate Precision、Agent Task Context Use Rate、L1 Hot Recall p95、Sensitive Reminder Leakage Rate。
- 每个失败 case 有失败分类。
- 旧 Day1 benchmark 仍通过。

## 队友晚上补位任务

1. 人工检查 20 条失败或边界样例。
2. 把不自然的 benchmark 对话改得更像真实飞书项目群。
3. 写 Benchmark Report 的“失败分类说明”和“当前局限”草稿。

今晚不用做：

- 不用接真实飞书权限。
- 不用追求最终指标上限，先保证指标可复现。

