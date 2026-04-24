# Day 3 Handoff

日期：2026-04-24

## 今日目标

D3 原计划日期是 2026-04-26，本次提前完成“真实飞书 Bot 稳定化与 Demo 口径”。

P0：

- 用真实飞书测试群跑通 `/remember`、`/recall`、`/versions`。
- Bot 回复统一为稳定字段：类型、主题、状态、版本、来源。
- 对非文本、空消息、机器人自发消息、重复消息、未知命令做明确处理。
- 记录真实飞书后台配置和未验证项。

P1：

- 增加 `/help`。
- 增加 `/health`。
- 新增真实飞书 Demo 脚本初稿：`docs/demo-runbook.md`。

## 真实飞书配置

- lark-cli profile：`feishu-ai-challenge`
- 应用 App ID：使用本地 `FEISHU_APP_ID`，真实值不提交。
- 机器人显示名：`Feishu Memory Engine bot`
- 机器人 mention open_id：使用本地 `FEISHU_BOT_OPEN_ID`，真实值不提交。
- 测试群名称：内部测试群，真实名称不提交。
- 测试群 `chat_id`：使用本地 `FEISHU_TEST_CHAT_ID`，真实值不提交。
- 默认数据库：`data/memory.sqlite`
- 推荐默认 scope：`project:feishu_ai_challenge`
- 推荐 Bot 回复模式：`FEISHU_BOT_MODE=reply`

`lark-cli doctor --profile feishu-ai-challenge` 已确认：

- CLI 配置存在。
- profile 能解析到飞书应用。
- user token 已登录，用户为 `程俊豪`。
- user token 已含 IM 发送、群消息读取、搜索等 scope。
- `open.feishu.cn` 和 `mcp.feishu.cn` 可访问。

## 已完成代码能力

- `/remember <内容>`：写入记忆，回复包含类型、主题、状态、版本、来源、记忆类型、`memory_id`。
- `/recall <查询>`：召回当前 active 记忆，回复包含类型、主题、状态、版本、来源、记忆类型、当前有效规则、证据。
- `/versions <memory_id>`：展示版本链，标明 active / superseded。
- `/help`：展示命令列表、参数示例和 Demo 推荐输入。
- `/health`：展示数据库路径、默认 scope、dry-run 状态和回复模式。
- 非文本消息：回复“暂时只支持文本消息”。
- 空消息：回复“收到空消息，未写入记忆”。
- 机器人自发消息：忽略且不回复，避免循环。
- 重复消息：回复重复投递提示，不重复写入。
- 未知命令：回复未知命令提示，并引导 `/help`。

## 启动方式

真实监听：

```bash
scripts/start_feishu_bot.sh
```

调试模式：

```bash
scripts/start_feishu_bot.sh --dry-run
```

推荐环境变量：

```bash
MEMORY_DB_PATH=data/memory.sqlite
MEMORY_DEFAULT_SCOPE=project:feishu_ai_challenge
FEISHU_BOT_MODE=reply
LARK_CLI_PROFILE=feishu-ai-challenge
```

## 真实群 CLI 验证命令

发送 Demo 命令。先在本机 shell 设置真实值，不要写入仓库：

```bash
export FEISHU_TEST_CHAT_ID="oc_xxx"
export FEISHU_BOT_OPEN_ID="ou_xxx"
```

然后发送：

```bash
lark-cli im +messages-send --profile feishu-ai-challenge --as user --chat-id "$FEISHU_TEST_CHAT_ID" --content "{\"text\":\"<at user_id=\\\"$FEISHU_BOT_OPEN_ID\\\">Feishu Memory Engine bot</at> /remember 生产部署必须加 --canary --region cn-shanghai\"}" --msg-type text --idempotency-key feishu-memory-d3-remember
lark-cli im +messages-send --profile feishu-ai-challenge --as user --chat-id "$FEISHU_TEST_CHAT_ID" --content "{\"text\":\"<at user_id=\\\"$FEISHU_BOT_OPEN_ID\\\">Feishu Memory Engine bot</at> /recall 生产部署参数\"}" --msg-type text --idempotency-key feishu-memory-d3-recall-1
lark-cli im +messages-send --profile feishu-ai-challenge --as user --chat-id "$FEISHU_TEST_CHAT_ID" --content "{\"text\":\"<at user_id=\\\"$FEISHU_BOT_OPEN_ID\\\">Feishu Memory Engine bot</at> /remember 不对，生产部署 region 改成 ap-shanghai\"}" --msg-type text --idempotency-key feishu-memory-d3-update
lark-cli im +messages-send --profile feishu-ai-challenge --as user --chat-id "$FEISHU_TEST_CHAT_ID" --content "{\"text\":\"<at user_id=\\\"$FEISHU_BOT_OPEN_ID\\\">Feishu Memory Engine bot</at> /recall 生产部署 region\"}" --msg-type text --idempotency-key feishu-memory-d3-recall-2
```

