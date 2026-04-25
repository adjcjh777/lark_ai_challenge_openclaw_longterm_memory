# Day 6 Handoff

日期：2026-04-25

目标日期：2026-04-29

说明：这是提前执行 D6。4 月 29 日主题直播尚未开始，因此直播相关范围校准只记录为待复核项；本轮不臆造直播结论。

## 今日目标

D6 目标是完成主题直播后范围校准与卡片化表达。由于直播未开始，本轮跳过直播内容，优先完成 P0，并继续做 P1 加码。

P0：

- 更新 `docs/day6-scope-adjustment.md`，明确初赛进入范围和复赛延后范围。
- 将 Bot 回复升级为真实飞书 interactive card；结构化文本仅作为 fallback。
- 卡片字段包含结论、理由、状态、版本、来源、是否被覆盖。
- interactive card 单次发送延时控制在 2 秒内，最多尝试 3 次，三次明确失败后才文本 fallback。
- 严格避免成功 card + 文本 fallback 双发。
- 检查安全措辞，避免展示敏感 token、secret、完整内部链接。
- 参考 Hermes Feishu gateway，补 `docs/day6-hermes-feishu-gateway-notes.md`。
- 在现有 handler 中做增强：命令白名单、重复消息提示、interactive card 三次明确失败后文本 fallback。

P1：

- 低置信候选记忆增加人工确认提示。
- 矛盾更新生成“旧规则 -> 新规则”卡片。
- 增加真实飞书卡片发送、按钮回调和 JSON 源码样例。
- 调研命令入口，确认初赛仍使用 `/help` 作为 slash command palette 替代。
- 增加 memory 内容安全扫描设计说明。

## 已完成代码能力

- 扩展 `memory_engine/feishu_messages.py`：
  - 新增 `SUPPORTED_COMMANDS` 命令白名单。
  - 记忆确认、召回、矛盾更新、待确认记忆统一输出卡片字段。
  - 召回回复输出 `卡片：历史决策卡片`。
  - 矛盾更新回复输出 `卡片：矛盾更新卡片` 和 `旧规则 -> 新规则`。
  - `/versions` 回复输出 `卡片：版本链卡片`，逐版本展示是否被覆盖。
  - ingestion 候选展示 confidence，低于 `0.70` 时提示人工确认，并给出 `/confirm <candidate_id>` / `/reject <candidate_id>` 建议动作。
  - `/confirm` / `/reject` 回复输出 `卡片：候选确认卡片`。
  - 对 secret/token/内部 URL 做回复层遮挡；文档 token、本地路径和消息 ID 在展示层只保留截断形态。
- 扩展 `memory_engine/repository.py`：
  - supersede 结果返回旧规则内容、旧版本号和旧版本状态，供矛盾更新卡片展示。
- 新增 `memory_engine/feishu_cards.py`：
  - `build_decision_card(...)`
  - `build_update_card(...)`
  - `build_card_from_text(...)`
  - 从结构化文本生成真实 interactive message JSON card payload。
  - 为候选确认、拒绝和查看版本链附加按钮；候选按钮携带候选序号，结果卡片会回显 `候选序号：候选 N`。
- 扩展 `memory_engine/feishu_publisher.py`：
  - 默认先发送 interactive card。
  - 单次尝试超时 `FEISHU_CARD_TIMEOUT_SECONDS=2` 秒。
  - 最多 `FEISHU_CARD_RETRY_COUNT=3` 次。
  - 三次明确失败后才发送文本 fallback。
  - timeout 属于发送结果未知，会抑制文本 fallback，避免成功 card 后又出现 fallback。
  - card 与 fallback 复用同一 idempotency key，降低重复消息风险。
  - 超长 card action token 会 hash 成短 idempotency key，避免飞书字段校验失败。
- 扩展 `memory_engine/feishu_events.py` / `memory_engine/feishu_runtime.py`：
  - 订阅 `card.action.trigger`。
  - 将按钮值转成 `/confirm`、`/reject`、`/versions` 命令。
