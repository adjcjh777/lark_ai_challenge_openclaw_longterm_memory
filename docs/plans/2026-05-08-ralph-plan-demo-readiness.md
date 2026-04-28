# 2026-05-08 Ralph Plan：Demo-ready + Pre-production Readiness

## 先看这个

1. 这份计划的目标是把当前 Phase 6 的“可检查、可初始化、可诊断”推进到“可演示、可本地试运行、具备上线前门禁”。
2. 本阶段仍然不做生产部署、不真实发飞书群消息、不宣称 productized live，也不改 OpenClaw `2026.4.24` 锁定版本。
3. 最短路径是先让 demo replay 的 step-level 结果全绿，再把 provider / Cognee 不可用时的诊断信息、OpenClaw 示例契约和 README 入口收口。
4. Ralph 主控可以派生多个 Codex native subagents 并行推进；每个子代理只写自己的文件范围，避免多人同时改共享核心。
5. 最终完成必须有 fresh verification evidence 和 architect verification `APPROVED`。

## 当前事实源

- Phase 6 healthcheck 已可运行：`python3 scripts/check_copilot_health.py` 当前可输出 `ok=true`、`fail=0`。
- OpenClaw 开发版本仍锁定为 `2026.4.24`，每次验收前继续运行 `python3 scripts/check_openclaw_version.py`。
- `python3 scripts/demo_seed.py --json-output reports/demo_replay.json` 可以运行并写出报告，但 demo replay 的 step-level 仍可能暴露失败项，需要在本阶段锁成全绿。
- 当前代码主线仍是 OpenClaw-native Feishu Memory Copilot；Cognee 是 memory substrate，但本阶段只做窄 adapter、fallback 和诊断，不做生产级 Cognee service。
- 飞书共享看板只在主控最终验收后统一同步，避免多个子代理重复创建或覆盖记录。

## 总目标

本阶段完成时，应该能稳定回答：

```text
可以拉起来运行。
本地 healthcheck 通过。
Demo replay step-level 全绿。
provider / Cognee 不可用时不会崩，会给明确 fallback 或修复建议。
README 顶部有队友可直接执行的命令。
当前仍不是生产部署，也没有真实飞书推送。
Architect verification APPROVED。
代码已提交并 push。
```

## Ralph 主控职责

Ralph leader 只做集成、冲突处理和最终门禁，不把所有工作重新集中到一个人手里。

启动前先运行：

```bash
python3 scripts/check_openclaw_version.py
git status --short
```

第一轮并行派生：

- Agent A：Demo Replay Green Owner
- Agent B：Provider / Cognee Diagnostic Owner
- Agent C：OpenClaw Contract / Example Owner
- Agent D：Local Run / Readiness Command Owner

第二轮串行收口：

- Agent E：Docs / Handoff / Board Owner
- Ralph leader：完整验证、architect verification、看板同步、commit、push

共享核心冻结规则：

- `memory_engine/copilot/service.py` 和 `memory_engine/copilot/tools.py` 默认冻结。
- 如果 demo replay 失败必须改共享核心，只能由 Ralph leader 单线程处理；其他子代理暂停触碰相关测试。
- 不允许任何子代理改 OpenClaw 锁定版本。

## Agent A：Demo Replay Green Owner

目标：让 demo replay 从“脚本可运行”变成“演示步骤全绿”。

写入范围：

- `scripts/demo_seed.py`
- `tests/test_demo_seed.py` 或新增同等 demo replay 测试文件

不得修改：

- `memory_engine/copilot/service.py`
- `memory_engine/copilot/tools.py`
- `agent_adapters/openclaw/memory_tools.schema.json`
- README / handoff 文档

任务：

1. 给 `memory.search`、`memory.explain_versions`、`memory.prefetch`、`heartbeat.review_due` 的 demo payload 补齐合法 `current_context.permission`。
2. 让 demo replay 的 compact summary 中所有 `steps[].ok` 都为 `true`。
3. candidate review / heartbeat 只能走 `CopilotService` 或 `handle_tool_request()`，不能直接绕过工具契约改 repository 状态。
4. `tests.test_demo_seed` 必须直接断言 replay 输出中的每个 `steps[].ok` 都为 `true`，避免“脚本退出 0 但步骤失败”再次发生。

验收命令：

```bash
python3 scripts/demo_seed.py --json-output reports/demo_replay.json
python3 -m unittest tests.test_demo_seed
```

## Agent B：Provider / Cognee Diagnostic Owner

目标：让 Cognee adapter 和 embedding provider 的不可用状态更可诊断，适合演示前自查。

写入范围：

- `scripts/check_embedding_provider.py`
- `scripts/spike_cognee_local.py`
- `memory_engine/copilot/cognee_adapter.py`
- `memory_engine/copilot/embeddings.py`
- `tests/test_copilot_cognee_adapter.py`
- 可新增：`tests/test_embedding_provider_health.py`

不得修改：

- `scripts/demo_seed.py`
- OpenClaw schema / examples
- README / handoff 文档

任务：

