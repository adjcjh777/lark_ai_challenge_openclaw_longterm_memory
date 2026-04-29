# Feishu Memory Copilot 主 TODO

日期：2026-04-28
目标：从 MVP / Demo / Pre-production 升级为完整可用的产品化 Copilot

---

## 文档整理（已完成）

- [x] 梳理文档依赖关系和时间线
- [x] 将 14 个已完成 handoff / evidence / runbook 移入 `productization/handoffs/`
- [x] 将 22 个已完成日期计划移入 `archive/plans/`
- [x] 将旧主控计划和问答日志移入 `archive/`
- [x] 更新 `docs/README.md` 文档导航，收敛活跃入口到 15 个

---

## P0 - 核心硬缺口（比赛核心竞争力）

### TODO-1: 打通真实飞书 DM 到 first-class memory.* tool routing

> 详细子任务文档：[todos/TODO-1-feishu-dm-routing.md](todos/TODO-1-feishu-dm-routing.md)（518 行，8 个子任务）

- [ ] 分析 OpenClaw Agent 当前 tool dispatch 机制，理解为什么真实 DM 走了内置 `memory_search`
- [ ] 修改 OpenClaw plugin 配置或 Agent prompt，使真实飞书消息优先选择本项目 `memory.search` 等工具
- [ ] 端到端验证：真实飞书 DM → OpenClaw Agent → `memory.search` → `handle_tool_request()` → `CopilotService` → 返回结果
- [ ] 确认回复保留 request_id、trace_id、permission_decision
- [ ] 写测试覆盖新路由路径
- [ ] 更新 handoff 文档

**涉及文件**：`agent_adapters/openclaw/plugin/`、`memory_engine/copilot/openclaw_tool_runner.py`
**完成标准**：真实飞书 DM 进入 OpenClaw Agent 后自然选择本项目 memory 工具

### TODO-2: 接真实 Feishu API 拉取和扩充样本

> 详细子任务文档：[todos/TODO-2-feishu-api-pull.md](todos/TODO-2-feishu-api-pull.md)（584 行，6 个子任务）

- [ ] 接通飞书任务 API，从真实任务中提取文本进入 candidate-only pipeline
- [ ] 接通飞书会议 API，从真实会议纪要中提取文本
- [ ] 接通 Bitable API，从真实多维表格记录中提取文本
- [ ] 实现 API 调用失败的 fallback 机制（不冒称 live 成功）
- [ ] 扩充人工复核样本集（每类来源至少 10 条真实样本）
- [ ] 确认所有真实来源仍只进入 candidate，不自动 active
- [ ] 写测试覆盖 API 调用和 fallback 路径

**涉及文件**：`memory_engine/document_ingestion.py`、`memory_engine/copilot/feishu_live.py`、`memory_engine/bitable_sync.py`
**完成标准**：真实飞书来源数据通过 API 拉取进入 candidate-only pipeline

### TODO-3: 扩大 Benchmark 规模

> 详细子任务文档：[todos/TODO-3-expand-benchmark.md](todos/TODO-3-expand-benchmark.md)（411 行，6 个子任务）

- [ ] recall 样例从 10 扩充到 30+（覆盖更多真实飞书表达）
- [ ] conflict 样例从 12 扩充到 30+
- [ ] prefetch 样例从 6 扩充到 20+
- [ ] heartbeat 样例从 7 扩充到 20+
- [ ] 新增真实飞书消息样本（非合成数据）
- [ ] 确保不删除已有的难例
- [ ] 重新跑全量 benchmark 并更新 benchmark-report.md

**涉及文件**：`benchmarks/copilot_*.json`、`docs/benchmark-report.md`
**完成标准**：总样例 200+，六类评测全部通过

---

## P1 - 产品化缺口

### TODO-4: 配置真实 Cognee 运行

> 详细子任务文档：[todos/TODO-4-real-cognee.md](todos/TODO-4-real-cognee.md)（181 行，5 个子任务）

- [ ] 安装并配置 Cognee 本地实例
- [ ] 验证 `cognee.add` → `cognee.cognify` → `cognee.search` 完整链路
- [ ] 验证 confirm 后 curated memory 同步到 Cognee
- [ ] 验证 reject 后 withdrawal 正确执行
- [ ] 验证 Cognee 不可用时 repository fallback 正确触发
- [ ] healthcheck 中 `cognee_adapter.status` 从 `fallback_used` 变为 `pass`
- [ ] 写测试覆盖真实 Cognee 链路

