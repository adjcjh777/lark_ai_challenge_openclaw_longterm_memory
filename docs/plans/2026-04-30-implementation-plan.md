# 2026-04-30 Implementation Plan

阶段：candidate、manual memory、evidence、governance  
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

实现 Copilot governance 的候选入口：`memory.create_candidate`、`memory.confirm`、`memory.reject`。手动记忆和自动候选都必须经过 evidence、safety、conflict check。

## 用户白天主线任务

1. 新增 `governance.py`，定义 candidate / active / rejected 的状态转移。
2. 在 `service.py` 中实现 `create_candidate()`、`confirm()`、`reject()`。
3. 在 `tools.py` 中暴露 `memory.create_candidate`、`memory.confirm`、`memory.reject`。
4. 手动“记住”类表达不能绕过 governance。
5. 候选必须带 evidence；高风险和低置信内容默认停留在 candidate。

## 需要改/新增的文件

- `memory_engine/copilot/governance.py`
- `memory_engine/copilot/service.py`
- `memory_engine/copilot/tools.py`
- `memory_engine/copilot/permissions.py`
- `tests/test_copilot_governance.py`
- `tests/test_copilot_tools.py`
- `benchmarks/copilot_candidate_cases.json`

## 测试

```bash
python3 -m unittest tests.test_copilot_governance tests.test_copilot_tools
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

## 验收标准

- candidate 默认不进入 search。
- confirm 后进入 active。
- reject 后不召回。
- 每条 active memory 必须带 evidence。
- Candidate Precision >= 60% 的 benchmark 数据集成型。

## 队友晚上补位任务

1. 补 30 条候选识别样例：15 条应该记，15 条不应该记。
2. 每条写白话原因，说明“为什么值得记 / 为什么不值得记”。
3. 检查卡片或 dry-run 文案里是否能看出这是“待确认记忆”。

今晚不用做：

- 不用替用户确认高风险记忆。
- 不用改 Bitable 同步。

