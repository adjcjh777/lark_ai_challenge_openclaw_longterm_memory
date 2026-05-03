# 项目文档导航

日期：2026-05-03（更新：九项 demo/pre-production completion gate 已用受控 Feishu live packet + Cognee long-run evidence 跑通）

## 先看这个

1. 当前项目已完成 MVP / Demo / Pre-production 本地闭环；2026-05-03 复核九项 productization completion gate 已通过。2026-05-04 新增 workspace ingestion pilot 的架构 ADR、本地 adapter 和 registry；它能做受控资源发现、candidate-only 路由、repeat-run skip / stale / revocation 统计，但仍不是生产全量 workspace ingestion。
2. 已完成的日期计划和 handoff 文档已归档到 `archive/` 和 `productization/handoffs/`，不再作为执行入口。
3. 当前代码和 `docs/productization/full-copilot-next-execution-doc.md` 是事实源。
4. 本项目由 Codex 完成主要代码和文档修改，人类接手时优先读产品指南和待办清单。
5. 读文档时要带着当前代码边界：受控测试群是 allowlist 模式；新群默认只进入 `pending_onboarding` 群策略，不记录消息内容，只有 reviewer/admin 显式 `/enable_memory` 后才会对该群非 `@Bot` 消息做静默 candidate 探测；OpenClaw gateway 本地路由也已补静默筛选入口；命中后默认不回群消息，审核卡片优先 DM/private 定向给相关 owner/reviewer；`@Bot` / 私聊才是主动交互路径；仍然不是全量群聊被动记忆或生产长期运行。

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
| [productization/deep-research-improvement-backlog.md](productization/deep-research-improvement-backlog.md) | 深研报告改进事项，聚焦指标口径、旧值泄漏、冲突更新和 retrieval 可解释性 |
| [productization/stable-memory-key-alias-design.md](productization/stable-memory-key-alias-design.md) | 稳定 memory key / alias 层设计，用于降低 subject normalization 和旧值泄漏风险 |
| [productization/real-feishu-controlled-expansion-checklist.md](productization/real-feishu-controlled-expansion-checklist.md) | 真实飞书受控扩样 gate，列出 smoke matrix、读回证据和凭据/资源 ID 阻塞 |
| [productization/product-demo-completion-checklist.md](productization/product-demo-completion-checklist.md) | 产品展示完成清单：四件事、8 步 demo 路线、真实证据采集和评委材料入口 |
| [productization/cross-platform-quick-deploy.md](productization/cross-platform-quick-deploy.md) | macOS / Linux / Windows 新机器快速部署到 demo / pre-production 验收状态 |
| [productization/handoffs/openclaw-feishu-completion-gate-handoff.md](productization/handoffs/openclaw-feishu-completion-gate-handoff.md) | 九项 demo/pre-production completion gate 的通过命令、证据路径和 no-overclaim 边界 |
| [productization/audit-read-only-live-gate.md](productization/audit-read-only-live-gate.md) | productized live 小步实施 gate：审计 read-only view，不宣称生产长期运行 |
| [productization/productized-live-long-run-plan.md](productization/productized-live-long-run-plan.md) | Productized live 长期运行方案；只定义 gate 和运行边界，不代表已上线 |
| [productization/workspace-ingestion-architecture-adr.md](productization/workspace-ingestion-architecture-adr.md) | Workspace ingestion ADR：lark-cli/API 选型、资源路由、记忆判断、共库与佐证模型 |
| [productization/document-writing-style-guide-opus-4-6.md](productization/document-writing-style-guide-opus-4-6.md) | 文档重写风格准则：按 Opus 4.6 的温和协作语气重写活跃文档，避免 4.7 风格 |

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