**涉及文件**：`memory_engine/copilot/cognee_adapter.py`、`memory_engine/copilot/retrieval.py`
**完成标准**：Cognee adapter 真实同步和检索，healthcheck pass

### TODO-5: 配置真实 Embedding 服务

> 详细子任务文档：[todos/TODO-5-real-embedding.md](todos/TODO-5-real-embedding.md)（337 行，8 个子任务）

- [ ] 启动 Ollama + qwen3-embedding:0.6b-fp16 作为长期 embedding 服务
- [ ] 替换 DeterministicEmbeddingProvider 为真实 Ollama embedding
- [ ] 验证向量维度 1024 和 cosine similarity 计算正确
- [ ] 验证 retrieval 走真实向量搜索
- [ ] healthcheck 中 `embedding_provider.status` 从 `warning` 变为 `pass`
- [ ] 写测试覆盖真实 embedding 链路

**涉及文件**：`memory_engine/copilot/embeddings.py`、`memory_engine/copilot/retrieval.py`
**完成标准**：embedding provider 真实运行，healthcheck pass

### TODO-6: 补充审计可观测性

> 详细子任务文档：[todos/TODO-6-audit-observability.md](todos/TODO-6-audit-observability.md)（127 行，15 个子任务）

- [x] 验证 `memory.search` 审计覆盖 - allow/deny 三种决策都写入 `memory_audit_events`
- [x] 验证 `memory.explain_versions` 审计覆盖
- [x] 验证 `memory.prefetch` 审计覆盖
- [x] 验证 Feishu review card action 审计覆盖（通过 `feishu_events.py` 路由到 confirm/reject）
- [x] 验证 source revoked/deleted 审计覆盖
- [x] 实现审计查询脚本 `scripts/query_audit_events.py`（支持按时间范围、event_type、actor_id、tenant_id 查询，--json 输出）
- [x] 实现审计导出功能（支持 CSV/JSON 导出）
- [x] 实现审计计数摘要（--summary 按 event_type、permission_decision、tenant_id 聚合）
- [x] 定义告警阈值（连续 permission deny >= 5、ingestion 失败率 > 10%、deny 比率 > 30%）
- [x] 实现告警检查脚本 `scripts/check_audit_alerts.py`
- [x] 告警输出格式 - 结构化 JSON
- [x] 验证 audit 日志不含 token/secret - `tests/test_audit_log_sanitization.py`
- [x] 验证 deny 日志不含 raw private memory
- [x] 验证 `redacted_fields` 只记录字段名
- [x] 编写停机流程文档 - `docs/productization/feishu-staging-runbook.md`
- [x] 编写审计数据回滚说明
- [x] 编写紧急降级流程
- [x] 更新 audit-observability-contract.md

**涉及文件**：`memory_engine/copilot/healthcheck.py`、`scripts/query_audit_events.py`、`scripts/check_audit_alerts.py`、`tests/test_audit_log_sanitization.py`、`docs/productization/feishu-staging-runbook.md`、`docs/productization/contracts/audit-observability-contract.md`
**完成标准**：audit 可查询、healthcheck 能看到运维指标、告警检查可运行、日志脱敏测试通过

### TODO-7: 扩充真实飞书记忆数据

> 详细子任务文档：[todos/TODO-7-expand-memory-data.md](todos/TODO-7-expand-memory-data.md)（137 行，18 个子任务）

- [ ] 从飞书测试群历史消息中提取 50+ 条候选记忆
- [ ] 从飞书文档中提取 30+ 条候选记忆
- [ ] 人工审核并 confirm 有价值的候选
- [ ] 确保数据库中 active memory 达到 100+ 条
- [ ] 验证 search 在真实数据上的召回质量

**涉及文件**：`memory_engine/document_ingestion.py`、`data/memory.sqlite`
**完成标准**：active memory 100+ 条，search 召回质量可接受

---

## P2 - 工程化缺口

### TODO-8: 设计 productized live 长期运行方案

> 详细子任务文档：[todos/TODO-8-productized-live.md](todos/TODO-8-productized-live.md)（157 行，28 个子任务）

