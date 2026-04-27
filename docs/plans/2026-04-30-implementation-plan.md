# 2026-04-30 Implementation Plan

阶段：candidate、manual memory、evidence、governance、document candidate source
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

实现 Copilot governance 的候选入口：`memory.create_candidate`、`memory.confirm`、`memory.reject`。手动记忆、自动候选和文档抽取都必须经过 evidence、safety、conflict check；旧 `document_ingestion.py` 只能作为 candidate source adapter，不能绕过 Copilot service 直接写 active memory。

## MemPalace 转换落点

今天只借鉴 MemPalace 的 drawer 思路：原文必须保留下来，但只能作为 evidence / candidate source，不能直接变成默认答案。对应到本项目就是 `RawEvidence` / `Evidence` gate：飞书消息、文档片段、OpenClaw 当前上下文先成为来源证据，再由 governance 判断是否生成 candidate，最后必须经过 confirm 才能 active。

今天要坚持两条边界：

- 手动“记住”也不能绕过 evidence、safety 和 conflict check。
- 文档 ingestion 只产出 candidate source，不直接写 active memory，也不把整篇文档塞进默认 search。

## 必读上下文

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/2026-04-30-implementation-plan.md`
- `memory_engine/document_ingestion.py`
- `memory_engine/repository.py`
- `memory_engine/benchmark.py`

## 用户白天主线任务

1. 新增 `governance.py`，定义 candidate / active / rejected 的状态转移。
2. 在 `schemas.py` 或 `governance.py` 中明确 raw evidence / source quote 的输入契约，至少包含 `source_type`、`source_id`、`quote`、`actor_id`、`created_at`。
3. 在 `service.py` 中实现 `create_candidate()`、`confirm()`、`reject()`。
4. 在 `tools.py` 中暴露 `memory.create_candidate`、`memory.confirm`、`memory.reject`，错误格式继续使用统一 `ToolError`。
5. 手动“记住”类表达不能绕过 governance。
6. 候选必须带 evidence；高风险和低置信内容默认停留在 candidate。
7. 把 `document_ingestion.py` 的抽取结果适配为 `memory.create_candidate` 输入，不再让文档 ingestion 自己决定 active 状态。
8. 扩展 `benchmarks/copilot_candidate_cases.json`，保持 5-10 条最小样例先跑通，再扩展到 30 条。
9. 扩展 benchmark runner 或单测替代路径，统计 Candidate Precision、evidence_missing、candidate_not_detected。

## 今日做到什么程度

今天结束时系统必须能区分“值得记的候选”和“已经生效的记忆”：

- `memory.create_candidate` 只产生 candidate，不默认进入 search。
- `memory.confirm` 才能让 candidate 进入 active。
- `memory.reject` 后 candidate 不再被默认召回。
- 每条 candidate 和 active memory 都必须带 evidence；没有 evidence 的内容不能升级为 active。
- 文档 ingestion、手动记忆、自动候选都走同一套 governance，不各自写库。

## 今日执行清单（按顺序）

| 顺序 | 动作 | 文件/位置 | 做到什么程度 | 验收证据 |
|---|---|---|---|---|
| 1 | 定义状态机 | `governance.py` | candidate -> active/rejected，active 不可无 evidence | governance 单测覆盖合法/非法转移 |
| 2 | 定义证据输入 | `schemas.py`、`governance.py` | 明确 raw evidence/source quote 字段；原文只作为证据，不作为默认答案 | 单测验证缺 quote/source_id 时失败 |
| 3 | 实现 create_candidate | `service.py`、`tools.py` | 输入 text/scope/source，输出 candidate、risk_flags、conflict | tools 单测覆盖成功和 validation_error |
| 4 | 实现 confirm/reject | `service.py`、`tools.py` | confirm 进入 active，reject 不召回；重复操作返回可读错误 | governance 单测覆盖幂等或错误 |
| 5 | 加 evidence gate | `governance.py` | 缺 source quote/source_id 时不可 active | evidence_missing 测试通过 |
| 6 | 加 sensitive 最小门控 | `permissions.py`、`governance.py` | token/secret 类内容进入 blocked 或人工复核 | sensitive case 不 auto-confirm |
| 7 | 改文档候选入口 | `document_ingestion.py` | 只产出 `create_candidate` 输入，不直接写 active | ingestion 测试检查状态为 candidate |
| 8 | 建 candidate benchmark | `copilot_candidate_cases.json` | 至少 5-10 条可跑，结构能扩到 30 条 | runner 或单测能统计 precision |
| 9 | 写失败分类 | `benchmark.py` 或 benchmark case | `candidate_not_detected`、`false_positive_candidate`、`evidence_missing` | report/summary 有分类字段 |

## 今日不做

- 不把所有文档句子都记成 active。
- 不让手动“记住”绕过 governance。
- 不做完整人工审核后台 UI。
- 不直接接真实 Bitable 审核流。

## 需要改/新增的文件

- `memory_engine/copilot/governance.py`
- `memory_engine/copilot/service.py`
- `memory_engine/copilot/tools.py`
- `memory_engine/copilot/permissions.py`
- `memory_engine/document_ingestion.py`
- `memory_engine/benchmark.py`
- `tests/test_copilot_governance.py`
- `tests/test_copilot_tools.py`
- `tests/test_document_ingestion.py`
- `benchmarks/copilot_candidate_cases.json`

## 测试

```bash
python3 scripts/check_openclaw_version.py
python3 -m unittest tests.test_copilot_governance tests.test_copilot_tools tests.test_document_ingestion
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json
```

如果 `copilot_candidate_cases.json` runner 尚未实现，必须在当天记录为缺口，并用 `tests.test_copilot_governance` 覆盖同等核心路径。

## 验收标准

- candidate 默认不进入 search。
- confirm 后进入 active。
- reject 后不召回。
- 每条 active memory 必须带 evidence。
- raw evidence / source quote 只用于 candidate、版本解释和 evidence 展示，不直接成为默认 search 当前答案。
- 手动“记住”不绕过 sensitive / evidence / conflict check。
- 文档 ingestion 只生成 candidate source，不直接改 active 状态。
- Candidate Precision >= 60% 的 benchmark 数据集成型。

## 我的补充任务

先看这个：

1. 今天要做的是“什么内容值得成为待确认记忆”，不是直接把所有内容存起来。
2. 补 30 条候选识别样例：15 条应该记，15 条不应该记。
3. 每条写白话原因，说明“为什么值得记 / 为什么不值得记”。
4. 检查卡片或 dry-run 文案里是否能看出这是“待确认记忆”，而不是已经生效。
5. 遇到问题记录：case_id、原文、正确处理和原因。

本阶段不用做：

- 不用替用户确认高风险记忆。
- 不用改 Bitable 同步。
- 不用把文档抽取结果直接写成 active memory。
