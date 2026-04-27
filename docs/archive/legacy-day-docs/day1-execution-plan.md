# Day 1 执行文档：Feishu Memory Engine 最小闭环

日期：2026-04-24
阶段：Day 1
目标：把比赛方案从调研收敛成可执行工程计划，并完成“本地记忆引擎最小闭环”的设计边界。

## 1. Day 1 总目标

Day 1 不追求飞书全链路接通。今天的核心目标是完成以下三件事：

1. **定架构边界**：明确 P0 做什么、不做什么，避免单人执行被飞书 API、H5、OpenClaw、评测、白皮书同时拉散。
2. **定数据契约**：把“企业记忆”落成可以编码的 schema、状态机、版本链、证据链。
3. **定最小闭环**：今天结束时，本地应能用 CLI 或脚本完成 `remember -> recall -> conflict update -> benchmark stub`。

Day 1 成功标准：

- 仓库有清晰文档入口。
- 本地 Memory Engine 的核心数据结构可直接开工。
- 明确 Day 2 接飞书 Bot 时需要哪些 API、权限和事件。
- 历史外部分工能基于文档独立产出测试集和 Demo 文案，不阻塞主线开发。

## 2. P0 产品范围

### 2.1 P0 必须成立的用户故事

用户故事 1：手动注入项目决策

```text
@Memory 记住：生产部署必须加 --canary --region cn-shanghai，不允许直接全量发布，原因是上次全量发布造成 20 分钟故障。
```

系统行为：

- 抽取为结构化决策记忆。
- 记录来源消息。
- 状态为 `active`。
- 后续查询“生产部署参数”时可返回。

用户故事 2：抗干扰召回

```text
中间插入 1000 条无关聊天后，用户问：生产部署参数是什么？
```

系统行为：

- 仍能召回正确 active 记忆。
- 返回证据来源。
- 不返回无关聊天。

用户故事 3：矛盾更新

```text
旧规则：以后周报发给 A。
新规则：不对，以后周报统一发给 B。
```

系统行为：

- A 版本保留，但状态变为 `superseded`。
- B 版本成为 `active`。
- 查询“周报发给谁”只返回 B。
- 版本链能解释 A 被 B 覆盖。

用户故事 4：飞书可展示

系统需要能把召回结果推回飞书消息或卡片。Day 1 只设计契约，Day 2 接入。

### 2.2 Day 1 明确不做

以下内容 Day 1 不做实现，只保留接口或文档位置：

- H5 管理台。
- 自动监听群聊全部消息。
- embedding 语义检索。
- 飞书卡片按钮回调。
- 日历遗忘提醒。
- 云文档全量扫描。
- OpenClaw 插件深度定制。

原因：这些都不是“记住、查回、覆盖、可评测”的最短路径。

## 3. 技术路线定稿

### 3.1 总体路线

采用“双层存储 + 轻量执行层”：

| 层 | 选择 | 作用 |
|---|---|---|
| 本地运行库 | SQLite | 低延迟检索、版本链、Benchmark 批量执行 |
| 飞书协作存储 | 多维表格 Bitable | 人工审核、结构化记忆台账、评委展示、Benchmark 看板 |
| 飞书交互 | Bot 消息 + 卡片 | `/remember`、`/recall`、历史决策提醒 |
| 飞书事件 | 长连接事件订阅 | 本地开发无需公网地址，适合比赛 |
| Agent 工具层 | lark-cli / OpenClaw 官方插件 | 快速操作飞书文档、消息、多维表格 |
| H5 | P1 | 记忆详情页和审核台 |

### 3.2 为什么不是“纯向量库”

纯向量库无法可靠解决本题核心要求：

- **矛盾更新**：向量库会同时召回旧规则和新规则，需要状态机和版本链。
- **证据链**：向量相似度不能替代来源消息、文档、时间戳。
- **权限范围**：企业记忆必须按用户、群、项目、团队隔离。
- **遗忘**：需要 TTL、复习时间、重要性和状态变迁。

所以 Day 1 的核心不是 embedding，而是 `structured memory + lifecycle`。

## 4. 数据模型

### 4.1 记忆类型

| type | 含义 | 示例 |
|---|---|---|
| `decision` | 已达成的团队/项目决策 | 后端采用 FastAPI |
| `preference` | 个人或团队偏好 | 周报优先发飞书文档 |
| `workflow` | 操作流程或命令习惯 | 生产部署必须 canary |
| `deadline` | 截止时间 | 评测报告周日 20:00 前完成 |
| `risk` | 风险或注意事项 | 不要直接全量发布 |
| `owner` | 负责人约定 | Benchmark 由外部分工维护 |
| `term` | 术语或命名约定 | MemoryOps 指本项目 |