- [ ] 写清部署方案（SQLite → PostgreSQL 迁移路径）
- [ ] 复赛后补生产级图谱存储方案：SQLite 图谱账本仅保留 L0/local staging；L1/L2 先做 PostgreSQL graph ledger pilot；多跳图查询成为主路径后再评估 Neo4j / ArangoDB / Cognee graph projection
- [ ] 写清监控方案（日志、指标、告警）
- [ ] 写清回滚方案
- [ ] 写清权限后台设计
- [ ] 写清审计 UI 设计
- [ ] 写清运维边界

**涉及文件**：`docs/productization/`
**完成标准**：产品化方案文档完成

### TODO-9: 收敛文档入口（已完成）

- [x] 梳理文档依赖关系
- [x] 归档已完成的 handoff 和日期计划
- [x] 更新 docs/README.md 导航

### TODO-10: 添加 CI/CD 管道

> 详细子任务文档：[todos/TODO-10-cicd-pipeline.md](todos/TODO-10-cicd-pipeline.md)（229 行，25 个子任务）

- [x] 配置 GitHub Actions workflow（`.github/workflows/ci.yml`）
- [x] 自动运行 `python3 scripts/check_openclaw_version.py`
- [x] 自动运行 `python3 -m compileall memory_engine scripts`
- [x] 自动运行 `python3 -m unittest discover tests`
- [x] ruff lint/format 检查
- [x] mypy type check
- [x] coverage.py 覆盖率检查（阈值 70%）
- [x] pip-audit 依赖扫描
- [x] `python -m build` 构建验证
- [x] OpenClaw schema 和插件验证
- [ ] Staging / Production 部署流程
- [ ] 自动化版本号管理
- [ ] 自动运行 `python3 scripts/check_copilot_health.py --json`
- [ ] 自动运行 benchmark

**涉及文件**：`.github/workflows/`
**完成标准**：push 时自动运行测试和健康检查

### TODO-11: 使用 Codex 进行代码审核

> 详细审核报告：[todos/TODO-11-codex-code-review.md](todos/TODO-11-codex-code-review.md)（Codex gpt5.3codex-high 生成）

- [ ] 审核 CopilotService 核心逻辑
- [ ] 审核权限门控实现
- [ ] 审核治理状态机实现
- [ ] 审核检索链路实现
- [ ] 审核 OpenClaw 插件实现
- [ ] 修复发现的问题

**涉及文件**：`memory_engine/copilot/*.py`、`agent_adapters/openclaw/`
**完成标准**：代码审核完成，关键问题修复

---

## 本阶段不用做

- 生产部署
- 多租户企业后台
- Web 审计 UI
- 真实权限后台
- 大规模压测
- 长期在线 embedding 服务（作为独立基础设施）

---

## 进度跟踪

| 任务 | 状态 | 详细文档 | 完成时间 |
|---|---|---|---|
| 文档整理 | ✅ 已完成 | - | 2026-04-28 |
| TODO-1: Feishu DM routing | ⬜ 待开始 | [518行](todos/TODO-1-feishu-dm-routing.md) | - |
| TODO-2: 真实 Feishu API | ⬜ 待开始 | [584行](todos/TODO-2-feishu-api-pull.md) | - |
| TODO-3: 扩大 Benchmark | ⬜ 待开始 | [411行](todos/TODO-3-expand-benchmark.md) | - |
| TODO-4: 真实 Cognee | ⬜ 待开始 | [181行](todos/TODO-4-real-cognee.md) | - |
| TODO-5: 真实 Embedding | ⬜ 待开始 | [337行](todos/TODO-5-real-embedding.md) | - |
| TODO-6: 审计可观测性 | ✅ 已完成 | [127行](todos/TODO-6-audit-observability.md) | 2026-04-28 |
| TODO-7: 扩充记忆数据 | ⬜ 待开始 | [137行](todos/TODO-7-expand-memory-data.md) | - |
| TODO-8: productized live | ⬜ 待开始 | [157行](todos/TODO-8-productized-live.md) | - |
| TODO-9: 文档收敛 | ✅ 已完成 | - | 2026-04-28 |
| TODO-10: CI/CD | 🔄 进行中 | [229行](todos/TODO-10-cicd-pipeline.md) | 2026-04-28 |
| TODO-11: Codex 代码审核 | 🔄 进行中 | [审核报告](todos/TODO-11-codex-code-review.md) | - |
