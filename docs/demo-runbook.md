# 真实飞书 Demo Runbook

目标：用 5 分钟证明 Memory Engine 不是普通搜索，而是带状态、版本和来源证据的企业协作记忆。

## 演示前准备，30 秒

启动 Bot：

```bash
scripts/start_feishu_bot.sh
```

确认测试群：

- 群名：内部测试群，真实名称不提交到公开仓库。
- Bot：`Feishu Memory Engine bot`
- 默认 scope：`project:feishu_ai_challenge`

## 5 分钟流程

### 1. 展示命令入口，30 秒

在群里发送：

```text
@Feishu Memory Engine bot /help
```

讲解口径：

> 这里先用 `/help` 作为 Day 3 的 slash command palette 替代。评委能直接看到可用命令和推荐输入。

截图需求：`/help` 输入和 Bot 回复。

### 2. 写入一条决策记忆，60 秒

发送：

```text
@Feishu Memory Engine bot /remember 生产部署必须加 --canary --region cn-shanghai
```

预期 Bot 回复包含：

- 类型：已记住
- 主题：生产部署
- 状态：active
- 版本：v1
- 来源：当前飞书消息
- memory_id

讲解口径：

> 系统把聊天里的协作信息压缩成结构化记忆，而不是只保存原消息。

截图需求：写入命令、Bot 回复、`memory_id`。

### 3. 召回当前有效规则，60 秒

发送：

```text
@Feishu Memory Engine bot /recall 生产部署参数
```

预期 Bot 回复包含：

- 类型：记忆召回
- 主题：生产部署
- 状态：active
- 版本：v1
- 当前有效规则：生产部署必须加 `--canary --region cn-shanghai`
- 证据：原始写入内容

讲解口径：

> 召回结果会说明状态、版本和来源证据，方便团队判断这是不是当前有效结论。

截图需求：召回命令和 Bot 回复。

### 4. 覆盖更新旧规则，75 秒

发送：

```text
@Feishu Memory Engine bot /remember 不对，生产部署 region 改成 ap-shanghai
```

再发送：

```text
@Feishu Memory Engine bot /recall 生产部署 region
```

预期 Bot 回复：

- 更新回复显示版本变成 v2。
- 召回只返回 `ap-shanghai`。
- 不再把 `cn-shanghai` 当作当前有效规则。

讲解口径：

> 普通搜索容易把新旧消息一起搜出来；Memory Engine 会把旧版本标记为 superseded，只返回 active 版本。

截图需求：覆盖命令、更新回复、第二次召回回复。

### 5. 查看版本链，60 秒

从写入或召回回复里复制 `memory_id`，发送：

```text
@Feishu Memory Engine bot /versions mem_xxx
```

预期 Bot 回复：

- 类型：版本链
- 状态：active
- 版本数量：2
- v1 `[superseded]`
- v2 `[active]`

讲解口径：

> 版本链是“企业记忆”区别于聊天搜索的关键：它保留历史，但明确告诉你现在该相信哪个版本。

截图需求：`/versions` 命令和完整版本链。

### 6. 健康检查和异常输入，45 秒

发送：

```text
@Feishu Memory Engine bot /health
@Feishu Memory Engine bot /unknown
```

预期：

- `/health` 返回数据库路径、默认 scope、dry-run 状态。
- `/unknown` 返回 unknown_command，并引导 `/help`。

讲解口径：

> Demo 现场如果网络或权限波动，可以先用 `/health` 判断 Bot 接入、数据库和运行模式。

截图需求：`/health` 和未知命令处理。

## 评委问答口径

- 为什么不是普通搜索？
  - 普通搜索返回消息列表；Memory Engine 返回当前有效结论。
  - 普通搜索不理解覆盖关系；Memory Engine 有 active / superseded 状态。
  - 普通搜索不给版本链；Memory Engine 可以展示 v1 到 v2 的演变。
  - 普通搜索只证明“说过”；Memory Engine 同时给出来源证据和当前状态。

- 如果飞书现场权限失败怎么办？
  - 本地 replay 可以完整演示同一套 handler。
  - `docs/day3-handoff.md` 已记录真实群、profile 和保底验证命令。
