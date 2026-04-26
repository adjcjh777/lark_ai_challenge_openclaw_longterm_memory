# 2026-05-02 Implementation Plan

阶段：`memory.prefetch` + heartbeat reminder prototype + OpenClaw demo flow  
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

完成 MVP 第一周闭环：OpenClaw Agent 能在任务前调用 `memory.prefetch` 获取 context pack；heartbeat 能生成 reminder candidate；至少 2 条 OpenClaw E2E demo flow 可复制演示。

## 用户白天主线任务

1. 实现 `memory.prefetch(task, scope, current_context)`。
2. 新增 `heartbeat.py`，生成 reminder candidate 并通过 importance、relevance、cooldown、permission、sensitive gates。
3. 创建 `agent_adapters/openclaw/examples/` 下的 demo flow。
4. 补 `tests/test_copilot_prefetch.py` 和 `tests/test_copilot_heartbeat.py`。
5. 准备 demo dry-run 输出，证明这不是旧 CLI-only 流程。

## 需要改/新增的文件

- `memory_engine/copilot/orchestrator.py`
- `memory_engine/copilot/heartbeat.py`
- `memory_engine/copilot/service.py`
- `memory_engine/copilot/tools.py`
- `agent_adapters/openclaw/examples/*.json`
- `tests/test_copilot_prefetch.py`
- `tests/test_copilot_heartbeat.py`
- `benchmarks/copilot_prefetch_cases.json`
- `benchmarks/copilot_heartbeat_cases.json`

## 测试

```bash
python3 -m unittest tests.test_copilot_prefetch tests.test_copilot_heartbeat
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

## 验收标准

- Agent Task Context Use Rate >= 70% 的评测入口成型。
- heartbeat 能输出 reminder candidate。
- Sensitive Reminder Leakage Rate = 0。
- OpenClaw demo flow 至少覆盖历史决策查询和任务前 prefetch，目标再覆盖冲突更新。

## 队友晚上补位任务

1. 按 `agent_adapters/openclaw/examples/` 走一遍 demo 样例。
2. 记录哪里不像真实办公 Copilot。
3. 准备 5 分钟 Demo 讲解词：先讲用户痛点，再讲 Agent 自动调用记忆工具。

今晚不用做：

- 不用做复杂个性化推送。
- 不用把 reminder 直接发到真实群，dry-run 可作为 MVP 验收。

