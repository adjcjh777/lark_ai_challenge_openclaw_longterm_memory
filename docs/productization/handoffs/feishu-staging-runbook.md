# Feishu Staging Runbook

日期：2026-04-28  
状态：已补单监听测试流程和 OpenClaw Feishu websocket running 本机 staging 证据；仍不是生产部署、全量 Feishu workspace ingestion 或 productized live。

## 先看这个

1. 同一个 `Feishu Memory Engine bot` 同一时间只能有一个监听入口：OpenClaw Feishu websocket、`copilot-feishu listen`、legacy `feishu listen` 三选一。
2. 当前推荐产品化路线是 OpenClaw-native；如果 OpenClaw Feishu websocket 已接管 bot，就不要再启动 `lark-cli event +subscribe`、`scripts/start_copilot_feishu_live.sh` 或 `scripts/start_feishu_bot.sh`。
3. 如果需要用仓库内 lark-cli sandbox 做回归，只能启动新的 `scripts/start_copilot_feishu_live.sh`；旧 `scripts/start_feishu_bot.sh` 只保留为 legacy fallback。
4. 真实群聊 ID、open_id、token 和 app secret 只放本机环境变量或 lark-cli/OpenClaw 配置，不写入仓库。
5. OpenClaw 2026.4.24 中 `openclaw health --json` 的 Feishu running 总览字段可能仍为 `false`；当前 running 证据以 `openclaw channels status --probe --json` 和 gateway 日志为准，并把不一致写为 warning。
6. 遇到监听冲突时，先停止多余监听，再重跑 preflight；不要靠同时开多个监听“碰运气”验收。

## 单监听模式

| 模式 | 什么时候用 | 可以启动什么 | 不能同时启动什么 |
|---|---|---|---|
| OpenClaw Feishu websocket | 真实 OpenClaw Agent runtime / Feishu 插件验收 | OpenClaw Feishu channel | `copilot-feishu listen`、legacy `feishu listen`、直接 `lark-cli event +subscribe` |
| Copilot lark-cli sandbox | 仓库内受控测试群回归 | `scripts/start_copilot_feishu_live.sh` | OpenClaw Feishu websocket、legacy `feishu listen` |
| Legacy fallback | 只复查旧 Bot handler | `scripts/start_feishu_bot.sh` | OpenClaw Feishu websocket、`copilot-feishu listen` |

## 本地 Dashboard

只读 dashboard 是 Memory Copilot runtime 的一部分，不作为另一个需要单独维护的服务：

- OpenClaw 加载 `feishu-memory-copilot` 插件时，会尝试启动 dashboard。
- `scripts/start_copilot_feishu_live.sh` 或 `python3 -m memory_engine copilot-feishu listen` 启动时，会同时启动 dashboard。
- 默认地址：`http://127.0.0.1:8765`。
- 只开放 `GET` / `HEAD` 查询；写请求返回 `405`。

如需关闭 dashboard：

```bash
export FEISHU_MEMORY_COPILOT_ADMIN_ENABLED=0
# 或仓库内 listener 使用：
python3 -m memory_engine copilot-feishu listen --no-admin
```

## 开始前检查

先确认 OpenClaw 版本锁：

```bash
python3 scripts/check_openclaw_version.py
```

如果准备让 OpenClaw Feishu websocket 接管 bot：

```bash
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
python3 scripts/check_openclaw_feishu_websocket.py --json --timeout 45
```

如果准备让仓库内 Copilot lark-cli sandbox 接管 bot：

```bash
python3 scripts/check_feishu_listener_singleton.py --planned-listener copilot-lark-cli
```

如果准备跑 legacy fallback：

```bash
python3 scripts/check_feishu_listener_singleton.py --planned-listener legacy-lark-cli
```

这个检查会拦截以下已知冲突：

- `python3 -m memory_engine copilot-feishu listen`
- `python3 -m memory_engine feishu listen`
- 直接运行的 `lark-cli event +subscribe`
- 命令行可识别的 OpenClaw Feishu / Lark websocket 进程

如果只看到 `openclaw-gateway`，单监听脚本会给 warning：进程列表无法判断该 gateway 是否已经启用 Feishu websocket。此时继续运行 `scripts/check_openclaw_feishu_websocket.py`，用 `channels.status`、credential probe 和 Feishu channel logs 判断是否真的 running；如果 OpenClaw 正在接收同一个 bot 的飞书事件，就不要再启动仓库内 lark-cli 监听。