Day 1 实现优先级：

1. `decision`
2. `workflow`
3. `preference`

其他类型先保留 enum。

### 4.2 状态机

```text
candidate -> active -> superseded
          -> active -> stale
          -> active -> archived
```

状态定义：

| status | 含义 | 是否默认召回 |
|---|---|---|
| `candidate` | 系统抽取但未确认 | 否 |
| `active` | 当前有效记忆 | 是 |
| `superseded` | 已被新版本覆盖 | 否 |
| `stale` | 可能过期，需要复核 | 否，除非显式要求 |
| `archived` | 废弃但保留审计 | 否 |

Day 1 只实现：

- `active`
- `superseded`

### 4.3 SQLite 表结构

Day 1 最小表结构：

```sql
CREATE TABLE raw_events (
  id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  scope_type TEXT NOT NULL,
  scope_id TEXT NOT NULL,
  sender_id TEXT,
  event_time INTEGER NOT NULL,
  content TEXT NOT NULL,
  raw_json TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE memories (
  id TEXT PRIMARY KEY,
  scope_type TEXT NOT NULL,
  scope_id TEXT NOT NULL,
  type TEXT NOT NULL,
  subject TEXT NOT NULL,
  current_value TEXT NOT NULL,
  reason TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  confidence REAL NOT NULL DEFAULT 0.5,
  importance REAL NOT NULL DEFAULT 0.5,
  source_event_id TEXT,
  active_version_id TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  expires_at INTEGER,
  last_recalled_at INTEGER,
  recall_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE memory_versions (
  id TEXT PRIMARY KEY,
  memory_id TEXT NOT NULL,
  version_no INTEGER NOT NULL,
  value TEXT NOT NULL,
  reason TEXT,
  status TEXT NOT NULL,
  source_event_id TEXT,
  created_by TEXT,
  created_at INTEGER NOT NULL,
  supersedes_version_id TEXT,
  FOREIGN KEY(memory_id) REFERENCES memories(id)
);

CREATE TABLE memory_evidence (
  id TEXT PRIMARY KEY,
  memory_id TEXT NOT NULL,
  version_id TEXT,
  source_type TEXT NOT NULL,
  source_url TEXT,
  source_event_id TEXT,
  quote TEXT,
  created_at INTEGER NOT NULL,
  FOREIGN KEY(memory_id) REFERENCES memories(id)
);
```

Day 1 可以暂不建 `retrieval_logs`，但建议预留迁移文件。

### 4.4 唯一性与冲突判定

一条记忆的逻辑主键：

```text
scope_type + scope_id + type + normalized_subject
```

示例：

```text
project + feishu_ai_challenge + workflow + 生产部署参数
```

冲突判断：

1. 主键相同。
2. 新 `current_value` 与旧 active value 不同。
3. 新输入包含覆盖意图：
   - 不对
   - 改成
   - 以后
   - 统一
   - 最终
   - 从现在起
4. 新证据时间晚于旧证据。

Day 1 先用规则实现，不引入 LLM 判断。

## 5. 飞书接入设计

### 5.1 Day 2 需要接的最小 API

| 用途 | API / 事件 | 权限 |
|---|---|---|
| 接收 @机器人消息 | `im.message.receive_v1` | `im:message.group_at_msg:readonly` |
| 接收单聊消息 | `im.message.receive_v1` | `im:message.p2p_msg:readonly` |
| 发送结果 | `POST /im/v1/messages` | `im:message:send_as_bot` |
| 回复原消息 | `POST /im/v1/messages/:message_id/reply` | `im:message:send_as_bot` 或相关消息权限 |
| 读文档纯文本 | `GET /docx/v1/documents/:id/raw_content` | `docx:document:readonly` |
| 写 Bitable 记录 | `POST /bitable/v1/apps/:app_token/tables/:table_id/records` | `base:record:create` 或 `bitable:app` |
| 更新 Bitable 记录 | `PUT /bitable/v1/apps/:app_token/tables/:table_id/records/:record_id` | `base:record:update` 或 `bitable:app` |

### 5.2 长连接处理原则

飞书长连接事件要求 3 秒内处理完成。实现上必须：

1. 收到事件。
2. 用 `message_id` 去重。
3. 写入 `raw_events` 或内存队列。
4. 立即返回成功。
5. 后台 worker 再抽取、写记忆、发回复。

不要在事件回调里直接调用 LLM 或跑复杂检索。

### 5.3 消息指令

Day 2 飞书 Bot 只支持 4 条指令：

```text
/remember <内容>
/recall <问题>
/update <主题> -> <新值>
/memory status
```

