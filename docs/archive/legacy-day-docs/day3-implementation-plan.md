# Day 3 实现计划：真实飞书 Bot 稳定化与 Demo 口径

日期：2026-04-26
阶段：Day 3
目标：在 Day 2 飞书 Bot 最小闭环基础上，把真实测试群演示稳定到评委可看懂、外部分工可复测、现场可兜底的状态。

## 1. Day 2 当前基线

仓库当前已完成：

- `python3 -m memory_engine feishu listen`：通过 `lark-cli event +subscribe` 监听 `im.message.receive_v1`。
- `python3 -m memory_engine feishu replay <fixture>`：不依赖飞书凭证即可 replay fake event。
- `/remember`、`/recall`、`/versions` 已接入 `MemoryRepository`。
- 飞书消息使用 `source_type=feishu_message`、`source_id=message_id` 做来源记录。
- `raw_events(source_type, source_id)` 可用于消息幂等，避免重复投递重复写入。
- `scripts/start_feishu_bot.sh` 已提供真实监听启动入口。

已验证：

```bash
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine feishu replay tests/fixtures/feishu_text_remember_event.json
python3 -m memory_engine feishu replay tests/fixtures/feishu_text_recall_event.json
```

Day 2 留给 Day 3 的主要缺口：

- 回复像日志，不够像 Demo 产品口径。
- 非文本、空消息、机器人自发消息、重复消息、未知命令没有统一说明。
- slash command palette 不能在 Bot 后端直接实现，需要低成本替代。
- 真实群验证路径、后台配置、未验证项需要形成 handoff。

## 2. Day 3 不变原则

Day 3 只稳定真实 Bot 和 Demo 口径，不扩大核心记忆能力。

### 2.1 P0 必做

1. 用真实飞书测试群跑通 `/remember`、`/recall`、`/versions`。
2. Bot 回复统一包含稳定字段：
   - 类型
   - 主题
   - 状态
   - 版本
   - 来源
3. 明确处理：
   - 非文本消息
   - 空消息
   - 机器人自发消息
   - 重复消息
   - 未知命令
4. 新增 `docs/day3-handoff.md`，记录真实飞书配置、验证结果、未验证项。

### 2.2 P1 可做

1. 增加 `/help`，返回命令列表、参数示例和 Demo 推荐输入。
2. 增加 `/health`，返回数据库路径、默认 scope、dry-run 状态和回复模式。
3. 新增 `docs/demo-runbook.md`，给出 5 分钟真实飞书 Demo 流程。
4. 将回复从“纯字段表”升级为“结论句 + 稳定字段”，提高评委可读性。

### 2.3 Day 3 不做

- 飞书卡片 JSON。
- Bitable 同步。
- 文档 ingestion。
- 深度 Benchmark 扩容。
- embedding 语义检索。
- H5 管理台。
- 群聊全量消息监听。

这些分别放到 D4、D5、D6、D7 后续阶段。Day 3 的价值是让真实 Bot 闭环稳定、清楚、可演示。

## 3. 实现路线

### 3.1 事件解析升级

Day 2 的解析函数只返回文本事件或 `None`。Day 3 需要保留“可回复但不进入记忆”的消息，因此新增更宽的内部事件：

```python
@dataclass(frozen=True)
class FeishuMessageEvent:
    message_id: str
    chat_id: str
    chat_type: str
    sender_id: str
    sender_type: str
    message_type: str
    text: str
    create_time: int
    raw: dict[str, Any]
    ignore_reason: str | None = None
```

处理规则：

| 场景 | 行为 |
|---|---|
| 非 `im.message.receive_v1` | 忽略，不回复 |
| 缺少 `message_id` 或 `chat_id` | 忽略，不回复 |
| `sender_type == bot` | 忽略，不回复，避免循环 |
| `message_type != text` | 回复“暂时只支持文本消息” |
| 文本为空 | 回复“收到空消息，未写入记忆” |
| 文本正常 | 进入命令解析 |

