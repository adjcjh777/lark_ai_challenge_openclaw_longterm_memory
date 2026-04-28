# Phase B OpenClaw Runtime Evidence

日期：2026-04-28  
阶段：Phase B 真实 OpenClaw Agent Runtime 验收  
结论：已完成受控 runtime 验收；后续已补 `memory.*` first-class OpenClaw 原生工具注册本机证据和 OpenClaw Feishu websocket running 本机 staging 证据；仍不宣称生产部署、全量飞书空间接入或 productized live。

## 先看这个

1. 今天补的是 OpenClaw Agent runtime 证据，不是再做一个 demo replay。
2. 真实 OpenClaw Agent 已通过 `exec` 工具运行仓库内证据脚本，脚本再进入 `handle_tool_request()` 和 `CopilotService`。
3. 三条必需 flow 已通过：历史决策召回、candidate 创建后确认、任务前 `memory.prefetch`。
4. 判断做对：每条 flow 都有 `request_id`、`trace_id` 和 `permission_decision.decision=allow`。
5. 遇到问题记录：Phase B 当时没有证明 OpenClaw Feishu websocket owns bot；后续已用 `channels.status`、gateway 日志和真实 DM dispatch 补 staging 证据，但真实 Feishu DM 还没稳定进入本项目 first-class `memory.search` runner。

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
- OpenClaw health：`ok=true`；Feishu channel configured/enabled，credential probe OK，botName 为 `Feishu Memory Engine bot`；当时 `channels.feishu.running=false`。后续 websocket staging 证据改以 `openclaw channels status --probe --json` 和 gateway 日志为准，并把 health running 字段不一致记为 warning。

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
- Phase B 这次不证明：OpenClaw Feishu websocket 已经 owns `Feishu Memory Engine bot`；后续已在 [openclaw-feishu-websocket-handoff.md](openclaw-feishu-websocket-handoff.md) 补本机 staging 证据。
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

说明：插件使用 Node `child_process` 调用 Python runner 进入 `memory_engine.copilot.openclaw_tool_runner`，因此本机安装时使用了 OpenClaw unsafe install override。这是本仓库受控源码，不等于生产部署。

## Feishu Websocket Staging Evidence

后期打磨 P0 已补齐 OpenClaw Feishu websocket running 本机 staging 证据，详见 [openclaw-feishu-websocket-handoff.md](openclaw-feishu-websocket-handoff.md)。

```bash
python3 scripts/check_openclaw_feishu_websocket.py --json --timeout 45
python3 -m unittest tests.test_openclaw_feishu_websocket_evidence
```

结果摘要：

- 单监听检查通过；未发现 repo 内 `copilot-feishu listen`、legacy `feishu listen` 或 direct `lark-cli event +subscribe`。
- `openclaw channels status --probe --json` 显示 Feishu channel 和 default account 均 `running=true`，credential probe OK。
- gateway 日志已看到 websocket start、WebSocket client started、真实 inbound message、dispatching to agent、dispatch complete。
- `python3 scripts/check_openclaw_feishu_websocket.py --json --timeout 45` 返回 `ok=true`，`pass=4`，`warning=1`，`fail=0`。
- `openclaw health --json` 总览 running 字段仍与 `channels.status` 不一致；本阶段作为 warning，不作为失败。
- 真实 Feishu DM 当前触发的是 OpenClaw 内置 `memory_search`，不是本项目 first-class `memory.search` runner；后续 Feishu Agent tool routing 仍要继续做。

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
