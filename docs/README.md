# 项目文档导航

日期：2026-04-29（更新：真实飞书互动卡片）

## 先看这个

1. 当前项目已完成 MVP / Demo / Pre-production 本地闭环，后续重点是补齐真实飞书集成和产品化硬缺口。
2. 已完成的日期计划和 handoff 文档已归档到 `archive/` 和 `productization/handoffs/`，不再作为执行入口。
3. 当前代码和 `docs/productization/full-copilot-next-execution-doc.md` 是事实源。
4. 本项目由 Codex 完成主要代码和文档修改，人类接手时优先读产品指南和待办清单。
5. 读文档时要带着当前代码边界：受控测试群是 allowlist 模式；群内非 `@Bot` 消息可以静默探测 candidate，但默认不回群消息；`@Bot` / 私聊才是主动交互路径；仍然不是全量群聊被动记忆。

## 活跃文档入口（当前应读的）

### 核心事实源（4 个）

| 文档 | 用途 | 读取场景 |
|---|---|---|
| `AGENTS.md`（项目根目录） | 执行规则、事实源优先级、验证规则 | 每次开始新任务前 |
| `README.md`（项目根目录） | 项目顶层入口、快速开始、架构说明 | 新读者 / 评委 |
| [productization/full-copilot-next-execution-doc.md](productization/full-copilot-next-execution-doc.md) | **当前主控执行文档** | 所有产品化任务 |
| [productization/prd-completion-audit-and-gap-tasks.md](productization/prd-completion-audit-and-gap-tasks.md) | PRD 完成度审计和未完成边界 | 复盘 / 对账 |

### 产品规划（4 个）

| 文档 | 用途 |
|---|---|
| [productization/complete-product-roadmap-prd.md](productization/complete-product-roadmap-prd.md) | 完整产品路线 PRD |
| [productization/complete-product-roadmap-test-spec.md](productization/complete-product-roadmap-test-spec.md) | 验收规格 |
| [productization/launch-polish-todo.md](productization/launch-polish-todo.md) | 待办清单 |
| [productization/user-experience-todo.md](productization/user-experience-todo.md) | 用户体验产品化 TODO，记录 7 个 UX 缺口是否完成 |
| [productization/productized-live-long-run-plan.md](productization/productized-live-long-run-plan.md) | Productized live 长期运行方案；只定义 gate 和运行边界，不代表已上线 |

### 工作流和人类入口（2 个）

| 文档 | 用途 |
|---|---|
| [productization/workflow-and-test-process.md](productization/workflow-and-test-process.md) | 工作流和测试流程规范 |
| [human-product-guide.md](human-product-guide.md) | 人类快速理解产品 |
| [manual-testing-guide.md](manual-testing-guide.md) | 手动测试指南：飞书 DM、本地 replay、互动卡片点击、权限负例、审计读回、截图记录 |
| [judge-10-minute-experience.md](judge-10-minute-experience.md) | 10 分钟评委体验包：脚本、固定数据、截图清单、fallback、计时验收 |

### 契约（6 个，按需读取）

| 文档 | 用途 |
|---|---|
| [productization/contracts/storage-contract.md](productization/contracts/storage-contract.md) | 存储契约 |
| [productization/contracts/permission-contract.md](productization/contracts/permission-contract.md) | 权限契约 |
| [productization/contracts/openclaw-payload-contract.md](productization/contracts/openclaw-payload-contract.md) | OpenClaw payload 契约 |
| [productization/contracts/audit-observability-contract.md](productization/contracts/audit-observability-contract.md) | 审计可观测性契约 |
| [productization/contracts/migration-rfc.md](productization/contracts/migration-rfc.md) | 存储迁移 RFC |
| [productization/contracts/negative-permission-test-plan.md](productization/contracts/negative-permission-test-plan.md) | 负面权限测试计划 |

## 证据材料（初赛交付物，评委可能复查）

| 文档 | 用途 |
|---|---|
| [judge-10-minute-experience.md](judge-10-minute-experience.md) | 10 分钟评委体验入口 |
| [demo-runbook.md](demo-runbook.md) | 5 分钟 demo replay 演示脚本 |
| [benchmark-report.md](benchmark-report.md) | 六类评测证据 |
| [memory-definition-and-architecture-whitepaper.md](memory-definition-and-architecture-whitepaper.md) | 初赛白皮书 |
| [feishu-memory-copilot-prd.md](feishu-memory-copilot-prd.md) | 产品 baseline PRD |

## 已归档（不作为执行入口）

| 目录 | 内容 |
|---|---|
| [productization/handoffs/](productization/handoffs/) | 19 个已完成的 handoff / evidence / runbook |
| [archive/plans/](archive/plans/) | 22 个已完成的日期计划和 handoff |
| [archive/legacy-day-docs/](archive/legacy-day-docs/) | Day 1-7 旧文档 |
| [archive/legacy-master/](archive/legacy-master/) | 旧主控计划 |
| [archive/feishu-memory-copilot-implementation-plan.md](archive/feishu-memory-copilot-implementation-plan.md) | 旧主控计划（被 next-execution-doc 取代） |
| [archive/copilot-product-question-log.md](archive/copilot-product-question-log.md) | 产品问答日志（已融入 PRD） |

## 参考资料（按需读取）

| 目录 | 用途 |
|---|---|
| [reference/](reference/) | lark-cli 配置、Cognee embedding、Bitable 视图等 |
| [diagrams/](diagrams/) | 架构图、交互流和 benchmark loop |
| [assets/](assets/) | 静态资源 |

## 推荐阅读路线

### 人类快速理解产品

1. [human-product-guide.md](human-product-guide.md)
2. [manual-testing-guide.md](manual-testing-guide.md)
3. [productization/launch-polish-todo.md](productization/launch-polish-todo.md)
4. [productization/user-experience-todo.md](productization/user-experience-todo.md)
5. [productization/workflow-and-test-process.md](productization/workflow-and-test-process.md)
6. [demo-runbook.md](demo-runbook.md)
7. [benchmark-report.md](benchmark-report.md)

### Codex / Agent 后续执行

1. `AGENTS.md`
2. `README.md`
3. [productization/full-copilot-next-execution-doc.md](productization/full-copilot-next-execution-doc.md)
4. [productization/launch-polish-todo.md](productization/launch-polish-todo.md)
5. [productization/workflow-and-test-process.md](productization/workflow-and-test-process.md)
6. 当前任务直接相关的 contract

### 评审或复盘证据

1. [judge-10-minute-experience.md](judge-10-minute-experience.md)
2. [demo-runbook.md](demo-runbook.md)
3. [benchmark-report.md](benchmark-report.md)
4. [diagrams/README.md](diagrams/README.md)
5. [productization/prd-completion-audit-and-gap-tasks.md](productization/prd-completion-audit-and-gap-tasks.md)
6. [productization/handoffs/openclaw-runtime-evidence.md](productization/handoffs/openclaw-runtime-evidence.md)
7. [productization/handoffs/phase-a-storage-audit-handoff.md](productization/handoffs/phase-a-storage-audit-handoff.md)
8. [productization/handoffs/phase-d-live-embedding-handoff.md](productization/handoffs/phase-d-live-embedding-handoff.md)
9. [productization/handoffs/phase-e-no-overclaim-handoff.md](productization/handoffs/phase-e-no-overclaim-handoff.md)

## 当前不要这样读

- 不要默认读完整个 `archive/`。
- 不要把 `archive/plans/` 下的日期计划当成当前待办。
- 不要把 dry-run、demo replay、测试群 sandbox 写成生产 live。