不要一开始做自然语言全自动解析。指令能保证 Demo 稳定。

## 6. 本地 CLI 设计

Day 1 本地 CLI 命令：

```bash
memory remember --scope project:feishu_ai_challenge "生产部署必须加 --canary --region cn-shanghai"
memory recall --scope project:feishu_ai_challenge "生产部署参数"
memory remember --scope project:feishu_ai_challenge "不对，生产部署 region 改成 ap-shanghai"
memory benchmark run benchmarks/day1_cases.json
```

如果今天还没写代码，至少要把接口契约固定下来。

### 6.1 输出格式

`recall` 输出必须带证据，不允许只输出答案：

```json
{
  "answer": "生产部署必须加 --canary --region ap-shanghai",
  "memory_id": "mem_...",
  "status": "active",
  "source": {
    "source_type": "manual_cli",
    "source_id": "evt_...",
    "quote": "不对，生产部署 region 改成 ap-shanghai"
  },
  "version": 2
}
```

## 7. Day 1 工程任务拆解

### 7.1 你白天任务

按优先级执行：

1. 建基础项目结构。
2. 建 SQLite schema。
3. 实现本地 `remember`。
4. 实现本地 `recall`。
5. 实现冲突覆盖。
6. 写 10 条测试样例。
7. 写最小 benchmark runner。
8. 输出 Day 1 晚间 handoff。

建议目录：

```text
.
├── docs/
│   ├── feishu-memory-engine-research-and-plan.md
│   └── day1-execution-plan.md
├── memory_engine/
│   ├── __init__.py
│   ├── cli.py
│   ├── db.py
│   ├── models.py
│   ├── repository.py
│   ├── extractor.py
│   ├── conflict.py
│   └── recall.py
├── benchmarks/
│   └── day1_cases.json
├── scripts/
│   └── init_db.py
├── data/
│   └── .gitkeep
└── README.md
```

### 7.2 历史补充任务

外部分工不应负责会阻塞主线的代码模块。今晚适合做：

1. 补 30 条记忆测试样例。
2. 补 100 条干扰聊天样例。
3. 设计 10 条矛盾更新 case。
4. 写 Demo 脚本第一版。
5. 审查卡片文案是否让评委一眼看懂。
6. 阅读 `docs/feishu-memory-engine-research-and-plan.md`，把白皮书目录提炼成 1 页。

### 7.3 Day 1 晚间交接模板

```md
Day 1 Handoff

今日完成：
- 本地 remember/recall 是否完成：
- 冲突更新是否完成：
- Benchmark runner 是否完成：
- 已知失败 case：

今晚请测：
1. 输入旧规则 -> 新规则，确认只返回新规则。
2. 加入干扰样例后 recall 是否还能命中。
3. Demo 文案是否能在 5 分钟讲清楚。

明天目标：
- 接飞书长连接。
- 支持 /remember 和 /recall。
- 发送飞书文本回复。
```

## 8. Day 1 Benchmark 设计

### 8.1 文件格式

`benchmarks/day1_cases.json`：

```json
[
  {
    "case_id": "conflict_weekly_recipient_001",
    "type": "conflict_update",
    "events": [
      "以后周报统一发给 A。",
      "不对，以后周报统一发给 B。"
    ],
    "query": "周报发给谁",
    "expected_active_value": "B",
    "forbidden_value": "A"
  },
  {
    "case_id": "deploy_param_001",
    "type": "recall",
    "events": [
      "生产部署必须加 --canary --region cn-shanghai，不允许直接全量发布。"
    ],
    "noise_count": 100,
    "query": "生产部署参数是什么",
    "expected_active_value": "--canary --region cn-shanghai"
  }
]
```

### 8.2 Day 1 指标

今天只统计 4 个指标：

| 指标 | 含义 | Day 1 目标 |
|---|---|---:|
| `case_pass_rate` | case 是否通过 | >= 80% |
| `conflict_accuracy` | 矛盾更新是否取新值 | >= 90% |
| `stale_leakage_rate` | 旧值误返回率 | <= 10% |
| `evidence_coverage` | 是否带来源证据 | 100% |

不要今天就追求 Recall@3、MRR、embedding 质量。先验证生命周期。

## 9. 提取规则 Day 1 版本

Day 1 用规则抽取，不依赖 LLM：

### 9.1 决策触发词

```text
决定
最终
统一
以后
必须
不允许
不要
采用
改成
```

### 9.2 subject 规则

先用简单关键词映射：

| 命中文本 | subject |
|---|---|
| 部署 / 发布 / prod | 生产部署 |
| 周报 | 周报收件人 |
| 后端 / 框架 | 后端框架 |
| 截止 / deadline | 截止时间 |
| 负责人 / owner | 负责人 |

