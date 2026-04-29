# Technical Debt Garbage Collection

日期：2026-04-29  
用途：把 harness engineering 里的“定期清理技术债”落到本仓库。这里不记录所有 bug，只记录会误导代理执行、抢走主线或破坏验收口径的债务。

## 1. 清理原则

1. 先清理会误导代理的入口，再清理实现细节。
2. 旧路径可以保留，但必须写清是 fallback / reference。
3. 每条债务都要有停止条件：什么时候可以删、什么时候只能冻结。
4. 不能为了清理而重写已稳定的 Copilot Core。
5. 清理完成后必须有脚本或测试防回退。

## 2. 当前技术债清单

| 债务 | 风险 | 当前处理 | 完成标准 |
|---|---|---|---|
| 过长 `AGENTS.md` | 新代理读取入口时把历史规则、主线、验证命令混成一个手册 | 已改成入口地图，详细规则移到 `agent-execution-contract.md` | `scripts/check_agent_harness.py` 保持通过 |
| 历史日期计划过多 | 代理可能按日期误判任务未完成，重复实现旧 slice | `AGENTS.md` 和 contract 明确只有用户点名日期时才读 | 后续可给 `docs/plans/` 增加归档索引 |
| legacy CLI / Bot fallback | 新功能可能绕开 `CopilotService` | AGENTS/contract 明确旧实现只做 fallback | 新入口默认走 `handle_tool_request()` / `CopilotService` |
| productized live wording | 容易把 sandbox、dry-run、staging 写成生产上线 | no-overclaim 边界写入 AGENTS、contract、README | 后续增加 no-overclaim 文案扫描 |
| 分散验证命令 | 代理容易只跑局部测试 | harness check 成为所有提交前 gate | 后续收敛一个总验证脚本 |

## 3. 后续建议

### P0：no-overclaim scanner

新增脚本扫描 README、handoff、benchmark report、白皮书里的高风险措辞。允许“不能说生产部署已完成”这种否定边界，但拒绝无边界的完成宣称。

完成标准：

```bash
python3 scripts/check_agent_harness.py
python3 -m unittest tests.test_agent_harness
```

### P1：legacy entrypoint inventory

给旧 CLI、旧 Bot、day benchmark 建一个 inventory，明确每个入口是 active、fallback、reference 还是 deprecated。

完成标准：`docs/harness/LEGACY_ENTRYPOINTS.md` 列出入口、调用方、是否允许新任务触达。

### P1：single validation command

把当前散落的常用 gate 收敛成一个只读验证命令，输出 JSON 和人类可读摘要。

完成标准：

```bash
python3 scripts/check_project_readiness.py --json
```

### P2：architecture boundary scanner

把“Cognee 只能通过 adapter”“Feishu live 入口必须进 CopilotService”“真实 Feishu 来源只能 candidate-only”等边界逐步固化成 AST 或文本结构检查。

完成标准：新增检查不会对现有合法测试 fixture 误报。