- 扩展 `scripts/start_feishu_bot.sh`：
  - 默认 `FEISHU_CARD_MODE=interactive`。
  - 打印 card retry/timeout 配置，方便测试时确认。
- 新增 `tests/test_feishu_day6.py`：
  - 验证历史决策卡片字段完整。
  - 验证 secret/token 回复遮挡。
  - 验证矛盾更新卡片展示旧规则到新规则。
  - 验证未知命令展示白名单。
  - 验证 JSON card builder 包含核心字段。
- 新增 `tests/test_feishu_interactive_cards.py`：
  - 验证 card 成功后不发送文本 fallback。
  - 验证 3 次 card 失败后才发送文本 fallback。
  - 验证 timeout 时抑制文本 fallback，避免未知发送结果造成双发。
  - 验证 card action 能路由到已有 confirm 命令。

## 已完成文档

- `docs/day6-scope-adjustment.md`
  - 明确初赛范围：白皮书、可运行 Demo、Benchmark、真实 interactive card、安全表达。
  - 明确复赛延后：H5、加号菜单、消息快捷操作、流式卡片、完整安全扫描拦截链路。
  - 记录命令入口调研结论。
  - 记录 memory 内容安全扫描设计。
  - 附历史决策卡片和矛盾更新卡片文本样例。
  - 附飞书卡片 JSON 源码样例。
- `docs/day6-hermes-feishu-gateway-notes.md`
  - 提炼 @mention gating、消息去重、allowlist、每 chat 串行处理、卡片事件 fallback、回复失败 fallback、自发消息过滤、内容安全扫描。
  - 明确 D6 吸收项和拒绝项。
  - 说明后续落地顺序。

## Demo 推荐输入

群聊：

```text
@Feishu Memory Engine bot /remember 生产部署必须加 --canary --region cn-shanghai
@Feishu Memory Engine bot /recall 生产部署参数
@Feishu Memory Engine bot /remember 不对，生产部署 region 改成 ap-shanghai
@Feishu Memory Engine bot /recall 生产部署 region
@Feishu Memory Engine bot /unknown 生产部署
```

单聊机器人时可以省略 `@Feishu Memory Engine bot`。

预期亮点：

- `/recall` 返回历史决策卡片字段。
- 第二次 `/remember` 返回矛盾更新卡片，显示旧规则到新规则。
- `/versions <memory_id>` 返回版本链卡片，展示 active/superseded 和是否被覆盖。
- `/ingest_doc` 返回人工确认队列，候选行直接给出确认/拒绝命令。
- `/unknown` 返回命令白名单。
- 如果输入包含 `API_TOKEN=...`，回复中会显示为 `[REDACTED]`。

## 真实飞书测试群检查清单

前置：

```bash
export LARK_CLI_PROFILE=feishu-ai-challenge
export MEMORY_DB_PATH=data/memory.sqlite
export MEMORY_DEFAULT_SCOPE=project:feishu_ai_challenge
export FEISHU_BOT_MODE=reply
export FEISHU_CARD_MODE=interactive
export FEISHU_CARD_RETRY_COUNT=3
export FEISHU_CARD_TIMEOUT_SECONDS=2
export FEISHU_LOG_DIR=logs/feishu-bot
./scripts/start_feishu_bot.sh
```

监听进程会为每次启动创建一个 `logs/feishu-bot/feishu-listen-<timestamp>.ndjson` 文件。日志记录包含 `listen_start`、`event_received`、`event_result`、`event_error`、`listen_stop` 和 `listen_exit`，每条都有 `ts` 时间戳，便于复盘真实飞书测试群里的卡片点击和 fallback 行为。

群聊测试输入：