后续再替换为 LLM JSON extractor。

### 9.3 current_value 规则

Day 1 可以先保存整句作为 `current_value`，保证版本链跑通。不要过早做复杂字段抽取。

示例：

```json
{
  "subject": "生产部署",
  "current_value": "生产部署必须加 --canary --region cn-shanghai，不允许直接全量发布。",
  "reason": null
}
```

## 10. Bitable 设计草案

Day 1 不一定要创建 Bitable，但需要定字段。

### 10.1 Memory Records 表

| 字段名 | 类型 | 说明 |
|---|---|---|
| memory_id | 文本 | 本地 memory id |
| scope_type | 单选 | project/user/team/chat |
| scope_id | 文本 | 项目 ID、群 ID、用户 ID |
| type | 单选 | decision/workflow/preference |
| subject | 文本 | 记忆主题 |
| current_value | 多行文本 | 当前有效值 |
| status | 单选 | active/superseded/stale/archived |
| confidence | 数字 | 置信度 |
| importance | 数字 | 重要性 |
| source_type | 单选 | feishu_message/doc/cli/manual |
| source_url | 超链接 | 来源 |
| updated_at | 日期 | 更新时间 |
| version | 数字 | 当前版本 |

### 10.2 Benchmark Results 表

| 字段名 | 类型 | 说明 |
|---|---|---|
| case_id | 文本 | 用例 ID |
| case_type | 单选 | recall/conflict/noise |
| query | 多行文本 | 查询 |
| expected | 多行文本 | 预期 |
| actual | 多行文本 | 实际 |
| passed | 复选框 | 是否通过 |
| latency_ms | 数字 | 延迟 |
| evidence_present | 复选框 | 是否带证据 |

## 11. 明天接飞书前的检查清单

### 11.1 应用与权限

需要准备：

- 飞书自建应用。
- 开启机器人能力。
- 应用可用范围包含测试用户。
- 机器人加入测试群。
- 配置长连接事件订阅。
- 订阅 `im.message.receive_v1`。

最小权限：

```text
im:message.group_at_msg:readonly
im:message.p2p_msg:readonly
im:message:send_as_bot
```

如果要写 Bitable：

```text
base:app:create
base:record:create
base:record:update
base:record:read
base:table:create
base:table:read
```

如果要读文档：

```text
docx:document:readonly
```

### 11.2 环境变量

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
MEMORY_DB_PATH=data/memory.sqlite
```

不要把 `.env` 提交到仓库。

## 12. 验收标准

Day 1 可以结束的标准：

1. 文档存在：
   - `docs/feishu-memory-engine-research-and-plan.md`
   - `docs/day1-execution-plan.md`
2. Git 远程已配置到比赛仓库。
3. `.omx`、`.env`、数据库文件不会被提交。
4. Day 1 任务边界清楚。
5. Day 2 飞书接入需要的权限和 API 已列明。

如果开始写代码，则额外要求：

1. `remember` 能插入 active 记忆。
2. `recall` 能查回 active 记忆。
3. 新规则能 supersede 旧规则。
4. 所有 recall 结果带 evidence。
5. benchmark 至少能跑 2 个 case。

## 13. 当前决策记录

| 决策 | 结论 | 理由 |
|---|---|---|
| 主场景 | 项目决策记忆 + 矛盾更新 | 最贴合课题“证明记住了” |
| 存储 | SQLite + Bitable 双层 | 性能与飞书展示兼顾 |
| Day 1 抽取 | 规则优先 | 快速闭环，减少 LLM 不确定性 |
| 飞书接入 | 长连接优先 | 本地开发无需公网 |
| H5 | P1 | Day 1/2 不阻塞核心闭环 |
| OpenClaw | 作为能力入口，不重写插件 | 官方插件和 CLI 已覆盖大量飞书能力 |

## 14. 明确风险

| 风险 | Day 1 应对 |
|---|---|
| 方案过大 | P0 只做 remember/recall/conflict/benchmark |
| 飞书权限阻塞 | Day 1 本地闭环，Day 2 再接 Bot |
| 抽取不准 | 先规则和人工指令，不全自动 |
| 旧记忆污染 | 默认只召回 active |
| 外部分工时间少 | 外部分工只做测试集、文案、QA，不接阻塞模块 |
| 远程同步混乱 | 当前目录独立 Git 仓库，只提交比赛文件 |

## 15. Day 1 最终输出物

今天必须能给出的输出物：

- 本文档。
- 调研总文档。
- 后续代码目录骨架或明确接口契约。
- 初版 benchmark case 格式。
- Git 提交并推送到远程仓库。

