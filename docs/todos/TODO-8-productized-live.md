# TODO-8：设计 productized live 长期运行方案

日期：2026-04-28
负责人：程俊豪
优先级：P2
状态：已完成（方案设计）

---

## 1. 目标

写清 Feishu Memory Copilot 从 demo/pre-production 升级为 productized live 的完整方案：部署、监控、回滚、权限后台、审计 UI 和运维边界。本阶段只做方案设计，不冒称已完成上线。

---

## 2. 当前状态分析

### 已完成

- Phase A Storage Migration + Audit Table：本地 SQLite schema version 2，有 tenant/org/visibility 字段和 audit table。
- Phase B OpenClaw Agent runtime 受控证据：三条 Copilot flow 全部 `ok=true`。
- Phase D live embedding gate：本机 Ollama 真实返回 1024 维。
- Phase E no-overclaim 审查：所有交付物口径一致。
- First-class OpenClaw 原生工具注册：7 个 `memory.*` 工具。
- OpenClaw Feishu websocket running 本机 staging 证据。
- 真实飞书权限映射本地闭环。
- Limited Feishu ingestion 本地底座。
- Review surface 可操作写回。

### 未完成

- 生产 DB 部署（当前是本地 SQLite）。
- 长期运行监控（当前只有 healthcheck）。
- 完整多租户后台。
- 生产级 card action 长期运行。
- 真实 Feishu DM 到本项目 first-class `fmc_*` / `memory.*` tool routing 的 live E2E 证据。
- 生产安装包和部署流程。
- 回滚和灾备方案。

---

## 3. 子任务清单

### 3.1 部署方案设计

| 子任务 | 说明 | 输出文件 | 验收标准 |
|---|---|---|---|
| [x] 8.1.1 生产 DB 选型 | SQLite -> PostgreSQL 迁移方案；托管 vs 自建 | `docs/productization/contracts/storage-contract.md` 更新 | 选型理由和边界写清 |
| [x] 8.1.2 部署架构图 | OpenClaw Agent + CopilotService + PostgreSQL + Cognee + Ollama | `docs/productization/productized-live-architecture.md` | 架构图可给新成员理解 |
| [x] 8.1.3 部署步骤文档 | 从零到可运行的完整步骤 | `docs/productization/deployment-runbook.md` | 新机器可按文档部署 |
| [x] 8.1.4 环境变量和配置管理 | 生产环境变量、密钥管理、配置模板 | `docs/productization/deployment-runbook.md` | 配置项清单完整 |
| [x] 8.1.5 Docker/容器化方案 | 可选的容器化部署 | `Dockerfile`、`docker-compose.yml` | 容器可启动 |

### 3.2 监控方案设计

| 子任务 | 说明 | 输出文件 | 验收标准 |
|---|---|---|---|
| [x] 8.2.1 监控指标定义 | 参考 audit-observability-contract 的 Metrics/Counters | `docs/productization/contracts/audit-observability-contract.md` 更新 | 指标清单完整 |
| [x] 8.2.2 监控采集方案 | 如何采集指标（日志解析 / Prometheus / 自建） | `docs/productization/monitoring-design.md` | 采集方案可行 |
| [x] 8.2.3 告警通道设计 | 告警发送到哪里（飞书群 / 邮件 / 短信） | `docs/productization/monitoring-design.md` | 告警可达 |
| [x] 8.2.4 Dashboard 设计 | 关键指标的可视化 | `docs/productization/monitoring-design.md` | Dashboard 可理解 |
| [x] 8.2.5 SLA 定义 | 可用性、延迟、错误率目标 | `docs/productization/monitoring-design.md` | SLA 可衡量 |

### 3.3 回滚和灾备方案

| 子任务 | 说明 | 输出文件 | 验收标准 |
|---|---|---|---|
| [x] 8.3.1 代码回滚流程 | 如何回滚到上一个可用版本 | `docs/productization/deployment-runbook.md` | 回滚步骤清晰 |
| [x] 8.3.2 数据库回滚流程 | migration 失败时如何回滚 | `docs/productization/contracts/migration-rfc.md` 更新 | 回滚步骤清晰 |
| [x] 8.3.3 数据备份策略 | 备份频率、保留周期、恢复流程 | `docs/productization/deployment-runbook.md` | 备份可恢复 |
| [x] 8.3.4 灾备切换方案 | 主库不可用时的 fallback | `docs/productization/deployment-runbook.md` | 切换方案可行 |

### 3.4 权限后台设计

