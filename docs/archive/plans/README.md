# Dated Implementation Plans

本目录保存 Feishu Memory Copilot 新主线的日期计划和交接证据。**2026-05-05 及以前的 implementation plan 已经全部完成，不再作为后续执行入口**；这些文件只用于查历史背景、验收证据和风险记录。

后续执行入口已经切到完整可用 Copilot 产品化主线：

```text
docs/productization/full-copilot-next-execution-doc.md
docs/productization/prd-completion-audit-and-gap-tasks.md
docs/productization/complete-product-roadmap-prd.md
```

如果后续还需要新增日期计划，继续使用绝对日期命名：

```text
docs/plans/YYYY-MM-DD-implementation-plan.md
```

新的默认读取顺序：

1. `AGENTS.md`
2. `README.md`
3. `docs/productization/full-copilot-next-execution-doc.md`
4. 当前产品化阶段直接相关的 contract / runbook / handoff
5. 必要时读取本目录下的历史 handoff / execution record
6. 只有被当前产品化阶段明确引用时，才读取 `docs/archive/legacy-day-docs/` 或 `docs/reference/`

## 每日计划必须包含的执行粒度

每个日期计划都要写到“打开文件就能开始做”的程度，不能只写方向词。至少包含：

- 当日目标：一句话说明今天要闭合哪条链路。
- 今日做到什么程度：写清当天结束时必须成立的事实，以及哪些能力不追求。
- 今日执行清单：按顺序列出动作、文件/位置、做到什么程度、验收证据。
- 需要改/新增的文件：写具体路径，不写“相关文件”。
- 测试：写当天必须跑的命令；未实现 runner 时要写降级说明。
- 验收标准：写可检查结果，不写“优化完成”这类模糊话。
- 我的补充任务：最多 5 条，每条要有动作、位置和完成标准。
- 今日不做：明确边界，避免当天任务扩散。

## 当前计划索引

| 日期 | 文件 | 阶段 |
|---|---|---|
| 2026-04-26 | `2026-04-26-implementation-plan.md` | 已完成；历史计划，不再执行 |
| 2026-04-27 | `2026-04-27-implementation-plan.md` | 已完成；历史计划，不再执行 |
| 2026-04-27 | `2026-04-27-handoff.md` | 已完成；历史交接证据 |
| 2026-04-28 | `2026-04-28-implementation-plan.md` | 已完成；历史计划，不再执行 |
| 2026-04-28 | `2026-04-28-handoff.md` | 已完成；历史交接证据 |
| 2026-04-29 | `2026-04-29-implementation-plan.md` | 已完成；历史计划，不再执行 |
| 2026-04-29 | `2026-04-29-handoff.md` | 已完成；历史交接证据 |
| 2026-04-30 | `2026-04-30-implementation-plan.md` | 已完成；历史计划，不再执行 |
| 2026-04-30 | `2026-04-30-handoff.md` | 已完成；历史交接证据 |
| 2026-05-01 | `2026-05-01-implementation-plan.md` | 已完成；历史计划，不再执行 |
| 2026-05-01 | `2026-05-01-handoff.md` | 已完成；历史交接证据 |
| 2026-05-02 | `2026-05-02-implementation-plan.md` | 已完成；历史计划，不再执行 |
| 2026-05-02 | `2026-05-02-handoff.md` | 已完成；历史交接证据 |
| 2026-05-03 | `2026-05-03-implementation-plan.md` | 已完成；历史计划，不再执行 |
| 2026-05-03 | `2026-05-03-handoff.md` | 已完成；历史交接证据 |
| 2026-05-04 | `2026-05-04-implementation-plan.md` | 已完成；历史计划，不再执行 |
| 2026-05-04 | `2026-05-04-handoff.md` | 已完成；历史交接证据 |
| 2026-05-05 | `2026-05-05-implementation-plan.md` | 已完成；历史计划，不再执行 |
| 2026-05-05 | `2026-05-05-handoff.md` | 已完成；历史交接证据 |
| 2026-05-06 | `2026-05-06-implementation-plan.md` | 产品化参考；当前入口以 `full-copilot-next-execution-doc.md` 为准 |
| 2026-05-07 | `2026-05-07-implementation-plan.md` | 产品化参考；当前入口以 `full-copilot-next-execution-doc.md` 为准 |
| 2026-05-07 | `2026-05-07-handoff.md` | 产品化阶段完成证据和风险参考 |
