# 2026-05-03 Implementation Plan

阶段：Benchmark expansion、metrics report、review surface evidence check
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

把 Copilot MVP 的 recall、candidate、conflict、layer、prefetch、heartbeat 指标纳入 benchmark runner，生成机器可读结果和评委可读报告。今天不追求指标冲高，先保证 PRD 里的每个指标都有计算入口、输入字段、输出字段和失败分类。

## 必读上下文

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/2026-05-03-implementation-plan.md`
- `docs/feishu-memory-copilot-prd.md` 的指标章节
- `memory_engine/benchmark.py`
- `memory_engine/bitable_sync.py`

## 用户白天主线任务

1. 扩展 `memory_engine/benchmark.py`，支持 `copilot_*_cases.json`。
2. 补齐 `benchmarks/copilot_recall_cases.json`、`copilot_candidate_cases.json`、`copilot_conflict_cases.json`、`copilot_layer_cases.json`、`copilot_prefetch_cases.json`、`copilot_heartbeat_cases.json`。
3. 每个样例集至少保留 5-10 条最小高质量样例，再逐步扩展。
4. 将指标统一写入 JSON / CSV / Markdown。
5. 更新 `docs/benchmark-report.md`，突出 PRD 指标映射和 demo 证据。
6. 记录失败分类和 recommended fix。
7. 确认 Bitable Benchmark Results dry-run 字段能承载这些指标，不要求真实写入。

## 指标计算任务

| 指标 | 当日计算入口 |
|---|---|
| Recall@3 | `copilot_recall_cases.json` 的 expected memory 是否出现在 Top 3 |
| Conflict Update Accuracy | `copilot_conflict_cases.json` 的旧值是否 superseded、新值是否 active |
| Evidence Coverage | recall / candidate / conflict 输出中带 evidence 的比例 |
| Candidate Precision | 被识别为 candidate 的样例里 true positive 占比 |
| Agent Task Context Use Rate | prefetch context pack 是否被后续 agent output 引用或命中 required_context |
| L1 Hot Recall p95 | `copilot_layer_cases.json` 中 L1 查询延迟 p95 |
| Sensitive Reminder Leakage Rate | reminder 输出中泄漏 sensitive 标记内容的比例，目标 0 |
| Stale Leakage Rate | 默认 search / prefetch 中把 stale 或 superseded 当当前值返回的比例 |

## 需要改/新增的文件

- `memory_engine/benchmark.py`
- `benchmarks/copilot_recall_cases.json`
- `benchmarks/copilot_candidate_cases.json`
- `benchmarks/copilot_conflict_cases.json`
- `benchmarks/copilot_layer_cases.json`
- `benchmarks/copilot_prefetch_cases.json`
- `benchmarks/copilot_heartbeat_cases.json`
- `docs/benchmark-report.md`
- `memory_engine/bitable_sync.py`，如 Benchmark Results 字段缺指标

## 测试

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_layer_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
```

未实现的 runner 必须在 `docs/benchmark-report.md` 中明确降级说明和替代验证，不能留空。

## 验收标准

- Benchmark Report 包含 Recall@3、Conflict Update Accuracy、Evidence Coverage、Candidate Precision、Agent Task Context Use Rate、L1 Hot Recall p95、Sensitive Reminder Leakage Rate、Stale Leakage Rate。
- 每个失败 case 有失败分类：`candidate_not_detected`、`wrong_subject_normalization`、`wrong_layer_routing`、`vector_miss`、`keyword_miss`、`stale_value_leaked`、`evidence_missing`、`agent_did_not_prefetch`、`reminder_too_noisy`、`permission_scope_error`。
- 每个 benchmark case 有输入字段、期望输出字段、实际输出摘要和 recommended fix。
- 旧 Day1 benchmark 仍通过。

## 队友晚上补位任务

给队友先看这个：

1. 今天重点是“怎么证明这个 Copilot 有用”，不是追求漂亮数字。
2. 人工检查 20 条失败或边界样例。
3. 把不自然的 benchmark 对话改得更像真实飞书项目群。
4. 写 Benchmark Report 的“失败分类说明”和“当前局限”草稿。
5. 遇到问题发我：case_id、你觉得不自然的句子、建议改成什么。

今晚不用做：

- 不用接真实飞书权限。
- 不用追求最终指标上限，先保证指标可复现。
