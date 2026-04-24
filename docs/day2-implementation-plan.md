# Day 2 实现计划：接入飞书 Bot 最小闭环

日期：2026-04-25  
阶段：Day 2  
目标：在 Day 1 本地记忆引擎基础上，打通真实飞书 Bot 的 `接收消息 -> 写入/召回记忆 -> 回复飞书` 最小闭环。

## 1. Day 1 当前基线

仓库当前已完成：

- 本地 CLI：`init-db`、`remember`、`recall`、`versions`、`benchmark run`。
- SQLite schema：`raw_events`、`memories`、`memory_versions`、`memory_evidence`。
- 规则抽取：按关键词推断 type、subject、reason。
- 矛盾更新：同 scope/type/subject 下，新规则覆盖旧规则，旧版本标记 `superseded`。
- Benchmark：10 条 Day 1 case，当前通过率 100%。
- 图源码和文档：总览图、产品流程图、系统架构图、评测闭环图。

已验证：

```bash
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

当前没有阻塞性问题。已发现并修复一个小问题：重复写入同一条 active 记忆时，返回版本号原先固定为 `1`，现改为返回当前 active version。

## 2. Day 2 不变原则

Day 2 只做飞书 Bot 最小闭环，不扩展过多能力。

### 2.1 P0 必做

1. 读取飞书应用配置。
2. 启动飞书长连接事件监听。
3. 接收 `im.message.receive_v1`。
4. 解析文本消息中的 `/remember` 和 `/recall`。
5. 调用现有 `MemoryRepository`。
6. 用 Bot 回复文本结果。
7. 提供 fake event replay，本地无飞书环境也能测试 handler。
8. 更新 README 和 Day 2 handoff。

### 2.2 P1 可做

1. 支持 `/versions <memory_id>`。
2. 支持更友好的飞书回复格式。
3. 将 Bot 回复挂到原消息线程。
4. 增加 `source_type=feishu_message`、`source_id=message_id`。
5. 增加飞书事件去重表或使用 `raw_events.source_id` 做幂等。

### 2.3 Day 2 不做

- H5 管理台。
- Bitable 同步。
- 文档 ingest。
- 群聊全量消息监听。
- 交互卡片按钮。
- embedding。
- 遗忘提醒。

这些放到 Day 3 以后。Day 2 的价值是把 Demo 从“本地可跑”推进到“飞书里可演示”。

## 3. 推荐实现路线

### 3.1 依赖选择

推荐新增官方 SDK：

```toml
dependencies = [
  "lark-oapi>=1.4.8"
]
```

理由：

- 飞书长连接事件订阅官方 Python 示例使用 `lark-oapi`。
- 长连接不需要公网地址，适合本地开发和比赛演示。
- SDK 负责 token、长连接、事件结构，减少手写 OpenAPI 风险。

备用方案：

- 如果 Day 2 不想加依赖，可先做 `lark-cli` 调用发送消息，但事件接收仍然缺少稳定入口。
- 因此 P0 推荐接受 `lark-oapi` 作为唯一新增依赖。

实现备注：

- 2026-04-24 执行时改为优先使用本机 `lark-cli` 完成长连接事件订阅和 Bot 回复。
- 当前实现不新增 `lark-oapi` 依赖；`feishu listen` 内部调用 `lark-cli event +subscribe`，回复调用 `lark-cli im +messages-reply` / `+messages-send`。
- 原 `lark-oapi` 路线保留为备用方案，仅在 `lark-cli` 无法覆盖运行时能力时再考虑。

### 3.2 新增模块

建议文件：

```text
memory_engine/
├── feishu_config.py
├── feishu_events.py
├── feishu_messages.py
├── feishu_publisher.py
└── feishu_runtime.py
```

职责：

| 文件 | 职责 |
|---|---|
| `feishu_config.py` | 读取 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`MEMORY_DB_PATH` |
| `feishu_events.py` | 将飞书事件对象转换为内部 `FeishuTextEvent` |
| `feishu_messages.py` | 解析 `/remember`、`/recall`、`/versions` |
| `feishu_publisher.py` | 封装发送消息或回复消息 |
| `feishu_runtime.py` | 启动长连接 client，注册事件 handler |

CLI 新增：

```bash
python3 -m memory_engine feishu listen
python3 -m memory_engine feishu replay tests/fixtures/feishu_message_event.json
```

`listen` 用于真实飞书长连接。  
`replay` 用于本地测试，不需要飞书凭证。

## 4. 配置与权限

### 4.1 环境变量

`.env` 不提交，只在本机配置：

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
MEMORY_DB_PATH=data/memory.sqlite
FEISHU_BOT_MODE=reply
```

