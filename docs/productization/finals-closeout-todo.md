# Finals Closeout TODO

日期：2026-05-04
来源：`/Users/junhaocheng/Downloads/deep-research-report (2).md`
阶段：复赛 / 比赛收尾材料收束

## 先看这个

这份清单把复赛推进研究报告转成可执行待办，并记录本轮是否已经完成。它不是新的产品主控文档；当前事实源仍按 `AGENTS.md` 执行，以当前代码、`README.md` 顶部、`docs/productization/full-copilot-next-execution-doc.md` 和 `docs/productization/prd-completion-audit-and-gap-tasks.md` 为准。

本轮收尾原则：

- 少做新功能，多收束现有能力。
- 主叙事固定为 **OpenClaw-native 企业记忆治理层**。
- 赛题方向固定为 **方向 B 为主、方向 D 为辅**：项目决策与上下文记忆是主线，团队共享记忆、冲突覆盖和遗忘提醒是辅助主线。
- 不把 demo / sandbox / pre-production / controlled readiness 写成 production live、全量 workspace ingestion、长期 embedding 服务或 productized live。

## 报告待办到交付物映射

| ID | 报告待办 | 当前处理 | 完成证据 | 边界 |
|---|---|---|---|---|
| F1 | 冻结一句话叙事：不是 Bot、RAG 或向量库 Demo，而是企业记忆治理层 | 已完成 | `README.md` 顶部已有项目定义；本轮在白皮书和评委包补复赛口径 | 不能写成生产部署或全量 workspace crawler |
| F2 | 把赛题方向收束为 B 主、D 辅，不把 A/C 当主叙事 | 已完成 | 本文、`docs/memory-definition-and-architecture-whitepaper.md`、`docs/judge-10-minute-experience.md` 已明确 B+D | CLI / preference 能力只能作为兼容入口或旁支，不抢主线 |
| F3 | 不再从零起草三份交付物，改写现有材料 | 已完成 | 本轮只更新现有白皮书、Demo、Benchmark、评委包，并新增本收尾清单 | 不新增未验证功能 |
| F4 | Demo 收成五分钟三幕式脚本 | 已完成 | `docs/demo-runbook.md` 新增“复赛三幕式脚本” | 真实飞书不稳时回退 replay；不能把 replay 写成 live |
| F5 | Benchmark 改写成三类赛题证明：抗干扰、矛盾更新、效能验证 | 已完成 | `docs/benchmark-report.md` 新增“复赛三类证明” | Steps Saved / Time-to-Answer 当前不是自动 runner 硬指标，不能虚报 |
| F6 | 把 heartbeat / superseded / stale leakage 讲成企业版遗忘管理 | 已完成 | 白皮书、Demo、Benchmark 均补“旧值过滤 / review_due candidate / stale leakage”讲法 | heartbeat 仍是 reminder candidate，不真实群推送、不自动 active |
| F7 | 模板落位：摘要、架构、Demo、Benchmark、边界 / 风险 / 后续计划 | 已完成 | `docs/judge-10-minute-experience.md` 新增“复赛模板落位” | 模板链接未直接展开，因此按现有评委材料清单映射 |
| F8 | 主动压制生产化冲动，复赛材料只讲今天已验证的价值 | 已完成 | 本文和相关材料都保留 no-overclaim 清单 | productized workspace ingestion 仍以 24h+ long-run blocker 为准 |

## 复赛材料入口

| 用途 | 文件 |
|---|---|
| 评委 10 分钟脚本和模板落位 | `docs/judge-10-minute-experience.md` |
| 五分钟三幕 Demo 和 fallback | `docs/demo-runbook.md` |
| 三类 benchmark 证明 | `docs/benchmark-report.md` |
| Define / Build / Prove 白皮书 | `docs/memory-definition-and-architecture-whitepaper.md` |
| 当前完成边界和 PRD 对账 | `README.md`、`docs/productization/prd-completion-audit-and-gap-tasks.md` |

## 本轮不做

- 不升级 OpenClaw；继续锁定 `2026.4.24`。
- 不启动新的 Feishu listener，不抢当前 OpenClaw websocket / sandbox。
- 不新增 production live、SSO、多租户后台或长期 embedding 服务实现。
- 不提交真实 `chat_id`、`open_id`、message id、token、`.env` 或脱敏前日志。
- 不把 Steps Saved / Time-to-Answer 写成已有自动化硬指标；除非后续补手动计时或 runner。

## 验收命令

文档-only 收尾至少运行：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
git diff --check
```

展示前建议追加：

```bash
python3 scripts/check_demo_readiness.py --json
python3 scripts/check_real_feishu_expression_quality_gate.py --json
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
```