```text
@Feishu Memory Engine bot /health
@Feishu Memory Engine bot /remember Day6 生产部署必须加 --canary --region cn-shanghai，API_TOKEN=demo_token_placeholder
@Feishu Memory Engine bot /recall Day6 生产部署参数
@Feishu Memory Engine bot /remember 不对，Day6 生产部署 region 改成 ap-shanghai
@Feishu Memory Engine bot /recall Day6 生产部署 region
@Feishu Memory Engine bot /versions <上一步回复里的 memory_id>
@Feishu Memory Engine bot /ingest_doc tests/fixtures/day5_doc_ingestion_fixture.md
@Feishu Memory Engine bot /confirm <候选回复里的 candidate_id>
@Feishu Memory Engine bot /unknown 生产部署
```

截图验收点：

- `/recall`：出现 `卡片：历史决策卡片`，字段包含结论、理由、状态、版本、来源、是否被覆盖。
- 矛盾更新：出现 `卡片：矛盾更新卡片` 和 `旧规则 -> 新规则`。
- `/versions`：出现 `卡片：版本链卡片`，旧版本显示 `是否被覆盖：是`。
- `/ingest_doc`：出现 `卡片：人工确认队列`，候选行包含 `/confirm` 和 `/reject`。
- 安全遮挡：`API_TOKEN=...` 在回复中显示为 `API_TOKEN=[REDACTED]`，不出现完整 token。
- 未知命令：出现 `命令白名单`。

## 命令入口结论

初赛继续采用：

- `/help` 展示可用命令和 Demo 推荐输入。
- 真实 interactive card 作为截图主承载。
- 结构化文本 fallback 作为严格兜底路径。
- 卡片按钮覆盖候选确认、拒绝、查看版本链。

暂不做：

- 实时 slash 候选 UI。
- H5 命令面板。
- 聊天框加号菜单或消息快捷操作。

原因：当前 Bot handler 能处理已发送消息和 card action，但不能控制用户输入中的候选面板；H5/加号菜单等产品入口需要开放平台后台配置和审核确认。

## 真实按钮点击问题

2026-04-25 真实飞书客户端点击 `拒绝` 按钮时出现：

```text
出错了，请稍后重试 code: 200340
```

判断：

- 真实 Bot listener 当时正在运行，并订阅 `im.message.receive_v1,card.action.trigger`。
- 点击后测试群没有出现新的 Bot 结果卡片，说明真实点击事件没有进入当前 handler，或飞书没有拿到有效 card action 回调 ACK。
- 该问题不是 `/reject` 业务命令本身失败；本地 synthetic `card.action.trigger` 已验证能路由到 `/confirm`、`/versions`，`/reject` 同一解析路径。

需要在飞书开发者后台复核：

1. 事件订阅是否包含 `card.action.trigger`，并且已发布/生效。
2. 机器人能力中是否启用了消息卡片/交互式卡片能力。
3. 如果当前应用使用 Webhook 模式，消息卡片请求地址必须配置到同一个事件回调地址；如果使用 WebSocket 模式，确认 lark-cli/openclaw 当前连接具备接收 card action 的能力。

临时 Demo 策略：

- 按钮旁继续保留 `/confirm <candidate_id>` / `/reject <candidate_id>` 文本命令作为 fallback。
- 卡片按钮只展示真正 `candidate` 行，最多前三个候选，并使用 `确认候选 1`、`拒绝候选 1` 这类可定位文案，结果卡片回显 `候选序号：候选 1`，避免评委误点 active 行或看不出操作对象。
- 在后台配置修好前，不把“人工点击按钮成功”作为唯一 Demo 路径；使用手动 `/reject <candidate_id>` 证明业务闭环。

## 验证结果

已通过：

```bash
python3 -m compileall memory_engine scripts
python3 -m unittest discover -s tests
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine benchmark ingest-doc benchmarks/day5_ingestion_cases.json
```

全量单测：

- `28 tests OK`

Day6 专项：

- `python3 -m unittest discover -s tests -p 'test_feishu_day6.py'`：`7 tests OK`
- `python3 -m unittest discover -s tests -p 'test_feishu_interactive_cards.py'`：`6 tests OK`

真实飞书测试群：