`FEISHU_BOT_MODE`：

- `reply`：优先回复原消息。
- `send`：直接向 chat_id 发送消息。

Day 2 默认用 `reply`，减少群聊打扰。

### 4.2 最小权限

应用身份权限：

```text
im:message.group_at_msg:readonly
im:message.p2p_msg:readonly
im:message:send_as_bot
```

事件订阅：

```text
im.message.receive_v1
```

应用配置：

- 开启机器人能力。
- 应用可用范围包含你和测试群成员。
- 机器人加入测试群。
- 事件订阅方式选择长连接。

### 4.3 不申请的权限

Day 2 不申请：

```text
im:message.group_msg
```

原因：这是群聊全量消息敏感权限，不是最小闭环必需项。先用 @机器人或单聊即可。

## 5. 内部事件契约

新增内部 dataclass：

```python
@dataclass(frozen=True)
class FeishuTextEvent:
    message_id: str
    chat_id: str
    chat_type: str
    sender_id: str
    text: str
    create_time: int
```

转换原则：

- 只处理 `message_type == "text"`。
- 忽略机器人自己发送的消息，避免自触发循环。
- 去掉 @Bot mention 文本。
- 保留原始 `message_id` 作为 `source_id`。
- `scope` 默认映射为 `chat:<chat_id>`，也支持配置为 `project:feishu_ai_challenge`。

Day 2 推荐默认 scope：

```text
chat:<chat_id>
```

但为了和 Day 1 benchmark、CLI Demo 保持一致，可以通过环境变量覆盖：

```bash
MEMORY_DEFAULT_SCOPE=project:feishu_ai_challenge
```

## 6. 飞书指令设计

### 6.1 `/remember`

输入：

```text
/remember 生产部署必须加 --canary --region cn-shanghai
```

处理：

```python
repo.remember(
    scope,
    content,
    source_type="feishu_message",
    source_id=event.message_id,
    sender_id=event.sender_id,
    created_by=event.sender_id,
)
```

回复：

```text
已记住
主题：生产部署
类型：workflow
状态：active
版本：1
来源：当前消息
```

如果 action 是 `superseded`：

```text
已更新记忆
主题：生产部署
新版本：2
旧版本已标记为 superseded
```

如果 action 是 `needs_manual_review`：

```text
检测到同主题不同内容，但没有明确覆盖意图。
请用“不对/改成/以后统一”等表达确认覆盖。
```

### 6.2 `/recall`

输入：

```text
/recall 生产部署参数是什么
```

回复：

```text
命中记忆：生产部署
当前有效规则：生产部署必须加 --canary --region cn-shanghai
版本：1
证据：生产部署必须加 --canary --region cn-shanghai
```

未命中：

```text
未找到相关 active 记忆。
可以用 /remember 先写入一条。
```

### 6.3 `/versions`

P1 支持：

```text
/versions mem_xxx
```

回复当前 memory 的版本链。

## 7. 幂等设计

飞书事件可能重复投递。Day 2 必须处理。

最低实现：

1. 在 `raw_events` 中查询 `source_type='feishu_message' AND source_id=<message_id>`。
2. 如果已存在，跳过写入并返回“已处理过”。

当前 `raw_events` 没有唯一约束。Day 2 可以先在 repository 层查重，不改 schema；如果时间允许，增加索引：

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_events_source_unique
  ON raw_events(source_type, source_id);