查看最近群消息：

```bash
lark-cli im +chat-messages-list --profile feishu-ai-challenge --as user --chat-id "$FEISHU_TEST_CHAT_ID" --page-size 20
```

说明：群聊里普通 `/help` 不会触发 `im.message.receive_v1` 的 group_at 事件；需要手动 `@Feishu Memory Engine bot /help`，或在 CLI 中使用上面的 `<at user_id="...">` 形式。

## 真实群验证结果

已在内部真实测试群完成真实收发验证：

- `/help`：Bot 返回命令帮助和 Demo 推荐输入。
- `/health`：Bot 返回 `/tmp/feishu_d3_real.sqlite`、`project:feishu_ai_challenge`、`dry-run:false`、`reply`。
- `/remember 生产部署必须加 --canary --region cn-shanghai`：Bot 返回 `类型：已记住`、`版本：v1` 和 `memory_id`。
- `/recall 生产部署参数`：Bot 返回 v1 当前有效规则。
- `/remember 不对，生产部署 region 改成 ap-shanghai`：Bot 返回 `类型：记忆更新`、`版本：v2`。
- `/recall 生产部署 region`：Bot 只返回 active v2 `ap-shanghai`。
- `/versions <memory_id>`：Bot 返回 v1 `[superseded]`、v2 `[active]`。
- `/unknown`：Bot 返回 `状态：unknown_command` 并引导 `/help`。

## 本地验证

```bash
python3 -m compileall memory_engine scripts
python3 -m unittest discover -s tests
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

本地 replay：

```bash
rm -f /tmp/feishu_d3_replay.sqlite
python3 -m memory_engine --db-path /tmp/feishu_d3_replay.sqlite feishu replay tests/fixtures/feishu_text_remember_event.json
python3 -m memory_engine --db-path /tmp/feishu_d3_replay.sqlite feishu replay tests/fixtures/feishu_text_recall_event.json
python3 -m memory_engine --db-path /tmp/feishu_d3_replay.sqlite feishu replay tests/fixtures/feishu_text_update_event.json
python3 -m memory_engine --db-path /tmp/feishu_d3_replay.sqlite feishu replay tests/fixtures/feishu_text_help_event.json
python3 -m memory_engine --db-path /tmp/feishu_d3_replay.sqlite feishu replay tests/fixtures/feishu_text_health_event.json
python3 -m memory_engine --db-path /tmp/feishu_d3_replay.sqlite feishu replay tests/fixtures/feishu_text_unknown_event.json
python3 -m memory_engine --db-path /tmp/feishu_d3_replay.sqlite feishu replay tests/fixtures/feishu_text_empty_event.json
python3 -m memory_engine --db-path /tmp/feishu_d3_replay.sqlite feishu replay tests/fixtures/feishu_non_text_event.json
python3 -m memory_engine --db-path /tmp/feishu_d3_replay.sqlite feishu replay tests/fixtures/feishu_bot_self_event.json
```

## 队友今晚任务

1. 按 `docs/demo-runbook.md` 在测试群人工跑 2 轮。
2. 每一步记录截图需求：用户输入、Bot 回复、版本链、异常输入处理。
3. 检查 Bot 回复是否评委秒懂；不清楚的中文文案直接改到 `memory_engine/feishu_messages.py`。
4. 扩写白皮书“为什么不是普通搜索”段落，重点对比：版本、状态、来源证据、覆盖更新、协作场景触发。

## 未验证项

- 飞书开放平台后台权限是否已全部发布到生产环境，仍以真实群发送和回复结果为准。
- 多人同时发送同主题覆盖命令的并发行为，当前只验证单线程消息处理和 message_id 幂等。
- 飞书卡片 JSON 尚未实现，D3 仍使用结构化文本；卡片化在 D6 处理。
- Bitable 同步尚未实现，D4 处理。
