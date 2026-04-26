# 2026-05-04 Implementation Plan

阶段：Demo runbook + README  
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

把可运行 Demo 固定下来，让评委或队友能按 README / runbook 复现 OpenClaw-native Copilot 主线；OpenClaw runtime 不稳定时，保留 CLI/dry-run 兜底，但叙事不退回 CLI-first。

## 用户白天主线任务

1. 更新 `docs/demo-runbook.md`，写清 5 分钟演示流程。
2. 更新 `README.md`：项目定位、快速开始、OpenClaw tools、Demo 路径、Benchmark 路径、飞书配置说明。
3. 准备 demo seed 或 dry-run 数据。
4. 检查 `agent_adapters/openclaw/examples/` 是否可复制执行或清楚标注为 schema demo。
5. 明确真实 Feishu Bot / Bitable / OpenClaw 的权限风险和 fallback 路径。

## 需要改/新增的文件

- `README.md`
- `docs/demo-runbook.md`
- `agent_adapters/openclaw/examples/*.json`
- 可选：`scripts/demo_seed.py`
- 可选：`scripts/run_demo_check.sh`

## 测试

```bash
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m unittest discover tests
```

## 验收标准

- README 能让新读者理解这是 Feishu Memory Copilot，而不是普通 CLI 工具。
- Demo runbook 至少覆盖：历史决策召回、冲突更新、prefetch、heartbeat dry-run。
- 每个演示步骤都有命令或输入输出样例。

## 队友晚上补位任务

1. 按 README 从头走一遍，记录卡住的位置。
2. 改 demo 讲解词，让非工程评委能理解。
3. 准备截图需求清单：需要截哪个页面、哪个输出、哪个指标表。

今晚不用做：

- 不用临时扩大功能。
- 不用改核心算法。

