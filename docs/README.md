# 项目文档导航

日期：2026-04-28（更新：文档收敛后）

## 先看这个

1. 当前项目已完成 MVP / Demo / Pre-production 本地闭环，后续重点是补齐真实飞书集成和产品化硬缺口。
2. 已完成的日期计划和 handoff 文档已归档到 `archive/` 和 `productization/handoffs/`，不再作为执行入口。
3. 当前代码和 `docs/productization/full-copilot-next-execution-doc.md` 是事实源。
4. 本项目由 Codex 完成主要代码和文档修改，人类接手时优先读产品指南和待办清单。

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

### 工作流和人类入口（2 个）

| 文档 | 用途 |
|---|---|
| [productization/workflow-and-test-process.md](productization/workflow-and-test-process.md) | 工作流和测试流程规范 |
| [human-product-guide.md](human-product-guide.md) | 人类快速理解产品 |

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
| [demo-runbook.md](demo-runbook.md) | 5 分钟 demo replay 演示脚本 |
| [benchmark-report.md](benchmark-report.md) | 六类评测证据 |
| [memory-definition-and-architecture-whitepaper.md](memory-definition-and-architecture-whitepaper.md) | 初赛白皮书 |
| [feishu-memory-copilot-prd.md](feishu-memory-copilot-prd.md) | 产品 baseline PRD |

## 已归档（不作为执行入口）

| 目录 | 内容 |
|---|---|
| [productization/handoffs/](productization/handoffs/) | 14 个已完成的 handoff / evidence / runbook |
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
2. [productization/launch-polish-todo.md](productization/launch-polish-todo.md)
3. [productization/user-experience-todo.md](productization/user-experience-todo.md)
4. [productization/workflow-and-test-process.md](productization/workflow-and-test-process.md)
5. [demo-runbook.md](demo-runbook.md)
6. [benchmark-report.md](benchmark-report.md)

### Codex / Agent 后续执行

1. `AGENTS.md`
2. `README.md`
3. [productization/full-copilot-next-execution-doc.md](productization/full-copilot-next-execution-doc.md)
4. [productization/launch-polish-todo.md](productization/launch-polish-todo.md)
5. [productization/workflow-and-test-process.md](productization/workflow-and-test-process.md)
6. 当前任务直接相关的 contract

### 评审或复盘证据

1. [productization/prd-completion-audit-and-gap-tasks.md](productization/prd-completion-audit-and-gap-tasks.md)
2. [productization/handoffs/openclaw-runtime-evidence.md](productization/handoffs/openclaw-runtime-evidence.md)
3. [productization/handoffs/phase-a-storage-audit-handoff.md](productization/handoffs/phase-a-storage-audit-handoff.md)
4. [productization/handoffs/phase-d-live-embedding-handoff.md](productization/handoffs/phase-d-live-embedding-handoff.md)
5. [productization/handoffs/phase-e-no-overclaim-handoff.md](productization/handoffs/phase-e-no-overclaim-handoff.md)

## 当前不要这样读

- 不要默认读完整个 `archive/`。
- 不要把 `archive/plans/` 下的日期计划当成当前待办。
- 不要把 dry-run、demo replay、测试群 sandbox 写成生产 live。
