# Dated Implementation Plans

本目录是 Feishu Memory Copilot 新主线的每日执行入口。后续任务不再新增 `day1`、`day2` 这种相对日期文档，而是使用绝对日期命名：

```text
docs/plans/YYYY-MM-DD-implementation-plan.md
```

默认读取顺序：

1. `AGENTS.md`
2. `docs/feishu-memory-copilot-implementation-plan.md`
3. 当天的 `docs/plans/YYYY-MM-DD-implementation-plan.md`
4. 必要时读取上一日 handoff / 执行记录，例如 `2026-04-27-handoff.md`
5. 只有被当天计划明确引用时，才读取 `docs/archive/legacy-day-docs/` 或 `docs/reference/`

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
| 2026-04-26 | `2026-04-26-implementation-plan.md` | 主控切换、OpenClaw tool schema、Copilot package skeleton |
| 2026-04-27 | `2026-04-27-implementation-plan.md` | Cognee local spike、adapter contract、Copilot schemas、`memory.search` fallback |
| 2026-04-27 | `2026-04-27-handoff.md` | 2026-04-26/27 完成总结和 2026-04-28 接续说明 |
| 2026-04-28 | `2026-04-28-implementation-plan.md` | `memory.search` service contract、L0/L1/L2/L3 和 query cascade |
| 2026-04-28 | `2026-04-28-handoff.md` | 2026-04-28 分层查询、评测脚本硬化完成总结和 2026-04-29 接续说明 |
| 2026-04-29 | `2026-04-29-implementation-plan.md` | hybrid retrieval、RecallIndex 短索引、Cognee recall/search fallback、curated memory embedding |
| 2026-04-29 | `2026-04-29-handoff.md` | 2026-04-29 混合召回、Recall@3 评测入口和 2026-04-30 接续说明 |
| 2026-04-30 | `2026-04-30-implementation-plan.md` | candidate、manual memory、evidence gate、governance、document candidate source |
| 2026-04-30 | `2026-04-30-handoff.md` | 2026-04-30 候选记忆治理、confirm/reject、candidate benchmark 和 2026-05-01 接续说明 |
| 2026-05-01 | `2026-05-01-implementation-plan.md` | conflict update、versions、Cold evidence、stale leakage、Card/Bitable review surface |
| 2026-05-01 | `2026-05-01-handoff.md` | 2026-05-01 冲突更新、版本解释、conflict benchmark、Card/Bitable dry-run 和 2026-05-02 接续说明 |
| 2026-05-02 | `2026-05-02-implementation-plan.md` | prefetch、heartbeat、agent run summary candidate、OpenClaw demo/card dry-run flow |
| 2026-05-02 | `2026-05-02-handoff.md` | 2026-05-02 prefetch、heartbeat reminder candidate、OpenClaw demo dry-run 和 2026-05-03 接续说明 |
| 2026-05-03 | `2026-05-03-implementation-plan.md` | Benchmark expansion、metrics report、review surface evidence check |
| 2026-05-04 | `2026-05-04-implementation-plan.md` | Demo runbook、README、OpenClaw examples freeze |
| 2026-05-04 | `2026-05-04-handoff.md` | 2026-05-04 Demo runbook、README 快速开始、demo dry-run 和 2026-05-05 接续说明 |
| 2026-05-05 | `2026-05-05-implementation-plan.md` | 白皮书、architecture proof、competition narrative |
| 2026-05-05 | `2026-05-05-handoff.md` | 2026-05-05 Memory 定义与架构白皮书初稿和 2026-05-06 接续说明 |
| 2026-05-06 | `2026-05-06-implementation-plan.md` | 提交材料、录屏、QA、scope freeze |
| 2026-05-07 | `2026-05-07-implementation-plan.md` | 最终验证、提交缓冲、push |