- 已启动 `./scripts/start_feishu_bot.sh`，使用 `reply` 模式监听测试群 @Bot 消息。
- 已在测试群发送并收到 Bot 回复：
  - `/remember ...`：真实 interactive card 首次发送成功，耗时约 718ms，`fallback_used=false`。
  - `/recall ...`：真实 interactive card 首次发送成功，耗时约 1289ms，`fallback_used=false`。
  - card action `versions`：回调路由到 `/versions`，真实 `send_card` 首次发送成功，耗时约 695ms，`fallback_used=false`。
  - card action `confirm`：回调路由到 `/confirm`，候选记忆状态变为 `active`，真实 `send_card` 首次发送成功，耗时约 787ms，`fallback_used=false`。
- 2026-04-25 17:33-17:34 用户在真实飞书测试群补充截图验证：
  - `/ingest_doc tests/fixtures/day5_doc_ingestion_fixture.md` 返回真实 interactive card，候选列表只展示 candidate 行，并以 `候选 1` / `候选 2` / `候选 3` 标识。
  - 点击 `拒绝候选 1` 后返回“候选记忆拒绝卡片”，卡片回显 `候选序号：候选 1`、`处理结果：rejected`、对应 `memory_id` 和“查看版本链”按钮。
  - 点击“查看版本链”后返回版本链 interactive card，展示同一记忆的 `v1 [rejected]` 状态。
  - 对应本地监听日志 `logs/feishu-bot/feishu-listen-20260425_173255.ndjson` 摘要：`event_received=3`、`event_result=3`、`event_error=0`；3 次卡片发送均成功，耗时约 803-1003ms，`fallback_used=false`；动作包含 `reject` 与 `versions`。
- 2026-04-25 17:45 重新执行 `/recall Day6 生产部署参数`，真实飞书测试群返回历史决策 interactive card；监听日志显示 `command=recall`、`mode=reply_card`、`latency_ms≈745`、`fallback_used=false`。

![Day6 `/recall` 真实飞书 interactive card 截图](assets/day6/day6-recall-card-20260425-1745.png)

- 真实测试中修复了两个问题：
  - `card_attempts` 循环引用导致监听进程 JSON 序列化失败。
  - card action synthetic message_id 过长导致 idempotency key 超限，飞书返回字段校验失败。
- 真实 `chat_id`、Bot mention `open_id`、消息 ID 不写入仓库；本节只记录验证结论。

Day 1 benchmark：

- `case_count = 10`
- `case_pass_rate = 1.0`
- `conflict_accuracy = 1.0`
- `evidence_coverage = 1.0`
- `stale_leakage_rate = 0.0`
- `avg_latency_ms = 0.798`

Day 5 ingestion benchmark：

- `case_count = 2`
- `case_pass_rate = 1.0`
- `avg_candidate_count = 5.0`
- `avg_quote_coverage = 1.0`
- `avg_noise_rejection_rate = 1.0`
- `document_evidence_coverage = 1.0`
- `avg_ingestion_latency_ms = 15.941`

## 队友今晚任务

1. 从评委视角检查卡片字段：是否一眼看出“这是企业记忆，不是聊天摘要”。
2. 基于已跑通的飞书测试群消息补齐 `/recall`、矛盾更新、版本链、人工确认队列四张图；`拒绝候选 1` 与版本链截图已完成。
3. 检查 `docs/day6-scope-adjustment.md` 的初赛/复赛边界是否过宽。
4. 如果直播后有新要求，在本 handoff 后追加“直播后复核”小节。

## 未验证项

- 4 月 29 日主题直播尚未发生，直播要求和评分偏好未复核。
- 真实飞书 interactive card 已启用为默认路径；文本 fallback 仅在三次 card 明确失败后使用，timeout 时抑制 fallback。
- 内容安全扫描还未做写入前强拦截；当前只做回复层遮挡和后续设计说明。
- 真实飞书测试群已验证 interactive card 发送和 `versions` / `confirm` / `reject` 按钮回调路径；`reject` 和 `versions` 已有飞书客户端截图，后续还建议补 `confirm` 截图。
