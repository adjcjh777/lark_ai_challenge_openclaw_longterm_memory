# 项目文档导航

日期：2026-04-28
阶段：产品后期打磨和上线前优化

## 先看这个

1. 当前项目已经完成 demo / pre-production 级别闭环，后续重点不是重复证明 MVP 能跑，而是补齐上线前的 OpenClaw 原生工具、飞书 websocket、真实权限、生产存储、审计和运维能力。
2. 初期构建、OMX 规划和后期打磨文档分开阅读；不要从旧 day 文档里倒推当前任务。
3. 当前代码和 `docs/productization/full-copilot-next-execution-doc.md` 是事实源；历史计划只作为证据和背景。
4. 本项目目前由 Codex 完成主要代码和文档修改，人类接手时优先读产品指南和待办清单，再看具体代码。

## 推荐阅读路线

### 人类快速理解产品

按这个顺序读，能最快理解为什么立项、现在做到哪里、接下来怎么用：

1. [human-product-guide.md](human-product-guide.md)
2. [productization/launch-polish-todo.md](productization/launch-polish-todo.md)
3. [productization/workflow-and-test-process.md](productization/workflow-and-test-process.md)
4. [demo-runbook.md](demo-runbook.md)
5. [benchmark-report.md](benchmark-report.md)

### Codex / OpenClaw 后续执行

后续开始任何产品化任务前，按这个顺序读：

1. `AGENTS.md`
2. `README.md`
3. [productization/full-copilot-next-execution-doc.md](productization/full-copilot-next-execution-doc.md)
4. [productization/launch-polish-todo.md](productization/launch-polish-todo.md)
5. [productization/workflow-and-test-process.md](productization/workflow-and-test-process.md)
6. 当前任务直接相关的 contract / runbook / handoff

### 评审或复盘证据

只想确认项目是否真的跑通过，读这些：

1. [productization/prd-completion-audit-and-gap-tasks.md](productization/prd-completion-audit-and-gap-tasks.md)
2. [productization/openclaw-runtime-evidence.md](productization/openclaw-runtime-evidence.md)
3. [productization/phase-a-storage-audit-handoff.md](productization/phase-a-storage-audit-handoff.md)
4. [productization/phase-d-live-embedding-handoff.md](productization/phase-d-live-embedding-handoff.md)
5. [productization/phase-e-no-overclaim-handoff.md](productization/phase-e-no-overclaim-handoff.md)

## 文档分区

### 1. 初期构建和 MVP 证据

这一组说明项目从初赛 demo 到 MVP 自证是怎么搭起来的。它们已经完成，不再作为当前待办入口。

| 文档 | 用途 |
|---|---|
| [feishu-memory-copilot-prd.md](feishu-memory-copilot-prd.md) | 产品最初的 PRD baseline：问题、用户、核心功能和指标。 |
| [feishu-memory-copilot-implementation-plan.md](feishu-memory-copilot-implementation-plan.md) | 历史主控计划和产品化参考。 |
| [plans/README.md](plans/README.md) | 日期计划和 handoff 索引；2026-05-05 及以前只作历史证据。 |
| [demo-runbook.md](demo-runbook.md) | 5 分钟 demo replay 和演示口径。 |
| [benchmark-report.md](benchmark-report.md) | recall、candidate、conflict、layer、prefetch、heartbeat 六类评测证据。 |
| [memory-definition-and-architecture-whitepaper.md](memory-definition-and-architecture-whitepaper.md) | 初赛白皮书和架构解释。 |
| [archive/](archive/) | 旧 day 文档和旧主控计划归档，只按需查。 |

### 2. OMX / RALPLAN 构建产物

这一组来自 OMX / RALPLAN 路线，用来把 MVP 推到完整产品路线。它们是计划和验收基线，不等于所有能力都已上线。

| 文档 | 用途 |
|---|---|
| [productization/complete-product-roadmap-prd.md](productization/complete-product-roadmap-prd.md) | 完整产品路线 PRD：阶段、决策、contract 和上线边界。 |
| [productization/complete-product-roadmap-test-spec.md](productization/complete-product-roadmap-test-spec.md) | 完整产品路线测试规格：分阶段验收、负例、E2E、no-overclaim。 |
| [plans/2026-05-08-ralph-plan-demo-readiness.md](plans/2026-05-08-ralph-plan-demo-readiness.md) | Demo readiness 聚合门禁的 Ralph 计划。 |
| [reference/hermes-agent-reference-notes.md](reference/hermes-agent-reference-notes.md) | Hermes 机制参考，借鉴 websocket、card action、memory 等思路。 |

说明：`.omx/` 是本地执行和上下文目录，不进入提交；仓库内可追踪副本以 `docs/productization/` 和 `docs/plans/` 下的文档为准。

### 3. 后期打磨和上线前优化

当前应主要阅读这一组。

| 文档 | 用途 |
|---|---|
| [productization/full-copilot-next-execution-doc.md](productization/full-copilot-next-execution-doc.md) | 当前产品化主控执行文档。 |
| [productization/launch-polish-todo.md](productization/launch-polish-todo.md) | 后续待办清单，按上线优先级排序。 |
| [productization/workflow-and-test-process.md](productization/workflow-and-test-process.md) | 后续工作流和测试流，每个任务完成前后按这里收口。 |
| [productization/feishu-staging-runbook.md](productization/feishu-staging-runbook.md) | 飞书 staging 和单监听规则。 |
| [productization/openclaw-runtime-evidence.md](productization/openclaw-runtime-evidence.md) | OpenClaw Agent runtime 受控证据和仍未完成边界。 |
| [productization/phase-e-no-overclaim-handoff.md](productization/phase-e-no-overclaim-handoff.md) | 当前 no-overclaim 审查完成证据。 |

### 4. 契约和参考资料

这些文档只在对应任务触达时读取。

| 目录 | 用途 |
|---|---|
| [productization/contracts/](productization/contracts/) | storage、permission、OpenClaw payload、audit、migration、negative permission 契约。 |
| [reference/](reference/) | lark-cli、本地 Cognee embedding、Bitable 视图等参考资料。 |
| [diagrams/](diagrams/) | 架构图、交互流和 benchmark loop。 |

## 当前不要这样读

- 不要默认读完整个 `docs/archive/`。
- 不要把 2026-05-05 及以前的日期计划当成当前待办。
- 不要把 dry-run、demo replay、测试群 sandbox、live embedding gate 写成生产 live。
- 不要把旧 CLI / Bot handler 当成新的主架构；它们只是 fallback 和回归面。