| 子任务 | 说明 | 输出文件 | 验收标准 |
|---|---|---|---|
| [x] 8.4.1 多租户数据隔离 | tenant_id 级别的数据隔离方案 | `docs/productization/contracts/permission-contract.md` 更新 | 隔离方案清晰 |
| [x] 8.4.2 角色权限管理 | admin / reviewer / member 角色的增删改查 | `docs/productization/permission-admin-design.md` | 权限管理可行 |
| [x] 8.4.3 审批流程设计 | 谁能审批 candidate、审批规则 | `docs/productization/permission-admin-design.md` | 审批流程清晰 |
| [x] 8.4.4 数据删除和遗忘 | 用户要求删除记忆时的处理流程 | `docs/productization/contracts/permission-contract.md` 更新 | 删除流程完整 |

### 3.5 审计 UI 设计

| 子任务 | 说明 | 输出文件 | 验收标准 |
|---|---|---|---|
| [x] 8.5.1 审计查询界面需求 | 支持按时间、actor、event_type、tenant 查询 | `docs/productization/audit-ui-design.md` | 需求清单完整 |
| [x] 8.5.2 审计导出需求 | 支持 CSV/JSON 导出，用于合规审查 | `docs/productization/audit-ui-design.md` | 导出需求清晰 |
| [x] 8.5.3 审计 Dashboard 需求 | 审计事件趋势、异常检测 | `docs/productization/audit-ui-design.md` | Dashboard 需求清晰 |

### 3.6 运维流程设计

| 子任务 | 说明 | 输出文件 | 验收标准 |
|---|---|---|---|
| [x] 8.6.1 日常运维 checklist | 每日/每周/每月的运维检查项 | `docs/productization/ops-runbook.md` | checklist 可执行 |
| [x] 8.6.2 故障排查流程 | 常见故障的排查步骤 | `docs/productization/ops-runbook.md` | 排查步骤清晰 |
| [x] 8.6.3 扩缩容方案 | 流量增长时的扩缩容策略 | `docs/productization/ops-runbook.md` | 扩缩容可行 |
| [x] 8.6.4 版本升级流程 | OpenClaw、Cognee、Ollama 版本升级 | `docs/productization/ops-runbook.md` | 升级流程安全 |

### 3.7 Feishu Agent Tool Routing

| 子任务 | 说明 | 输出文件 | 验收标准 |
|---|---|---|---|
| [x] 8.7.1 分析当前 routing 问题 | 真实 DM 触发 OpenClaw 内置 `memory_search`，不是本项目 `memory.search` | `docs/productization/feishu-agent-routing-design.md` | 问题分析清晰 |
| [x] 8.7.2 设计 routing 方案 | 如何让 Agent 自然选择本项目工具 | `docs/productization/feishu-agent-routing-design.md` | 方案可行 |
| [x] 8.7.3 设计 fallback 方案 | routing 失败时的降级策略 | `docs/productization/feishu-agent-routing-design.md` | fallback 可行 |

---

## 4. 依赖关系

| 依赖项 | 说明 |
|---|---|
| Phase A-D 已完成 | 本地闭环已有 |
| Phase E no-overclaim 审查 | 口径一致 |
| audit-observability-contract.md | 监控指标参考 |
| storage-contract.md | 存储方案参考 |
| permission-contract.md | 权限方案参考 |
| migration-rfc.md | 迁移方案参考 |

---

## 5. 风险和注意事项

1. **不冒称已完成**：本 TODO 只做方案设计，不写成已上线。
2. **不绕过 CopilotCore**：任何方案都必须保持 CopilotService 作为唯一事实源。
3. **保持 candidate-only**：真实飞书来源仍只进 candidate，不自动 active。
4. **保持 permission fail-closed**：缺失或畸形 permission 必须 deny。
5. **不升级 OpenClaw 版本**：保持 2026.4.24，除非有明确升级计划。
6. **真实 ID 不写仓库**：chat_id、open_id、token 只在本机环境。

---

## 6. 验证命令

```bash
# 基础检查
python3 scripts/check_openclaw_version.py
python3 scripts/check_copilot_health.py --json
python3 scripts/check_demo_readiness.py --json

# 文档完整性检查
# 确认以下文件存在且内容完整：
ls -la docs/productization/productized-live-architecture.md
ls -la docs/productization/deployment-runbook.md
ls -la docs/productization/monitoring-design.md
ls -la docs/productization/permission-admin-design.md
ls -la docs/productization/audit-ui-design.md
ls -la docs/productization/ops-runbook.md
ls -la docs/productization/feishu-agent-routing-design.md

# 口径一致性检查
# README、handoff、飞书看板口径一致：已完成方案设计，未完成生产上线

# Git 检查
git diff --check
git status --short
```
