# Day 2 Handoff

日期：2026-04-24

## 今日完成

- 新增飞书 Bot 最小闭环：`feishu replay` 和 `feishu listen`。
- 运行时优先使用本机 `lark-cli`，不依赖 `lark-oapi` 接收事件或发送消息。
- 支持 `/remember`、`/recall`、`/versions` 文本命令。
- `/remember` 写入现有 `MemoryRepository`，并记录 `source_type=feishu_message`、`source_id=message_id`、`sender_id`。
- `/recall` 返回 active 记忆、版本号、`memory_id` 和 evidence。
- 使用 `raw_events(source_type, source_id)` 查询处理过的飞书消息，避免重复投递造成重复写入。
- 新增 fake event fixture，未配置真实飞书应用时也能验证 handler。

## 启动方式

本地 replay：

```bash
python3 -m memory_engine feishu replay tests/fixtures/feishu_text_remember_event.json
python3 -m memory_engine feishu replay tests/fixtures/feishu_text_recall_event.json
```

真实监听：

```bash
python3 -m memory_engine feishu listen
```

调试模式，不真实发送飞书回复：

```bash
python3 -m memory_engine feishu listen --dry-run
```

推荐环境变量：

```bash
MEMORY_DB_PATH=data/memory.sqlite
MEMORY_DEFAULT_SCOPE=project:feishu_ai_challenge
FEISHU_BOT_MODE=reply
```

如果需要指定 lark-cli profile：

```bash
LARK_CLI_PROFILE=your_profile
```

## 飞书后台仍需人工确认

1. 企业自建应用已开启机器人能力。
2. 事件订阅方式为长连接。
3. 已订阅 `im.message.receive_v1`。
4. 已开通并发布权限：
   - `im:message.group_at_msg:readonly`
   - `im:message.p2p_msg:readonly`
   - `im:message:send_as_bot`
5. 应用可用范围包含测试用户和测试群成员。
6. 机器人已加入测试群，并允许发言。

## Demo 命令

```text
/remember 生产部署必须加 --canary --region cn-shanghai
/recall 生产部署参数
/remember 不对，生产部署 region 改成 ap-shanghai
/recall 生产部署 region
```

## 已验证

```bash
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine feishu replay tests/fixtures/feishu_text_remember_event.json
python3 -m memory_engine feishu replay tests/fixtures/feishu_text_recall_event.json
```

## 未验证

- 真实飞书 Bot 收发消息，依赖飞书后台权限、机器人入群和 lark-cli bot 身份可用性。
- 生产部署。
