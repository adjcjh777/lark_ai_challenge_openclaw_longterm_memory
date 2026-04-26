# 2026-05-04 Implementation Plan

阶段：Demo runbook、README、OpenClaw examples freeze
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

把可运行 Demo 固定下来，让评委或队友能按 README / runbook 复现 OpenClaw-native Copilot 主线；OpenClaw runtime 不稳定时，保留 CLI/dry-run 兜底，但叙事不退回 CLI-first。README 必须说明 Cognee 是本地 knowledge / memory engine，企业记忆治理由 Copilot Core 自研。

## 必读上下文

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/2026-05-04-implementation-plan.md`
- `agent_adapters/openclaw/examples/`
- `docs/benchmark-report.md`

## 用户白天主线任务

1. 更新 `docs/demo-runbook.md`，写清 5 分钟演示流程。
2. 更新 `README.md`：项目定位、快速开始、OpenClaw tools、Cognee local SDK path、Demo 路径、Benchmark 路径、飞书配置说明。
3. 准备 demo seed 或 dry-run 数据。
4. 检查 `agent_adapters/openclaw/examples/` 是否可复制执行或清楚标注为 schema demo。
5. 明确真实 Feishu Bot / Bitable / OpenClaw 的权限风险和 fallback 路径。
6. 在 runbook 中展示 evidence、version chain、stale/superseded 不泄漏、reminder candidate dry-run。
7. 确认 demo flow 覆盖历史决策查询、任务前 prefetch、冲突更新三条线，至少前两条必须可演示。

## 今日做到什么程度

今天结束时必须让一个不熟悉仓库的人能按文档复现核心 demo：

- README 第一屏能说明这是 OpenClaw-native Feishu Memory Copilot，不是旧 CLI demo。
- Demo runbook 有 5 分钟演示顺序、每一步输入、预期输出和失败兜底。
- OpenClaw examples 与 `memory_tools.schema.json` 字段一致。
- 如果 live OpenClaw gateway 不稳，runbook 明确 schema examples + CLI/dry-run 的替代演示。
- demo seed / replay 数据固定，避免现场临时造数据。

## 今日执行清单（按顺序）

| 顺序 | 动作 | 文件/位置 | 做到什么程度 | 验收证据 |
|---|---|---|---|---|
| 1 | 写 README 快速开始 | `README.md` | 10 分钟内能看懂定位、安装、验证、demo、benchmark | 队友按 README 能走到第一条命令 |
| 2 | 写 demo runbook | `docs/demo-runbook.md` | 5 分钟脚本，覆盖痛点、工具调用、证据、版本、prefetch、heartbeat | 每步有输入和预期输出 |
| 3 | 固定 demo 数据 | `scripts/demo_seed.py` 或 examples | 能复现历史决策、冲突更新、prefetch 三条主线 | seed/dry-run 输出稳定 |
| 4 | 冻结 OpenClaw examples | `agent_adapters/openclaw/examples/*.json` | examples 字段与 schema 对齐，至少 2 条必演示可复制 | JSON 可解析，和 runbook 互相引用 |
| 5 | 写 fallback 路径 | `docs/demo-runbook.md` | live 失败时走 CLI/dry-run/replay/录屏，不退回 CLI-first 叙事 | runbook 有“现场故障处理”小节 |
| 6 | 串联 benchmark | `docs/benchmark-report.md` | demo 里展示的能力能在 report 里找到对应指标 | runbook 引用指标章节 |
| 7 | 检查敏感文件 | README / `.gitignore` | 说明 `.data/cognee/`、logs、token 不提交 | `git status --ignored` 不出现敏感提交项 |
| 8 | 全量 smoke test | 本地命令 | README 中的核心命令至少手动跑一次 | final 记录成功/失败命令 |

## 今日不做

- 不新增 MVP 外的新工具或新入口。
- 不让 README 变成营销页，优先可复现。
- 不把 OpenClaw runtime 不稳定包装成已完全验证。
- 不真实写飞书生产空间，除非 dry-run 和材料已稳定。

## 需要改/新增的文件

- `README.md`
- `docs/demo-runbook.md`
- `docs/benchmark-report.md`
- `agent_adapters/openclaw/examples/*.json`
- 可选：`scripts/demo_seed.py`
- 可选：`scripts/run_demo_check.sh`

## 测试

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m unittest discover tests
```

## 验收标准

- README 能让新读者理解这是 Feishu Memory Copilot，而不是普通 CLI 工具。
- Demo runbook 至少覆盖：历史决策召回、冲突更新、prefetch、heartbeat dry-run。
- 每个演示步骤都有命令或输入输出样例。
- OpenClaw runtime 不稳时，schema examples + CLI/dry-run 路径仍能证明工具契约。
- README 明确本地数据目录 `.data/cognee/` 不提交，真实 token / 飞书日志不提交。

## 队友晚上补位任务

给队友先看这个：

1. 今天主要把 Demo 固定成评委能复现的路径。
2. 按 README 从头走一遍，记录卡住的位置。
3. 改 demo 讲解词，让非工程评委能理解“不是普通搜索，而是有证据和版本的企业记忆”。
4. 准备截图需求清单：需要截哪个页面、哪个输出、哪个指标表。
5. 遇到问题发我：卡住步骤、命令或文档段落、实际输出。

今晚不用做：

- 不用临时扩大功能。
- 不用改核心算法。
- 不用真实写入飞书生产空间。
