# Phase B OpenClaw Runtime Evidence

日期：2026-04-28  
阶段：Phase B 真实 OpenClaw Agent Runtime 验收  
结论：已完成受控 runtime 验收；后续已补 `memory.*` first-class OpenClaw 原生工具注册本机证据；仍不宣称生产部署、全量飞书空间接入或 Feishu websocket running。

## 先看这个

1. 今天补的是 OpenClaw Agent runtime 证据，不是再做一个 demo replay。
2. 真实 OpenClaw Agent 已通过 `exec` 工具运行仓库内证据脚本，脚本再进入 `handle_tool_request()` 和 `CopilotService`。
3. 三条必需 flow 已通过：历史决策召回、candidate 创建后确认、任务前 `memory.prefetch`。
4. 判断做对：每条 flow 都有 `request_id`、`trace_id` 和 `permission_decision.decision=allow`。
5. 遇到问题记录：OpenClaw Feishu websocket 当前 health 仍没有 `running=true` 证据，所以这次不宣称 OpenClaw websocket 已 owns bot；Feishu 测试群仍走既有 live sandbox 证据。

## 执行前检查

```bash
date '+%Y-%m-%d %H:%M:%S %Z (%z)'
python3 scripts/check_openclaw_version.py
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
openclaw health --json --timeout 5000
```

结果摘要：

- 当前机器时间：`2026-04-28 13:10:41 CST (+0800)`。
- OpenClaw version OK：`2026.4.24`。
- 单监听 preflight：通过；只看到 `openclaw-gateway`，没有 repo 内 lark-cli listener 冲突。
- OpenClaw health：`ok=true`；Feishu channel configured/enabled，credential probe OK，botName 为 `Feishu Memory Engine bot`；但 `channels.feishu.running=false`。

## Runtime Evidence

先用最小 ping 确认 OpenClaw Agent runtime 可执行：

```bash
openclaw agent --agent main --message '请只回复：OpenClaw runtime ping' --json --timeout 60
```

结果摘要：

- `runId=8099a091-89cd-49de-a48e-a74743d9c4f7`
- `status=ok`
- `provider=rightcode`
- `model=gpt-5.3-codex`
- `runner=embedded`
- assistant 输出：`OpenClaw runtime ping`

随后让 OpenClaw Agent 在本仓库执行 Phase B 证据脚本：

```bash
openclaw agent --agent main --message '你在 /Users/junhaocheng/feishu_ai_challenge。请用 exec 工具运行这个命令：python3 scripts/openclaw_runtime_evidence.py --json-output reports/openclaw_runtime_evidence_agent.json。然后只基于命令输出，用中文列出三条 flow 的 name、tool、ok、request_id、trace_id、permission_decision.decision。不要修改文件。' --json --timeout 120
```

结果摘要：

- `runId=b252f11e-b49d-495c-a14f-0b823a888a5e`
- `status=ok`
- `provider=rightcode`
- `model=gpt-5.3-codex`
- `runner=embedded`
- `toolSummary.calls=1`
- `toolSummary.tools=["exec"]`
- `toolSummary.failures=0`
- 证据 JSON 写入 `reports/openclaw_runtime_evidence_agent.json`，该目录已被 `.gitignore` 忽略，不提交真实运行产物。

## 三条 Flow

| Flow | OpenClaw runtime 入口 | Copilot tool | 结果 | request_id | trace_id | permission |
|---|---|---|---|---|---|---|
| historical_decision_search | `openclaw agent` -> `exec` -> `scripts/openclaw_runtime_evidence.py` | `memory.search` | `ok=true` | `req_phase_b_search` | `trace_phase_b_search` | `allow` |
| candidate_create_then_confirm | `openclaw agent` -> `exec` -> `scripts/openclaw_runtime_evidence.py` | `memory.create_candidate + memory.confirm` | `ok=true` | `req_phase_b_confirm` | `trace_phase_b_candidate_confirm` | `allow` |
| task_prefetch_context_pack | `openclaw agent` -> `exec` -> `scripts/openclaw_runtime_evidence.py` | `memory.prefetch` | `ok=true` | `req_phase_b_prefetch` | `trace_phase_b_prefetch` | `allow` |

## 边界

- 这次证明的是：OpenClaw Agent runtime 可以执行仓库证据脚本，脚本通过正式 `handle_tool_request()` 进入 `CopilotService`，三条 PRD flow 均有权限和 trace 元数据。
- 后续已补证明：`feishu-memory-copilot` 插件可在本机 OpenClaw 中安装、启用并读回 7 个 `toolNames`，见 [first-class-openclaw-tools-handoff.md](first-class-openclaw-tools-handoff.md)。
- 这次不证明：OpenClaw Feishu websocket 已经 owns `Feishu Memory Engine bot`；`openclaw health --json` 当前显示 Feishu channel `running=false`。
- 这次不写真实飞书生产空间；真实飞书数据仍必须 candidate-only，confirm/reject 仍必须走 `CopilotService` / `handle_tool_request()`。

## First-class Tool Registry Evidence

后期打磨 P0 已补齐 OpenClaw 原生工具注册 artifact：

```bash
openclaw plugins install --link --dangerously-force-unsafe-install ./agent_adapters/openclaw/plugin
openclaw plugins enable feishu-memory-copilot
openclaw plugins inspect feishu-memory-copilot --json
```

读回结果：

- `id=feishu-memory-copilot`
- `status=loaded`
- `enabled=true`
- `activated=true`
- `toolNames=["memory.search","memory.create_candidate","memory.confirm","memory.reject","memory.explain_versions","memory.prefetch","heartbeat.review_due"]`

说明：插件使用 Node `child_process` 调用 Python runner 进入 `memory_engine.copilot.openclaw_tool_runner`，因此本机安装时使用了 OpenClaw unsafe install override。这是本仓库受控源码，不等于生产部署，也不等于 Feishu websocket running。

## 本阶段验证

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
openclaw health --json --timeout 5000
python3 scripts/openclaw_runtime_evidence.py --json-output reports/openclaw_runtime_evidence_local.json
openclaw agent --agent main --message '你在 /Users/junhaocheng/feishu_ai_challenge。请用 exec 工具运行这个命令：python3 scripts/openclaw_runtime_evidence.py --json-output reports/openclaw_runtime_evidence_agent.json。然后只基于命令输出，用中文列出三条 flow 的 name、tool、ok、request_id、trace_id、permission_decision.decision。不要修改文件。' --json --timeout 120
python3 -m unittest tests.test_openclaw_runtime_evidence
python3 -m unittest tests.test_openclaw_tool_registry
```

结果：

- OpenClaw version OK：`2026.4.24`。
- Singleton preflight OK；未发现 repo 内 lark-cli listener 冲突。
- OpenClaw Agent runtime run `b252f11e-b49d-495c-a14f-0b823a888a5e` 成功，`exec` 调用 1 次，失败 0 次。
- 三条 Copilot flow 全部 `ok=true`。
- `tests.test_openclaw_runtime_evidence`：2 tests OK。
