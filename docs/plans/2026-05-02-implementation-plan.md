# 2026-05-02 Implementation Plan

阶段：`memory.prefetch`、heartbeat reminder prototype、OpenClaw demo/card dry-run flow
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

完成 MVP 第一周闭环：OpenClaw Agent 能在任务前调用 `memory.prefetch` 获取 context pack；heartbeat 能生成 reminder candidate；至少 2 条 OpenClaw E2E demo flow 可复制演示。Card/Bitable 走 dry-run 也必须能展示 evidence、version chain 和 stale/superseded 不泄漏。

## 必读上下文

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/2026-05-02-implementation-plan.md`
- `agent_adapters/openclaw/memory_tools.schema.json`
- `agent_adapters/openclaw/examples/`
- `memory_engine/feishu_cards.py`
- `memory_engine/bitable_sync.py`

## 用户白天主线任务

1. 实现 `memory.prefetch(task, scope, current_context)`，返回 compact context pack。
2. 新增 `heartbeat.py`，生成 reminder candidate 并通过 importance、relevance、cooldown、permission、sensitive gates。
3. 创建 `agent_adapters/openclaw/examples/` 下的 demo flow：历史决策查询、任务前 prefetch，目标再补冲突更新。
4. 补 `tests/test_copilot_prefetch.py` 和 `tests/test_copilot_heartbeat.py`。
5. 准备 demo dry-run 输出，证明这不是旧 CLI-only 流程。
6. 让 candidate review card、version card、reminder card 都能从 Copilot service 输出生成 dry-run payload。
7. 让 Bitable dry-run payload 覆盖 Memory Ledger、Versions、Candidate Review、Benchmark Results、Reminder Candidates。
8. 扩展 `benchmarks/copilot_prefetch_cases.json` 和 `benchmarks/copilot_heartbeat_cases.json`，至少各有 5 条可读样例。

## 需要改/新增的文件

- `memory_engine/copilot/orchestrator.py`
- `memory_engine/copilot/heartbeat.py`
- `memory_engine/copilot/service.py`
- `memory_engine/copilot/tools.py`
- `memory_engine/feishu_cards.py`
- `memory_engine/bitable_sync.py`
- `agent_adapters/openclaw/examples/*.json`
- `tests/test_copilot_prefetch.py`
- `tests/test_copilot_heartbeat.py`
- `tests/test_feishu_interactive_cards.py`
- `tests/test_bitable_sync.py`
- `benchmarks/copilot_prefetch_cases.json`
- `benchmarks/copilot_heartbeat_cases.json`

## 测试

```bash
python3 scripts/check_openclaw_version.py
python3 -m unittest tests.test_copilot_prefetch tests.test_copilot_heartbeat
python3 -m unittest tests.test_feishu_interactive_cards tests.test_bitable_sync
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

如果 prefetch / heartbeat benchmark runner 已实现，再追加：

```bash
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
```

## 验收标准

- Agent Task Context Use Rate >= 70% 的评测入口成型。
- heartbeat 能输出 reminder candidate。
- Sensitive Reminder Leakage Rate = 0。
- Stale Leakage Rate 可被 conflict / heartbeat / prefetch 评测统计。
- OpenClaw demo flow 至少覆盖历史决策查询和任务前 prefetch，目标再覆盖冲突更新。
- card / Bitable 写入失败时有 dry-run payload，可展示 evidence、version chain 和 stale/superseded 过滤。

## 队友晚上补位任务

给队友先看这个：

1. 今天要把第一周 Demo 闭环串起来，重点看 Agent 是否会在任务前主动取上下文。
2. 按 `agent_adapters/openclaw/examples/` 走一遍 demo 样例。
3. 记录哪里不像真实办公 Copilot，尤其是 prefetch 输出是否像一个同事提前提醒你。
4. 准备 5 分钟 Demo 讲解词：先讲用户痛点，再讲 Agent 自动调用记忆工具。
5. 检查 reminder 文案中是否有 token、secret 或完整内部链接。

今晚不用做：

- 不用做复杂个性化推送。
- 不用把 reminder 直接发到真实群，dry-run 可作为 MVP 验收。
- 不用扩大 OpenClaw 工具范围。
