# Harness Quality Score

日期：2026-04-29  
用途：给仓库的 agent harness 做可复查评分。分数不是对产品能力的评分，而是衡量代理能否稳定理解、修改、验证这个代码库。

## 1. 当前评分

| 维度 | 分数 | 证据 | 下一步 |
|---|---:|---|---|
| 入口地图 | 4/5 | `AGENTS.md` 已从长手册改成短入口，并指向详细 contract | 后续保持 180 行以内 |
| 文档事实源 | 4/5 | `docs/productization/agent-execution-contract.md`、主控执行文档、PRD audit 形成事实源链 | 继续减少历史日期计划对新任务的干扰 |
| 机械检查 | 3/5 | 新增 `scripts/check_agent_harness.py` 和 `tests/test_agent_harness.py` | 逐步增加架构边界检查和 no-overclaim 检查 |
| 本地验证回路 | 4/5 | OpenClaw version、healthcheck、demo readiness、benchmark、harness check 都有命令 | 将最常用 gate 收敛成一个总入口 |
| 技术债回收 | 3/5 | 新增垃圾回收清单，旧 Bot / legacy fallback 已有边界 | 后续给 legacy 路径增加更明确的 deprecation gate |
| 可观测性 | 4/5 | request_id、trace_id、permission_decision、audit table 已是工具合同的一部分 | 真实 Feishu DM live E2E 后补端到端证据 |

当前总评：**22/30**。

## 2. 评分标准

### 入口地图

- 5：入口短、稳定、只做路由；所有详细规则都有明确文档落点。
- 3：入口能用，但仍包含大量手册式内容。
- 1：代理需要在多个历史文档里猜主线。

### 文档事实源

- 5：当前状态、边界、handoff、验收命令互相一致。
- 3：主要文档一致，但历史计划容易误导执行。
- 1：README、PRD、handoff、代码状态互相冲突。

### 机械检查

- 5：关键规则都能被脚本或单测检查。
- 3：已有少数结构检查，但很多规则仍靠人工记忆。
- 1：没有可运行的 harness 检查。

### 本地验证回路

- 5：常用 gate 一条命令即可覆盖，并能清楚区分 warning / fail。
- 3：命令齐全但分散。
- 1：验证依赖人工试错。

### 技术债回收

- 5：旧路径有明确停用条件和迁移计划。
- 3：旧路径有边界，但还会被新任务触发。
- 1：旧路径和新主线混在一起。

### 可观测性

- 5：每条关键链路都有 request_id、trace_id、permission_decision、audit 和读回证据。
- 3：核心路径有 metadata，但端到端证据仍不完整。
- 1：运行结果只能靠日志猜。
