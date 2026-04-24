# 队友本机 lark-cli 配置与 Day 2 测试指南

适用对象：队友在自己的电脑上拉取仓库后，配置 `lark-cli` 并测试 Day 2 飞书 Bot 最小闭环。

## 1. 前置条件

你这边需要先确认：

- 飞书开放平台应用已经发布。
- 应用已经开启机器人能力。
- 应用可用范围已经包含队友。
- 应用已开通并发布这些权限：
  - `im:message.group_at_msg:readonly`
  - `im:message.p2p_msg:readonly`
  - `im:message:send_as_bot`
- 队友已被加入测试群，或队友有权限把机器人加入测试群。

队友本机需要拿到：

```text
App ID: cli_a961a18dbebadcd1
App Secret: 从飞书开放平台应用后台复制，不能提交到仓库
Profile name: feishu-ai-challenge
```

## 2. 拉取仓库

```bash
git clone https://github.com/adjcjh777/lark_ai_challenge_openclaw_longterm_memory.git
cd lark_ai_challenge_openclaw_longterm_memory
```

如果已经克隆过：

```bash
cd lark_ai_challenge_openclaw_longterm_memory
git pull
```

## 3. 安装或检查 lark-cli

先检查：

```bash
lark-cli --version
```

如果没有安装，按官方方式安装：

```bash
npm install -g @larksuite/cli
```

安装后再确认：

```bash
lark-cli --version
```

## 4. 配置项目 profile

不要使用裸 `lark-cli config init --new`，它可能覆盖已有配置。使用 `profile add` 追加项目应用。

```bash
read -s APP_SECRET
printf '%s' "$APP_SECRET" | lark-cli profile add \
  --name feishu-ai-challenge \
  --app-id cli_a961a18dbebadcd1 \
  --app-secret-stdin \
  --brand feishu
unset APP_SECRET
```

输入 `read -s APP_SECRET` 后，终端不会显示 App Secret。粘贴后按回车即可。

查看 profile：

```bash
lark-cli profile list
```

验证项目应用配置：

```bash
lark-cli --profile feishu-ai-challenge doctor
```

说明：

- 只跑 Bot 长连接监听和 Bot 回复时，主要使用 bot 身份，不一定要求 user 登录。
- 如果队友要用 CLI 搜索群、查历史消息或拉人进群，需要额外 user 登录：

```bash
lark-cli --profile feishu-ai-challenge auth login --domain im
```

## 5. 本地业务验证

先跑不依赖飞书的本地验证：

```bash
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

再跑 fake event replay：

```bash
tmpdb=$(mktemp /tmp/feishu_day2_XXXX.sqlite)
MEMORY_DB_PATH=$tmpdb MEMORY_DEFAULT_SCOPE=project:feishu_ai_challenge \
  python3 -m memory_engine feishu replay tests/fixtures/feishu_text_remember_event.json
MEMORY_DB_PATH=$tmpdb MEMORY_DEFAULT_SCOPE=project:feishu_ai_challenge \
  python3 -m memory_engine feishu replay tests/fixtures/feishu_text_recall_event.json
rm -f "$tmpdb"
```

看到 `已记住` 和 `命中记忆` 说明本地 handler 正常。

## 6. 启动真实飞书监听

仓库已提供启动脚本：

```bash
scripts/start_feishu_bot.sh
```

脚本默认配置：

```text
LARK_CLI_PROFILE=feishu-ai-challenge
MEMORY_DB_PATH=data/memory.sqlite
MEMORY_DEFAULT_SCOPE=project:feishu_ai_challenge
FEISHU_BOT_MODE=reply
```

调试模式，不真实回复飞书：

```bash
scripts/start_feishu_bot.sh --dry-run
```

正式测试时使用：

```bash
scripts/start_feishu_bot.sh
```

保持这个终端不要关闭。关闭后，Bot 不会继续接收新消息。

## 7. 飞书群内测试

群聊里必须 @机器人：

```text
@机器人 /remember 生产部署必须加 --canary --region cn-shanghai
@机器人 /recall 生产部署参数
@机器人 /remember 不对，生产部署 region 改成 ap-shanghai
@机器人 /recall 生产部署 region
```

单聊机器人时可以不 @：

```text
/remember 生产部署必须加 --canary --region cn-shanghai
/recall 生产部署参数
/remember 不对，生产部署 region 改成 ap-shanghai
/recall 生产部署 region
```

## 8. 查看本机测试结果

查看当前 active 记忆：

```bash
python3 -m memory_engine recall --scope project:feishu_ai_challenge "生产部署 region"
```

查看最近飞书事件：

```bash
python3 - <<'PY'
import sqlite3

conn = sqlite3.connect("data/memory.sqlite")
conn.row_factory = sqlite3.Row
for row in conn.execute("""
    SELECT source_id, sender_id, content, created_at
    FROM raw_events
    WHERE source_type = 'feishu_message'
    ORDER BY created_at DESC
    LIMIT 10
"""):
    print(dict(row))
conn.close()
PY
```

## 9. 队友 Day 2 交付物

队友不需要改核心代码。建议产出：

```text
docs/day2-test-notes.md
docs/day2-demo-script.md
docs/day2-demo-cases.md
```

至少记录：

- 测试输入。
- Bot 实际回复。
- 是否符合预期。
- 失败截图或异常现象。
- 20 条 Demo 语料。
- 5 分钟 Demo 台词。

## 10. 常见问题

### profile 不存在

```bash
lark-cli profile list
```

如果看不到 `feishu-ai-challenge`，重新执行第 4 步。

### doctor 提示 no user logged in

如果只跑 Bot 监听，不一定阻塞。若需要 user 身份操作，再登录：

```bash
lark-cli --profile feishu-ai-challenge auth login --domain im
```

### 群里 @机器人没有反应

检查：

1. `scripts/start_feishu_bot.sh` 是否还在运行。
2. 机器人是否在测试群。
3. 飞书开放平台事件订阅是否已发布。
4. 应用可用范围是否包含队友和测试群成员。
5. 是否在群聊里 @机器人。

### 能收到事件但不能回复

检查：

1. 应用是否已发布 `im:message:send_as_bot`。
2. 机器人是否被禁言。
3. 机器人是否仍在群里。
4. 终端里 `publish.returncode` 和 `stderr` 的错误信息。

### App Secret 泄露

不要把 App Secret 写入 `.env` 后提交，也不要发到群里。若怀疑泄露，到飞书开放平台重置 App Secret，并重新配置 profile。
