# Day 2 QA Notes

日期：2026-04-25  
对应任务：D2 队友晚上任务补齐  
主题：飞书 Bot 最小闭环检查

## 给队友先看这个

这份文件补齐 D2 队友任务：检查飞书后台准备项、准备测试群命令、记录本地 replay 和真实飞书验证结论。真实飞书截图、群聊 ID、用户 ID、token 不提交仓库；这里只写可公开的复盘结论。

## 飞书后台检查结果

| 检查项 | 结果 | 证据或说明 |
|---|---|---|
| 企业自建应用已开启机器人能力 | 已满足 | 后续 D6 真实测试群已能收到 Bot interactive card 回复 |
| 事件订阅方式为长连接 | 已满足 | `scripts/start_feishu_bot.sh` 使用 `lark-cli event +subscribe` |
| 已订阅 `im.message.receive_v1` | 已满足 | D6 真实测试收到 `/remember`、`/recall` 消息事件 |
| 已开通 `im:message.group_at_msg:readonly` | 已满足 | 群聊 @Bot 命令可被监听 |
| 已开通 `im:message.p2p_msg:readonly` | 待单聊复核 | D2 最小闭环主要验证群聊；单聊可作为后续补测 |
| 已开通 `im:message:send_as_bot` | 已满足 | D6 真实测试中 Bot 成功发送卡片回复 |
| 应用可用范围包含测试用户和测试群成员 | 已满足 | 测试群能完成真实收发 |
| 机器人已加入测试群并允许发言 | 已满足 | D6 handoff 已记录真实测试群回复成功 |

说明：D2 当晚的真实后台截图不适合提交仓库；当前用后续 D6 的真实飞书收发证据回填 D2 最小闭环结论。D2 本地 replay 仍然是没有权限时的保底验收路径。

## 本地 replay 检查

运行：

```bash
python3 -m memory_engine feishu replay tests/fixtures/feishu_text_remember_event.json
python3 -m memory_engine feishu replay tests/fixtures/feishu_text_recall_event.json
```

预期：

- 第一条返回可发送给飞书的回复内容，包含“已记住”或“记忆确认卡片”。
- 第二条返回召回结果，包含主题、状态、版本、来源和证据。
- replay 不需要真实飞书凭证。

## 测试群 Demo 命令

完整输入见 `docs/day2-demo-inputs.md`。D2 最小闭环优先跑这 4 条：

```text
@Feishu Memory Engine bot /remember 生产部署必须加 --canary --region cn-shanghai
@Feishu Memory Engine bot /recall 生产部署参数
@Feishu Memory Engine bot /remember 不对，生产部署 region 改成 ap-shanghai
@Feishu Memory Engine bot /recall 生产部署 region
```

做对的标准：

- 第一次 `/recall` 能看到 `cn-shanghai`。
- 覆盖更新后第二次 `/recall` 只返回 `ap-shanghai`。
- 回复里有 `memory_id`，方便继续查 `/versions`。
- 回复不泄露真实 token、内部链接或完整用户 ID。

## 回复文案人工审查

| 场景 | 结论 | 建议 |
|---|---|---|
| `/remember` 成功 | 能看懂 | 第一行保留“已记住/记忆确认”，后面列主题、状态、版本 |
| `/recall` 成功 | 能看懂 | 继续保持“当前有效规则”和证据摘录 |
| 矛盾更新 | 能看懂 | 必须保留“旧规则 -> 新规则” |
| 未知命令 | 能看懂 | 白名单比沉默更适合 Demo |
| 敏感信息 | 已有遮挡 | 后续仍要避免把真实 token 输入测试群 |

## 失败时记录模板

如果后续复测失败，按这个格式补到本文件末尾：

```text
时间：
测试位置：群聊 / 单聊
输入命令：
预期结果：
实际结果：
终端日志路径：logs/feishu-bot/feishu-listen-<timestamp>.ndjson
飞书页面提示：
下一步判断：
```

## D2 队友任务完成对照

| 原任务 | 完成情况 |
|---|---|
| 用测试群真实试 `/remember`、`/recall` | 已用 D6 真实收发证据回填；D2 最小命令见本文件 |
| 记录失败输入和 Bot 回复截图 | 仓库只记录文字结论；真实截图不提交 |
| 补 20 条飞书 Demo 用语料 | 已写入 `docs/day2-demo-inputs.md` |
| 写 5 分钟 Demo 台词 | D1 脚本已覆盖 CLI 主线，D2 用 `docs/day2-demo-inputs.md` 替换为飞书群聊输入 |
| 检查回复文案是否对评委清楚 | 已写入“回复文案人工审查” |
