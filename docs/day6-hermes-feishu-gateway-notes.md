# Day 6 Hermes Feishu Gateway Notes

日期：2026-04-25

参考文件：

- `.reference/hermes-agent/gateway/platforms/feishu.py`
- `.reference/hermes-agent/tools/memory_tool.py`

用途：只吸收可用于初赛 Demo 稳定性和安全表达的机制；不把 Hermes Agent 作为运行时依赖。

## 可吸收机制

| Hermes 机制 | 观察 | 本项目 D6 处理 |
| --- | --- | --- |
| @mention gating | 群聊消息需要明确 @Bot 或符合策略，避免吞全量群消息 | 已沿用群聊必须 @Bot 的使用约定；当前 parser 会剥离 mention 后处理 slash 命令 |
| 消息去重 | Hermes 对 message_id 做 TTL dedup，并持久化去重状态 | 当前 repository 用 `source_type + source_id` 去重；重复投递返回 duplicate 提示，不重复写入 |
| allowlist / group policy | Hermes 支持 allowlist、blacklist、admin_only、disabled 等群策略 | D6 先做命令白名单；用户 allowlist 放到复赛或真实多群演示前 |
| 每 chat 串行处理 | Hermes 对同一 chat 使用 lock，避免并发覆盖顺序混乱 | 当前本地 listen 是单进程顺序处理；如果后续部署成多 worker，需要加 chat-level lock |
| 卡片事件 fallback | Hermes 将 card action 转成 synthetic command，并对重复 token 去重 | D6 先生成 JSON 源码和结构化文本；真实按钮回调放到复赛 |
| 回复失败 fallback | Hermes 对 reply 失败码回落为新消息 | 当前 `LarkCliPublisher` 已在 reply 失败后尝试 send fallback；结构化文本是最终保底路径 |
| 自发消息过滤 | Hermes 会丢弃 bot 自己发送的消息，避免循环 | 当前 `message_event_from_payload` 标记 `bot self message`，handler 不回复 |
| 内容安全扫描 | Hermes `memory_tool.py` 对 prompt injection、secret/exfil、不可见字符做写入前扫描 | D6 完成设计说明，并先在 Bot 回复层遮挡 secret/token/内部 URL |

## 本轮吸收

### 1. 命令白名单

D6 将支持命令集中为 `SUPPORTED_COMMANDS`：

```text
/remember
/recall
/versions
/help
/health
/ingest_doc
/confirm
/reject
```

未知命令不进入业务分支，并在回复中展示白名单。

### 2. 重复消息提示

重复 `message_id` 返回：

```text
状态：duplicate
处理结果：这条飞书消息已处理过，已跳过重复写入。
```

这满足 D6 “重复消息提示”要求。当前去重依赖数据库 raw event；只要同一 SQLite 库未丢失，就能跨 handler 调用生效。

### 3. 结构化文本 fallback

当前真实发送仍使用纯文本消息：

- 对评委截图来说足够稳定。
- 不依赖 interactive card 权限或回调配置。
- 如果后续启用 card JSON 发送失败，可以直接回落到同一份文本结构。

### 4. 卡片事件预留

Hermes 的 card action 会合成为 `/card <action>` 事件。本项目后续可以采用更窄的动作集合：

```text
/confirm <candidate_id>
/reject <candidate_id>
/versions <memory_id>
```

不建议 D6 直接引入 `/card` 泛命令，因为它会扩大 handler 面积，也会让测试和权限解释变复杂。

## 本轮拒绝

| 机制 | 拒绝原因 |
| --- | --- |
| 引入 Hermes runtime 或 lark_oapi SDK | 初赛当前闭环基于 `lark-cli`，新增依赖会扩大安装和权限风险 |
| 完整 group policy DSL | 当前只有一个测试群和一条 Demo 主链路；命令白名单和 @Bot 约定足够 |
| 持久化 dedup cache 文件 | SQLite raw event 已能覆盖当前重复投递场景；再加文件会产生状态维护成本 |
| 真实 card action callback | 需要开放平台事件订阅和回调调试；D6 提前执行阶段不适合加不可验证链路 |
| 多 worker chat lock | 当前 `listen` 单进程串行处理；多 worker 部署尚未进入初赛 P0 |
| 强制写入前安全拦截 | 可能误伤 Demo 文档；D6 先做回复层遮挡和设计说明，后续用测试集校准 |

## 后续落地顺序

1. D7 benchmark 扩容时增加安全扫描 case：prompt injection、secret、不可见字符。
2. 若真实群聊压力测试出现并发覆盖，再补 chat-level lock。
3. 若直播后评分明显偏产品交互，再启用 interactive card 发送和按钮回调。
4. 若多人测试或真实组织部署，优先补用户 allowlist 和管理员配置。

## 当前验收判断

D6 已吸收的 Hermes 机制足够支撑初赛演示：

- 评委能看到“企业记忆卡片”的核心字段。
- 重复投递不会污染记忆。
- 未知命令被白名单拦截。
- 回复中不会直接展示明显 secret、token 或完整内部链接。
- 真实卡片失败不会阻塞，因为演示默认路径是结构化文本。
