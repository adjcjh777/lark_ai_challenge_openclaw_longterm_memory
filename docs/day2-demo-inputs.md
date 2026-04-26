# Day 2 飞书 Bot Demo 输入语料

日期：2026-04-25  
用途：补齐 D2 队友任务中的飞书群聊 Demo 输入。

## 给队友先看这个

群聊里统一使用机器人显示名 `Feishu Memory Engine bot`。单聊机器人时可以省略 @，直接发送 `/remember`、`/recall` 或 `/versions`。

## 10 条最小演示输入

这 10 条用于 5 分钟 Demo，顺序不要打乱。

```text
@Feishu Memory Engine bot /remember 生产部署必须加 --canary --region cn-shanghai
@Feishu Memory Engine bot /recall 生产部署参数
@Feishu Memory Engine bot /remember 不对，生产部署 region 改成 ap-shanghai
@Feishu Memory Engine bot /recall 生产部署 region
@Feishu Memory Engine bot /remember 周报以后统一发飞书文档链接
@Feishu Memory Engine bot /recall 周报怎么发
@Feishu Memory Engine bot /remember 后端框架最终采用 FastAPI
@Feishu Memory Engine bot /recall 后端框架
@Feishu Memory Engine bot /versions <上一步回复里的 memory_id>
@Feishu Memory Engine bot /help
```

## 10 条补充演示输入

这些用于备用截图或队友人工测试。

```text
@Feishu Memory Engine bot /health
@Feishu Memory Engine bot /remember Benchmark 报告周日 20:00 前完成
@Feishu Memory Engine bot /recall Benchmark 报告截止时间
@Feishu Memory Engine bot /remember 飞书 Bot 权限必须包含 group_at_msg、p2p_msg 和 send_as_bot
@Feishu Memory Engine bot /recall 飞书机器人权限
@Feishu Memory Engine bot /remember 不对，周报以后统一发给 Bob，不再发给 Alice
@Feishu Memory Engine bot /recall 周报发给谁
@Feishu Memory Engine bot /remember API_TOKEN=demo_secret_placeholder 生产部署仍然必须走 canary
@Feishu Memory Engine bot /recall 生产部署 token
@Feishu Memory Engine bot /unknown 生产部署
```

## 预期截图点

| 输入 | 需要看到什么 |
|---|---|
| `/remember 生产部署...` | 回复“已记住”，包含主题、状态、版本、来源 |
| `/recall 生产部署参数` | 返回当前有效规则和证据 |
| `/remember 不对...改成...` | 返回矛盾更新，旧规则被覆盖 |
| 第二次 `/recall` | 只返回 `ap-shanghai`，不再默认返回 `cn-shanghai` |
| `/versions <memory_id>` | 能看到 v1 已覆盖、v2 active |
| `API_TOKEN=...` 样例 | 回复中 token 被遮挡 |
| `/unknown` | 回复命令白名单 |

## 回复文案检查口径

- 评委第一眼要看到“结论”。
- 每次写入或召回都要能看到“状态”和“版本”。
- 召回结果必须有证据，不能只有一句答案。
- 矛盾更新必须能看出“旧规则 -> 新规则”。
- 未知命令不能沉默，要告诉用户用 `/help`。
