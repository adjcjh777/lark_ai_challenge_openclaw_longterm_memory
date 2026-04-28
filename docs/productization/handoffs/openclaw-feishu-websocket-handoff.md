# OpenClaw Feishu Websocket Running Handoff

日期：2026-04-28
阶段：后期打磨 P0，OpenClaw Feishu websocket running 证据

## 先看这个

1. 今天补的是 OpenClaw Feishu websocket 接管 `Feishu Memory Engine bot` 的运行证据，不是生产上线。
2. 我接下来从 `scripts/check_openclaw_feishu_websocket.py`、`docs/productization/openclaw-runtime-evidence.md` 和 `docs/productization/feishu-staging-runbook.md` 继续。
3. 要交付的是可重复检查：同一时间没有 repo 内 lark-cli listener 冲突，OpenClaw Feishu channel `running=true`，真实飞书 DM 能进入 OpenClaw Agent 并完成 dispatch。
4. 判断做对：`python3 scripts/check_openclaw_feishu_websocket.py --json` 返回 `ok=true`，并且 `channels_status.channel_running=true`、`account_running=true`、`feishu_logs.missing_required_events=[]`。
5. 遇到问题记录：OpenClaw 2026.4.24 的 `openclaw health --json` 总览仍把 Feishu `running` 报成 `false`，但 `openclaw channels status --probe --json` 和 gateway 日志已经显示 running；本阶段把这个写成 warning，不把它改写成 production live。

## 本阶段做了什么

- 新增 `scripts/check_openclaw_feishu_websocket.py`：聚合单监听检查、`openclaw channels status --probe --json`、`openclaw health --json --timeout 5000` 和 Feishu channel 日志，只输出脱敏状态摘要。
- 新增 `tests/test_openclaw_feishu_websocket_evidence.py`：覆盖 `channels.status` running、`health` 总览 running 字段不一致时的 warning、以及飞书 ID 脱敏。
- 用 lark-cli 用户身份向 `Feishu Memory Engine bot` 发送真实 DM，OpenClaw gateway 日志记录：
  - `received message`：2026-04-28 15:35:03 CST
  - `dispatching to agent`：2026-04-28 15:35:04 CST
  - `dispatch complete`：2026-04-28 15:36:14 CST
- `openclaw channels status --probe --json` 显示 Feishu channel 和 default account 均 `running=true`，credential probe OK。

## 验收证据

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
openclaw channels status --probe --json
openclaw health --json --timeout 5000
python3 scripts/check_openclaw_feishu_websocket.py --json --timeout 45
python3 -m unittest tests.test_openclaw_feishu_websocket_evidence
```

结果摘要：

- OpenClaw version OK：`2026.4.24`。
- 单监听检查通过；只看到 `openclaw-gateway`，没有 repo 内 `copilot-feishu listen`、legacy `feishu listen` 或 direct `lark-cli event +subscribe`。
- `check_openclaw_feishu_websocket.py`：`ok=true`，`fail=0`，`pass=4`，`warning=1`。
- `channels_status`：`channel_running=true`、`account_running=true`、`probe_ok=true`。
- `feishu_logs`：已看到 websocket start、WebSocket client started、真实 inbound message、dispatching to agent、dispatch complete。
- `health_consistency`：warning；`openclaw health --json` 总览 running 字段仍为 false，但 `channels.status` 和日志证据为 true。

## 边界

- 可以说：OpenClaw Feishu websocket 在本机 staging 中已 running，并且真实 DM 已进入 OpenClaw Agent dispatch。
- 可以说：同一个 bot 当前没有 repo 内 lark-cli listener 冲突。
- 不要说：生产部署、全量 Feishu workspace ingestion、长期运行监控、productized live 已完成。
- 不要说：真实 Feishu DM 已经稳定走本项目 `memory.search` / `handle_tool_request()`。本次真实 DM 触发的是 OpenClaw 内置 `memory_search`，不是本项目 first-class `memory.search` runner；这个要放到后续“体验和旧入口收敛 / Feishu tool routing”任务继续处理。

## 下一步

- 优先做真实飞书权限映射：把 demo 常量式 permission context 升级为真实 actor、tenant、organization、chat、document 映射。
- 另开一项小任务处理 Feishu Agent tool routing：让真实飞书消息自然选择本项目 `memory.*` first-class tool，而不是只落到 OpenClaw 内置 `memory_search`。
- 继续保持 candidate-only、permission fail-closed、CopilotService 事实源和 no-overclaim 口径。
