# UX-07：10 分钟评委体验包

日期：2026-04-29
负责人：程俊豪
状态：待执行
上游总览：[用户体验产品化 TODO 清单](../user-experience-todo.md)
执行顺序：第 7 个

## 本轮要做什么

做一个评委可以在 10 分钟内走完的体验包，让评委不用理解内部 ID，也能看懂：

1. 项目解决什么问题。
2. 飞书里如何查当前结论。
3. 如何确认候选记忆。
4. 如何解释旧版本。
5. 如何做任务前 prefetch。
6. benchmark 和安全边界是什么。
7. 架构为什么是 OpenClaw-native。

## 为什么现在做

README、demo runbook、benchmark report 和白皮书已经有，但入口仍偏工程验收。评委时间有限，需要一条短、稳、能失败 fallback 的产品路线，而不是阅读全部文档后自己拼演示。

## 本阶段不用做

- 本阶段不用制作生产级宣传页。
- 本阶段不用让评委现场理解 `candidate_id`、`trace_id` 或 `memory_id`。
- 本阶段不用把 dry-run、demo replay、sandbox 或本机 staging 写成 production live。
- 本阶段不用接全量真实飞书 workspace。

## 执行任务

| 顺序 | 任务 | 文件位置 | 完成标准 |
|---|---|---|---|
| 1 | 写 10 分钟评委脚本 | `docs/demo-runbook.md` 或新 `docs/judge-10-minute-experience.md` | 每分钟有输入、动作、预期输出、失败 fallback 和讲解词。 |
| 2 | 固定演示数据和截图清单 | `docs/demo-runbook.md`、`docs/assets/`、`reports/` 本地证据目录 | 演示数据可复现；截图不包含真实 ID、token 或敏感内容。 |
| 3 | 对齐 benchmark 和安全边界讲法 | `docs/benchmark-report.md`、`README.md`、`docs/human-product-guide.md` | 评委能看到指标、样本规模、不能 overclaim 的边界。 |
| 4 | 补架构图入口 | `docs/diagrams/`、`docs/README.md` | 10 分钟脚本能链接到系统架构、产品交互流和 benchmark loop。 |
| 5 | 做一次计时验收 | `docs/demo-runbook.md` 或 handoff | 记录 10 分钟内能否走完；失败点和替代路线写清。 |

## 10 分钟脚本结构

| 时间 | 内容 | 评委看到什么 |
|---|---|---|
| 1 分钟 | 问题和产品定义 | 这个项目把飞书协作信息变成可治理企业记忆。 |
| 2 分钟 | 当前结论召回 | 用户普通话提问，系统返回 active 结论、证据和解释。 |
| 2 分钟 | 候选确认 | 用户说一条新规则，系统生成 candidate，reviewer 确认或拒绝。 |
| 1 分钟 | 旧版本解释 | 系统解释为什么旧值被 superseded。 |
| 1 分钟 | 任务前 prefetch | Agent 做任务前拿到 compact context pack。 |
| 1 分钟 | benchmark 和安全边界 | 展示 Recall@3、误记率、旧值泄漏率、敏感泄漏率等指标。 |
| 2 分钟 | 架构和 no-overclaim | 展示 OpenClaw Agent -> memory.* -> CopilotService -> governance / retrieval / audit。 |

## 评委版讲法边界

可以说：

- 已完成 MVP / Demo / Pre-production 本地闭环。
- 已完成 OpenClaw tool schema、本地 first-class registry 和本地 Agent `fmc_*` 调用验证。
- 已完成受控飞书测试群 sandbox 和 OpenClaw Feishu websocket running 本机 staging 证据。
- 已完成 candidate-only、permission fail-closed、audit 和 benchmark。

不能说：

- 不能说生产部署已完成。
- 不能说全量接入飞书 workspace。
- 不能说真实 Feishu DM 已稳定路由到本项目 first-class `fmc_*` / `memory.*` 工具链路。
- 不能说 productized live 长期运行已完成。
- 不能说长期 embedding 服务已完成。

## 验收命令

文档和演示脚本更新后运行：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_demo_readiness.py --json
python3 scripts/check_copilot_health.py --json
git diff --check
ollama ps
```

如果同步更新 benchmark 报告或样本，再追加：

```bash
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
```

## 完成标准

- 评委按一条脚本 10 分钟内能看懂问题、体验、指标、安全边界和架构。
- 每一步都有输入、预期输出和失败 fallback。
- 脚本不要求评委复制内部 ID。
- README、human guide、demo runbook 和 benchmark report 口径一致。
- 演示材料没有真实敏感 ID、token 或 chat 内容。

## 失败处理

- 如果真实飞书链路当天不稳定，切到 demo replay / 本地证据脚本，并明确说明不是 live E2E。
- 如果 OpenClaw health running 字段和 channels status 不一致，按现有规则记录为 warning，不把它包装成失败或完成。
- 如果 10 分钟超时，优先删工程细节，不删 no-overclaim 和安全边界。

## 顺序执行出口

完成 UX-07 后，回到 [用户体验产品化 TODO 清单](../user-experience-todo.md) 更新 7 项状态、验证证据、剩余风险，并按 AGENTS.md 同步飞书任务看板和提交推送。
