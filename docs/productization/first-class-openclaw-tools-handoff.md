# First-class OpenClaw Tools Handoff

日期：2026-04-28
阶段：后期打磨 P0，`memory.*` first-class OpenClaw 原生工具注册

## 先看这个

1. 今天做的是把 Copilot Core 的 7 个工具注册成 OpenClaw 原生插件工具，不再只依赖 `exec` 调用证据脚本。
2. 我接下来从 `agent_adapters/openclaw/plugin/`、`agent_adapters/openclaw/tool_registry.py` 和 `memory_engine/copilot/openclaw_tool_runner.py` 开始。
3. 要交付的是本机可安装、可启用、可读回 `toolNames` 的 OpenClaw 插件；它调用 Python runner 后仍进入 `handle_tool_request()` 和 `CopilotService`。
4. 判断做对：`openclaw plugins inspect feishu-memory-copilot --json` 能看到 7 个工具名；单测和 healthcheck 都能验证 registry 与 schema / handler 一致。
5. 遇到问题记录：OpenClaw Feishu websocket running 是下一项任务；`openclaw health --json --timeout 5000` 当前仍没有完成 websocket running 证据，不能写成 production live。

## 已完成

- 新增 `agent_adapters/openclaw/plugin/package.json`、`openclaw.plugin.json` 和 `index.js`，定义 `feishu-memory-copilot` OpenClaw 插件。
- 新增 `agent_adapters/openclaw/tool_registry.py`，从 `memory_tools.schema.json` 生成 native registry manifest，并校验 schema tools 与 `supported_tool_names()` 一致。
- 新增 `memory_engine/copilot/openclaw_tool_runner.py`，让 OpenClaw 插件通过 Python runner 调用 `handle_tool_request()`，保留 `request_id`、`trace_id`、`permission_decision`。
- 新增 `tests/test_openclaw_tool_registry.py`，覆盖 registry、插件 manifest 和 runner 调用。
- 更新 `memory_engine/copilot/healthcheck.py`，新增 `openclaw_native_registry` 检查项。

## 本机 OpenClaw 验收

本插件需要通过 Node `child_process` 调用 Python runner，因此 OpenClaw 安装时会触发 dangerous code 检查。这里使用的是本仓库内的受控插件源码。

```bash
openclaw plugins install --link --dangerously-force-unsafe-install ./agent_adapters/openclaw/plugin
openclaw plugins enable feishu-memory-copilot
openclaw plugins inspect feishu-memory-copilot --json
```

读回结果摘要：

- `id=feishu-memory-copilot`
- `status=loaded`
- `enabled=true`
- `activated=true`
- `source=/Users/junhaocheng/feishu_ai_challenge/agent_adapters/openclaw/plugin/index.js`
- `toolNames=["memory.search","memory.create_candidate","memory.confirm","memory.reject","memory.explain_versions","memory.prefetch","heartbeat.review_due"]`

## 验证命令

已运行并通过：

```bash
python3 scripts/check_openclaw_version.py
python3 -m unittest tests.test_openclaw_tool_registry
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools tests.test_openclaw_runtime_evidence
python3 scripts/check_copilot_health.py --json
openclaw plugins install --link --dangerously-force-unsafe-install ./agent_adapters/openclaw/plugin
openclaw plugins enable feishu-memory-copilot
openclaw plugins inspect feishu-memory-copilot --json
```

## 还没做

- OpenClaw Feishu websocket running 证据还没完成；下一步继续跑 `python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket` 和 `openclaw health --json --timeout 5000`，直到 Feishu channel `running=true`。
- 真实飞书消息进入 OpenClaw Agent 再自然选择这些原生工具的端到端证据还没完成。
- 这不是生产部署、全量 Feishu workspace ingestion、长期 embedding 服务或 productized live。