1. 不新增依赖，优先使用已有 fallback。
2. provider 不可用时必须返回 `not_configured`、`warning`、`fallback_used` 或明确错误，不能静默成功或直接崩溃。
3. `check_embedding_provider.py` 支持默认配置检查和可选 live check。
4. 如果运行 live Cognee / embedding / Ollama 验证，结束前必须执行 `ollama ps`，必要时只停止本项目拉起的模型。

验收命令：

```bash
python3 scripts/check_embedding_provider.py
python3 -m unittest tests.test_copilot_cognee_adapter
ollama ps
```

## Agent C：OpenClaw Contract / Example Owner

目标：保证 OpenClaw 工具契约和 examples 能被 healthcheck、demo replay 和后续 Agent 稳定消费。

写入范围：

- `agent_adapters/openclaw/memory_tools.schema.json`
- `agent_adapters/openclaw/examples/*.json`
- `tests/test_copilot_schemas.py`
- `tests/test_copilot_tools.py`

不得修改：

- `memory_engine/copilot/service.py`
- `memory_engine/copilot/tools.py`
- `scripts/demo_seed.py`
- README / handoff 文档

任务：

1. 不改 OpenClaw 版本锁。
2. schema/tool version 或等价版本信息继续可被 healthcheck 读取。
3. examples 中所有正常 tool request 都带合法 permission context。
4. permission deny 示例继续覆盖 missing / malformed permission fail-closed。

验收命令：

```bash
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools
python3 scripts/check_copilot_health.py --json
```

## Agent D：Local Run / Readiness Command Owner

目标：交付一个“本地拉起 / 演示前检查”的聚合入口。

写入范围：

- `scripts/check_demo_readiness.py`
- `tests/test_copilot_healthcheck.py`
- `tests/test_demo_readiness.py`

不得修改：

- `scripts/demo_seed.py`
- provider / Cognee 文件
- OpenClaw schema / examples
- README / handoff 文档

任务：

1. 聚合 OpenClaw version、Phase 6 healthcheck、demo replay summary、provider config check。
2. 输出人类可读文本，也支持 `--json`。
3. 状态值统一使用：`pass`、`fail`、`warning`、`skipped`、`not_configured`、`fallback_used`。
4. 如果 demo replay step 失败，整体应 fail，并列出失败 step 名称和下一步建议。
5. 明确声明这是 demo/pre-production readiness，不是生产部署。
6. `tests.test_demo_readiness` 必须断言：任一 `steps[].ok=false` 都会让 readiness 整体失败。

验收命令：

```bash
python3 scripts/check_demo_readiness.py
python3 scripts/check_demo_readiness.py --json
python3 -m unittest tests.test_demo_readiness
```

## Agent E：Docs / Handoff / Board Owner

目标：把队友如何运行、怎么判断通过、仍未实现什么写清楚。

写入范围：

- `README.md`
- `docs/plans/2026-05-07-handoff.md`
- 可新增：`docs/plans/2026-05-08-demo-readiness-handoff.md`

不得修改：

- Python 代码
- OpenClaw schema / examples
- tests

任务：

1. README 顶部任务区加入“本地拉起 / 演示前检查”的明确入口。
2. 写清推荐命令顺序。
3. 文案不得说成生产部署、真实 live、完整 audit migration 或 productized live。
4. handoff 写清已完成、怎么运行、仍未实现、剩余风险。
5. 看板只在 Ralph leader 最终验收后统一同步并读回确认。

验收命令：

```bash
git diff --check
```

## 总体验收命令

Ralph leader 在合并所有子代理结果后运行：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_copilot_health.py
python3 scripts/demo_seed.py --json-output reports/demo_replay.json
python3 scripts/check_demo_readiness.py
python3 scripts/check_demo_readiness.py --json
git diff --check
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_demo_seed tests.test_demo_readiness
python3 -m unittest tests.test_copilot_permissions tests.test_copilot_schemas tests.test_copilot_tools tests.test_copilot_healthcheck
python3 -m unittest tests.test_copilot_cognee_adapter tests.test_copilot_prefetch tests.test_copilot_heartbeat
python3 -m unittest discover tests
ollama ps
```

其中 `python3 scripts/check_demo_readiness.py` 是必交付门禁，不是可选项。它必须显式检查 demo replay 的每个 step；只要任一 `steps[].ok=false`，readiness 整体必须失败。

## Architect Verification Gate

完成前必须派生 architect 子代理做最终检查，检查点：

- 子代理写入范围是否互不干扰。
- demo readiness 是否没有越界成生产部署。
- permission fail-closed 是否仍保留 request_id / trace_id / reason_code。
- provider / Cognee 不可用时是否明确 fallback 或修复建议。
- 文档是否没有 productized live 过度宣称。

只有 architect 返回 `APPROVED` 后，才允许同步看板、commit 和 push。

## 今日不做

- 不做生产部署。
- 不真实发飞书群消息。
- 不做完整生产调度服务。
- 不做完整 audit table migration。
- 不做完整多租户后台。
- 不做复杂个性化推荐。
- 不做全量 Feishu workspace ingestion。
- 不改 OpenClaw `2026.4.24` 锁定版本。
- 不把 readiness 写成 productized live 宣称。