```

如果加唯一索引，需要注意 Day 1 benchmark 的 `source_type=benchmark` 自动生成 source_id 不受影响。

## 8. 本地测试设计

### 8.1 fake event fixture

新增：

```text
tests/fixtures/feishu_text_remember_event.json
tests/fixtures/feishu_text_recall_event.json
```

结构只保留 handler 必需字段：

```json
{
  "message_id": "om_test_001",
  "chat_id": "oc_test",
  "chat_type": "group",
  "sender_id": "ou_test",
  "message_type": "text",
  "content": "{\"text\":\"/remember 生产部署必须加 --canary\"}",
  "create_time": "1777000000000"
}
```

### 8.2 replay 命令

```bash
python3 -m memory_engine feishu replay tests/fixtures/feishu_text_remember_event.json
python3 -m memory_engine feishu replay tests/fixtures/feishu_text_recall_event.json
```

replay 不真实发送飞书消息，只输出将要发送的回复 JSON：

```json
{
  "reply_to": "om_test_001",
  "text": "已记住..."
}
```

这能保证 CI/本地无凭证也可验证业务逻辑。

## 9. 验证命令

Day 2 完成前必须通过：

```bash
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine feishu replay tests/fixtures/feishu_text_remember_event.json
python3 -m memory_engine feishu replay tests/fixtures/feishu_text_recall_event.json
```

如果配置了真实飞书应用，再手动验证：

```bash
python3 -m memory_engine feishu listen
```

飞书测试：

```text
/remember 生产部署必须加 --canary --region cn-shanghai
/recall 生产部署参数
不对，生产部署 region 改成 ap-shanghai
/recall 生产部署 region
```

验收：

- Bot 能收到消息。
- Bot 能回复。
- `/remember` 写入 SQLite。
- `/recall` 返回 active 记忆。
- 覆盖更新后只返回新规则。
- 回复中带 evidence。

## 10. Day 2 任务拆解

### 10.1 你白天主线

按顺序执行：

1. 加 `lark-oapi` 依赖。
2. 新增 `feishu_config.py`。
3. 新增 `feishu_messages.py`，只解析 `/remember`、`/recall`。
4. 新增 `feishu_events.py`，实现飞书事件到内部事件转换。
5. 新增 replay fixture。
6. 新增 replay 命令。
7. 新增 `feishu_publisher.py`，先实现 dry-run publisher。
8. 新增 `feishu_runtime.py`，接长连接真实事件。
9. 接真实 Bot 回复。
10. 更新 README 和 handoff。

### 10.2 队友晚上任务

队友不接核心代码。安排：

1. 用测试群真实试 `/remember`、`/recall`。
2. 记录失败输入和 Bot 回复截图。
3. 补 20 条飞书 Demo 用语料。
4. 写 5 分钟 Demo 台词：
   - 手动注入
   - 抗干扰
   - 矛盾更新
   - 证据链
5. 检查回复文案是否对评委清楚。

## 11. Day 2 完成标准

必须满足：

- 本地 benchmark 仍 100% 通过。
- fake event replay 可跑。
- 真实飞书 Bot 至少完成一次 `/remember` 和 `/recall`。
- 代码不提交 `.env`、数据库、日志。
- README 写清楚飞书启动方式。
- 新增 Day 2 handoff。
- 提交并推送远程。

可选加分：

- 真实飞书回复使用 `reply` 挂到原消息。
- 加事件去重。
- 加 `/versions`。
- 回复中输出 `memory_id`，方便 Demo 查版本链。

## 12. 风险与回退

| 风险 | 表现 | 回退方案 |
|---|---|---|
| 飞书应用权限没批 | 收不到事件或发不出消息 | 先用 replay 命令完成本地可验收闭环 |
| 长连接 SDK 配置失败 | listen 启动失败 | 用 `lark-cli` 或官方 API 调试台验证 app_id/app_secret |
| 事件结构和预期不一致 | text 解析失败 | 先打印 raw event，补转换适配 |
| Bot 在群里刷屏 | 回复太频繁 | 只响应 `/remember`、`/recall` 和 @Bot |
| 重复事件导致重复写入 | 同一消息多次创建 evidence | 按 `message_id` 做幂等 |
| 真实飞书调试耗时 | 白天被配置卡住 | 保持 replay + dry-run 为主验收，真实飞书只作为最后一段 |

## 13. Day 2 Commit 要求

提交前运行：

```bash
git status --short
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine feishu replay tests/fixtures/feishu_text_remember_event.json
python3 -m memory_engine feishu replay tests/fixtures/feishu_text_recall_event.json
```

提交信息建议：

```text
Connect the local memory loop to Feishu bot events

Implemented the minimal Feishu receive/reply path so the Day 1 local memory engine can be exercised from a real Feishu conversation.

Constraint: Avoid broad group message permissions on Day 2
Rejected: Build H5/Bitable first | does not prove the conversational memory loop
Tested: python3 -m compileall memory_engine scripts
Tested: python3 -m memory_engine benchmark run benchmarks/day1_cases.json
Tested: python3 -m memory_engine feishu replay tests/fixtures/feishu_text_remember_event.json
Not-tested: production deployment
```