保留 `text_event_from_payload` 兼容旧调用，但真实 runtime 使用 `message_event_from_payload`。

### 3.2 命令解析升级

Day 3 支持命令：

```text
/remember <内容>
/recall <查询>
/versions <memory_id>
/help
/health
```

解析规则：

- 命令名统一 lower-case。
- `/remember`、`/recall`、`/versions` 缺参数时转为 `/help <command>`。
- 未知 `/xxx` 返回 `unknown_command`，不静默忽略。
- 非 slash 文本在群聊中作为未知输入处理，引导 `/help`。

### 3.3 稳定回复契约

所有 Bot 业务回复采用两段式：

```text
一句评委能直接理解的中文结论。

类型：...
主题：...
状态：...
版本：...
来源：...
```

命令回复要求：

| 命令 | 结论句 | 稳定字段 |
|---|---|---|
| `/remember` 新建 | 已保存为当前有效记忆，后续可以直接召回。 | 类型、主题、状态、版本、来源、记忆类型、memory_id |
| `/remember` 覆盖 | 已更新这条记忆，后续召回会优先使用新版本。 | 类型、主题、状态、版本、来源、记忆类型、处理结果、memory_id |
| `/recall` 命中 | 当前有效结论：`<answer>` | 类型、主题、状态、版本、来源、记忆类型、当前有效规则、memory_id、证据 |
| `/recall` 未命中 | 暂时没找到当前有效记忆。 | 类型、主题、状态、版本、来源、处理结果、下一步 |
| `/versions` | 这是这条记忆的版本链，active 版本是当前有效结论。 | 类型、主题、状态、版本、来源、版本数量、版本列表 |
| `/help` | 我可以帮你记住、召回和查看团队决策的版本链。 | 类型、主题、状态、版本、来源、命令列表、Demo 推荐输入 |
| `/health` | Bot 当前可用，下面是本次运行状态。 | 类型、主题、状态、版本、来源、数据库、默认 scope、dry-run、回复模式 |

### 3.4 幂等与重复消息

保持 Day 2 的 `raw_events(source_type, source_id)` 幂等策略：

```text
source_type = feishu_message
source_id = event.message_id
```

如果 `message_id` 已处理过：

- 不再次调用 `repo.remember`。
- 回复稳定提示：

```text
这条消息之前已经处理过，不会重复写入。

类型：消息处理
主题：重复投递
状态：duplicate
版本：-
来源：当前飞书消息
处理结果：这条飞书消息已处理过，已跳过重复写入。
```

### 3.5 真实群触发方式

飞书群聊普通 `/help` 不一定触发 `im.message.receive_v1` 的 group_at 事件。Day 3 真实群 Demo 统一使用：

```text
@Feishu Memory Engine bot /help
@Feishu Memory Engine bot /remember ...
```

CLI 主动发群时使用本机环境变量，不提交真实值：

```bash
export FEISHU_TEST_CHAT_ID="oc_xxx"
export FEISHU_BOT_OPEN_ID="ou_xxx"

lark-cli im +messages-send \
  --profile feishu-ai-challenge \
  --as user \
  --chat-id "$FEISHU_TEST_CHAT_ID" \
  --content "{\"text\":\"<at user_id=\\\"$FEISHU_BOT_OPEN_ID\\\">Feishu Memory Engine bot</at> /help\"}" \
  --msg-type text
```

真实标识获取步骤写入 `docs/reference/local-lark-cli-setup.md`，公开文档只保留占位符。

## 4. 安全与文档规则

Day 3 后所有公开文档遵守：

- 不提交真实 `chat_id`。
- 不提交真实 Bot `open_id`。
- 不提交真实 App ID。
- 不提交 App Secret、token、refresh token。
- 不提交真实测试群名称。
- 不提交一次性 Demo `memory_id`。

真实值只放本机 `.env.local`，该文件已被 `.gitignore` 忽略。

提交前扫描：

```bash
rg -n "oc_[a-zA-Z0-9]{8,}|ou_[a-zA-Z0-9]{8,}|cli_[a-zA-Z0-9]{8,}" README.md docs memory_engine scripts
```

