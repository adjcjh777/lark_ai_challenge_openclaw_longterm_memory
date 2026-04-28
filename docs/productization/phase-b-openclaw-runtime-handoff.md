# Phase B OpenClaw Runtime Handoff

日期：2026-04-28  
阶段：真实 OpenClaw Agent Runtime 验收已完成受控闭环。

## 先看这个

1. 今天补齐了 Phase B runtime 证据：OpenClaw Agent 真实运行，并通过 `exec` 调用仓库证据脚本。
2. 我接下来从 [openclaw-runtime-evidence.md](openclaw-runtime-evidence.md) 和 [openclaw_runtime_evidence.py](../../scripts/openclaw_runtime_evidence.py) 开始；这两个文件说明了怎么复现三条 flow。
3. 要交付的是评委或队友可复查的 runtime 证据，不是生产部署、全量飞书空间接入或长期运行服务。
4. 判断做对：`openclaw agent` 的 run id 存在，三条 flow 都有 `request_id`、`trace_id`、`permission_decision.decision=allow`。
5. 遇到问题记录：OpenClaw Feishu websocket 当前 health 仍显示 `running=false`；这不是本阶段已完成项。

## 已完成

- 新增 [scripts/openclaw_runtime_evidence.py](../../scripts/openclaw_runtime_evidence.py)：用临时 SQLite 跑 `memory.search`、`memory.create_candidate + memory.confirm`、`memory.prefetch` 三条 Phase B flow。
- 新增 [tests/test_openclaw_runtime_evidence.py](../../tests/test_openclaw_runtime_evidence.py)：锁住三条 flow 的工具名、成功状态、request/trace 元数据和 candidate -> active 状态变化。
- 新增 [openclaw-runtime-evidence.md](openclaw-runtime-evidence.md)：记录 OpenClaw ping、Agent runtime run id、三条 flow 和边界说明。
- 更新 README 顶部任务区：Phase B 已有 runtime evidence，下一步进入 Phase D live embedding gate 和 Phase E no-overclaim 审查。
- 更新产品化主控文档和 PRD gap tasks：把真实 OpenClaw runtime 验收从未完成项移到已完成项，同时保留 first-class tool registry 和 Feishu websocket 的风险边界。

## 怎么复现

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
openclaw health --json --timeout 5000
python3 scripts/openclaw_runtime_evidence.py --json-output reports/openclaw_runtime_evidence_local.json
openclaw agent --agent main --message '你在 /Users/junhaocheng/feishu_ai_challenge。请用 exec 工具运行这个命令：python3 scripts/openclaw_runtime_evidence.py --json-output reports/openclaw_runtime_evidence_agent.json。然后只基于命令输出，用中文列出三条 flow 的 name、tool、ok、request_id、trace_id、permission_decision.decision。不要修改文件。' --json --timeout 120
python3 -m unittest tests.test_openclaw_runtime_evidence
```

## 当前验证结果

已运行并通过：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
openclaw health --json --timeout 5000
python3 scripts/openclaw_runtime_evidence.py --json-output reports/openclaw_runtime_evidence_local.json
openclaw agent --agent main --message '你在 /Users/junhaocheng/feishu_ai_challenge。请用 exec 工具运行这个命令：python3 scripts/openclaw_runtime_evidence.py --json-output reports/openclaw_runtime_evidence_agent.json。然后只基于命令输出，用中文列出三条 flow 的 name、tool、ok、request_id、trace_id、permission_decision.decision。不要修改文件。' --json --timeout 120
python3 -m unittest tests.test_openclaw_runtime_evidence
```

结果摘要：

- OpenClaw version OK：`2026.4.24`。
- Singleton preflight OK；未发现 repo 内 lark-cli listener 冲突。
- OpenClaw health OK；Feishu channel configured/enabled，credential probe OK；但 `channels.feishu.running=false`。
- OpenClaw runtime ping run：`8099a091-89cd-49de-a48e-a74743d9c4f7`，输出 `OpenClaw runtime ping`。
- OpenClaw Phase B evidence run：`b252f11e-b49d-495c-a14f-0b823a888a5e`，`toolSummary.calls=1`，`toolSummary.tools=["exec"]`，`toolSummary.failures=0`。
- 三条 flow 全部通过：`memory.search`、`memory.create_candidate + memory.confirm`、`memory.prefetch`。
- `tests.test_openclaw_runtime_evidence`：2 tests OK。

## 飞书共享看板

需要同步或已同步的任务描述：

- `2026-04-28 程俊豪：Phase B 真实 OpenClaw Agent runtime 验收`

建议备注：

```text
OpenClaw Agent runtime run b252f11e-b49d-495c-a14f-0b823a888a5e 已通过；Agent 使用 exec 调用 scripts/openclaw_runtime_evidence.py，三条 Copilot flow ok=true：memory.search、memory.create_candidate+memory.confirm、memory.prefetch；均保留 request_id、trace_id、permission_decision=allow。验证：check_openclaw_version、listener singleton、openclaw health、tests.test_openclaw_runtime_evidence。边界：不是生产部署；不是全量 Feishu ingestion；memory.* 仍未宣称为 OpenClaw first-class tool registry；Feishu websocket health running=false。
```

## 还没做

- `memory.*` 还没有在本机 OpenClaw Agent `systemPromptReport.tools.entries` 中作为 first-class 原生工具出现；本阶段证据路径是 Agent runtime -> `exec` -> 证据脚本 -> `handle_tool_request()` -> `CopilotService`。
- OpenClaw Feishu websocket 没有证明已经 owns bot；health 当前显示 `running=false`。
- Live Cognee / Ollama embedding gate 仍未完成；下一步从 `scripts/check_embedding_provider.py` 和 `scripts/spike_cognee_local.py --dry-run` 开始。
- No-overclaim 审查仍要继续检查 README、runbook、benchmark report 和白皮书。
