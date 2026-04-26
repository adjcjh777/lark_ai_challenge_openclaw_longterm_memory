# Dated Implementation Plans

本目录是 Feishu Memory Copilot 新主线的每日执行入口。后续任务不再新增 `day1`、`day2` 这种相对日期文档，而是使用绝对日期命名：

```text
docs/plans/YYYY-MM-DD-implementation-plan.md
```

默认读取顺序：

1. `AGENTS.md`
2. `docs/feishu-memory-copilot-implementation-plan.md`
3. 当天的 `docs/plans/YYYY-MM-DD-implementation-plan.md`
4. 必要时读取上一日 handoff / 执行记录
5. 只有被当天计划明确引用时，才读取 `docs/archive/legacy-day-docs/` 或 `docs/reference/`

## 当前计划索引

| 日期 | 文件 | 阶段 |
|---|---|---|
| 2026-04-26 | `2026-04-26-implementation-plan.md` | 主控切换、OpenClaw tool schema、Copilot package skeleton |
| 2026-04-27 | `2026-04-27-implementation-plan.md` | `memory.search` contract |
| 2026-04-28 | `2026-04-28-implementation-plan.md` | L0/L1/L2/L3 和 query cascade |
| 2026-04-29 | `2026-04-29-implementation-plan.md` | hybrid retrieval 和 curated memory embedding |
| 2026-04-30 | `2026-04-30-implementation-plan.md` | candidate、manual memory、evidence、governance |
| 2026-05-01 | `2026-05-01-implementation-plan.md` | conflict update、versions、stale leakage |
| 2026-05-02 | `2026-05-02-implementation-plan.md` | prefetch、heartbeat、OpenClaw demo flow |
| 2026-05-03 | `2026-05-03-implementation-plan.md` | Benchmark expansion |
| 2026-05-04 | `2026-05-04-implementation-plan.md` | Demo runbook 和 README |
| 2026-05-05 | `2026-05-05-implementation-plan.md` | 白皮书 |
| 2026-05-06 | `2026-05-06-implementation-plan.md` | 提交材料、录屏、QA |
| 2026-05-07 | `2026-05-07-implementation-plan.md` | 最终验证、提交缓冲、push |