如果 Git 历史已经出现真实运行标识，先记录到 `docs/day3-security-risk-decision.md`。是否执行 history rewrite + force push 需要单独授权，因为这会改变远端提交图。

## 5. 测试计划

### 5.1 本地自动验证

```bash
python3 -m compileall memory_engine scripts
python3 -m unittest discover -s tests
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

### 5.2 Replay 验证

使用临时 SQLite，不动 `data/memory.sqlite`：

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

### 5.3 真实飞书验证

前置：

```bash
lark-cli doctor --profile feishu-ai-challenge
source .env.local
```

启动监听：

```bash
MEMORY_DEFAULT_SCOPE=project:feishu_ai_challenge \
LARK_CLI_PROFILE=feishu-ai-challenge \
FEISHU_BOT_MODE=reply \
scripts/start_feishu_bot.sh
```

真实群验收序列：

1. `@Feishu Memory Engine bot /help`
2. `@Feishu Memory Engine bot /health`
3. `@Feishu Memory Engine bot /remember 生产部署必须加 --canary --region cn-shanghai`
4. `@Feishu Memory Engine bot /recall 生产部署参数`
5. `@Feishu Memory Engine bot /remember 不对，生产部署 region 改成 ap-shanghai`
6. `@Feishu Memory Engine bot /recall 生产部署 region`
7. `@Feishu Memory Engine bot /versions <memory_id>`
8. `@Feishu Memory Engine bot /unknown`

验收重点：

- 写入决策成功。
- 召回能返回当前 active 决策。
- 覆盖更新后旧值不再作为当前有效规则返回。
- 版本链能显示 `superseded` 和 `active`。
- `/help`、`/health` 能作为现场兜底入口。
- 未知命令和异常输入不静默失败。

## 6. 交付物

Day 3 完成后应至少新增或更新：

```text
memory_engine/feishu_events.py
memory_engine/feishu_messages.py
memory_engine/feishu_runtime.py
tests/test_feishu_day3.py
tests/fixtures/feishu_*_event.json
docs/day3-handoff.md
docs/demo-runbook.md
docs/day3-security-risk-decision.md
README.md
```

## 7. 历史补充任务

外部分工不需要改核心逻辑，重点做 Demo 可理解性补充：

1. 按 `docs/demo-runbook.md` 在测试群人工跑 2 轮。
2. 每一步记录截图需求：输入、Bot 回复、版本链、异常输入。
3. 标出不够清楚的中文回复，优先改 `memory_engine/feishu_messages.py`。
4. 扩写白皮书“为什么不是普通搜索”段落：
   - active / superseded 状态
   - 版本链
   - 来源证据
   - 覆盖更新
   - 真实飞书协作入口

## 8. 风险与兜底

| 风险 | 表现 | 兜底 |
|---|---|---|
| user token 过期 | CLI 主动发群失败 | 重新 `lark-cli auth login --domain im` |
| 群聊普通 slash 不触发 | `/help` 无回复 | 群聊统一 @Bot，单聊才省略 @ |
| 事件订阅单实例冲突 | `another event +subscribe instance` | 查找旧 `lark-cli event +subscribe` 进程并停止 |
| 真实标识误入文档 | GitHub 显示 `oc_xxx` / `ou_xxx` | 立即脱敏；是否重写历史单独决策 |
| 现场飞书权限失败 | 收不到事件或发不出消息 | 用 replay + runbook 截图演示同一套 handler |

## 9. 完成标准

- 真实群或 replay 至少一条路径完整可演示。
- 真实群最好完成：写入决策、召回决策、覆盖更新、查看版本。
- Bot 回复每条都能让评委先看到自然中文结论，再看到稳定字段。
- `docs/demo-runbook.md` 有 5 分钟演示流程。
- `docs/day3-handoff.md` 有真实配置获取方式、验证结果和未验证项。
- 当前公开文件不包含真实飞书运行标识。
- 本地验证命令通过。