## 推荐测试顺序

### A. OpenClaw Feishu websocket owns the bot

用于 OpenClaw-native 真实入口验收和后期打磨 staging 证据。

1. 运行单监听检查：

```bash
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
python3 scripts/check_openclaw_feishu_websocket.py --json --timeout 45
```

2. 确认没有 legacy `memory_engine feishu listen`、`memory_engine copilot-feishu listen` 或直接 `lark-cli event +subscribe`。
3. 检查 `check_openclaw_feishu_websocket.py` 结果：
   - `ok=true`
   - `channels_status.channel_running=true`
   - `channels_status.account_running=true`
   - `channels_status.probe_ok=true`
   - `feishu_logs.missing_required_events=[]`
4. 在 OpenClaw Agent 里跑三条 flow：
   - 历史决策召回：触发 `memory.search`。
   - 候选确认：触发 `memory.create_candidate`，再触发 `memory.confirm` 或 `memory.reject`。
   - 任务前上下文：触发 `memory.prefetch`，让 Agent 输出 checklist / plan / report。
5. 把每条 flow 的 input、output、tool、request_id、trace_id、permission_decision 和失败回退写入 `docs/productization/openclaw-runtime-evidence.md` 或对应 handoff。

已知边界：2026-04-28 本机 staging 证据中，真实 DM 已进入 OpenClaw Agent dispatch，但工具调用落到 OpenClaw 内置 `memory_search`，还不是本项目 first-class `memory.search` runner。这个不影响 websocket running 证据，但不能写成 Feishu DM 已完成项目 `memory.*` tool routing。

### B. Copilot lark-cli sandbox owns the bot

用于仓库内受控测试群回归，不代表 productized live。

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_feishu_listener_singleton.py --planned-listener copilot-lark-cli
scripts/start_copilot_feishu_live.sh
```

启动成功后，本地只读 dashboard 默认可访问：

```text
http://127.0.0.1:8765
```

测试群里按顺序发送：

```text
@Feishu Memory Engine bot /health
@Feishu Memory Engine bot /remember 决定：Copilot live sandbox 验收口径是 candidate 先确认再 active
@Feishu Memory Engine bot /confirm <candidate_id>
@Feishu Memory Engine bot Copilot live sandbox 验收口径是什么？
@Feishu Memory Engine bot /reject <candidate_id>
```

完成标准：

- `/remember` 只创建 candidate（待确认记忆），不会自动 active。
- `/confirm` / `/reject` 必须由 reviewer 执行，且走 `CopilotService` / `handle_tool_request()`。
- 普通提问触发 `memory.search`，回复包含 request_id / trace_id。
- 日志写入 `logs/feishu-copilot-live/`，不提交真实日志。

### C. Legacy fallback owns the bot

只在明确复查旧 handler 时使用：

```bash
python3 scripts/check_feishu_listener_singleton.py --planned-listener legacy-lark-cli
scripts/start_feishu_bot.sh
```

legacy fallback 不作为 OpenClaw-native 主线证据；测试结束后必须停止。

## 停止监听

优先用启动终端里的 `Ctrl-C` 停止。

如果监听被留在后台，先查看：

```bash
ps -axo pid,ppid,command | rg 'lark-cli event \+subscribe|memory_engine (feishu|copilot-feishu) listen|openclaw.*(feishu|lark|websocket)'
```

只在确认 PID 属于本项目监听后再停止：

```bash
kill <pid>
```

不要停止无关 OpenClaw gateway、其他项目 bot 或用户正在使用的进程。

## 失败记录

如果 preflight 失败，把以下内容写入 runtime evidence 或 handoff：

- planned listener 是什么。
- 冲突进程的 pid、kind、command。
- 最终选择哪个监听作为唯一入口。
- 是否仍保留 OpenClaw gateway running，以及为什么。

如果需要临时绕过，可以设置：

```bash
FEISHU_SINGLE_LISTENER_ALLOW_CONFLICT=1
```

这个开关只允许 throwaway debugging；不能用于正式验收、handoff 或看板完成证据。
