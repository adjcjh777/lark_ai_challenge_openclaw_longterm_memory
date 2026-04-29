# 10 分钟评委体验包

日期：2026-04-29
主线：OpenClaw-native Feishu Memory Copilot
适用场景：评委现场走查、答辩录屏、队友复盘

## 先看这个

1. 这条路线优先使用固定演示数据、脱敏截图清单和本地可复现证据；如果现场已有单监听 OpenClaw websocket 和受控私聊权限，可以追加一次真实 DM allow-path 读回。
2. 评委不需要理解 `candidate_id`、`trace_id` 或 `memory_id`，这些字段只放在审计详情或工程 fallback。
3. 当前可说 demo / sandbox / pre-production / 本机 staging，以及一次受控真实 Feishu DM -> `fmc_memory_search` -> `CopilotService` allow-path live E2E 已完成；不能说 production live、全量 Feishu workspace 接入或真实 Feishu DM 已稳定长期路由到本项目 `fmc_*` / `memory.*`。
4. 真实飞书来源仍是 candidate-only，不能自动 active；确认、拒绝、版本解释和 prefetch 都必须进入 `handle_tool_request()` / `CopilotService`。

## 固定演示数据

演示主题固定为“生产部署规则”：

| 字段 | 固定值 |
|---|---|
| 当前 active 结论 | 生产部署 region 使用 `ap-shanghai`，并加 `--canary` |
| 被覆盖旧值 | `cn-shanghai` |
| 任务场景 | 今天上线前 checklist |
| 用户表达 | 普通话自然输入，不要求复制内部 ID |
| 数据来源 | `scripts/demo_seed.py` 生成的本地 replay 和 `agent_adapters/openclaw/examples/*.json` |
| 本地证据 | `reports/demo_replay.json`，该目录不提交 |

准备命令：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/demo_seed.py --json-output reports/demo_replay.json
```

预期看到：

- `OpenClaw version OK: 2026.4.24`
- `production_feishu_write=false`
- `openclaw_example_contract_ok=true`
- replay steps 均为 `ok=true`

## 入口和准备检查

评委现场按两层入口执行。普通评委和普通用户先走 A 路线；只有在本机 OpenClaw websocket 已经接管 bot、且操作者确认不会启动第二个 Feishu listener 时，才追加 B 路线。

| 路线 | 入口 | 适用人群 | 目的 | 不做什么 |
|---|---|---|---|---|
| A. 10 分钟产品主路径 | 本文 `10 分钟脚本` + `reports/demo_replay.json` | 评委、普通用户、队友复盘 | 让用户看懂搜索、候选、确认、版本解释、prefetch、提醒和 benchmark | 不要求真实飞书写入，不要求理解内部 ID |
| B. 受控真实 DM allow-path | 飞书私聊 `Feishu Memory Engine bot`，发送下方固定 DM | 现场演示负责人或工程验收者 | 读回一次真实 DM -> OpenClaw -> `fmc_memory_search` -> `CopilotService` 的 allow-path 证据 | 不验证长期稳定性，不验证所有 `fmc_*` 工具动作，不写真实 ID |

执行 B 路线前只做读状态检查，不启动第二个 listener：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
openclaw channels status --probe --json
```

必须满足：

- OpenClaw version 为 `2026.4.24`。
- 单监听检查通过；同一 bot 没有 repo 内 `copilot-feishu listen`、legacy listener 或 direct `lark-cli event +subscribe` 冲突。
- `openclaw channels status --probe --json` 能证明 Feishu channel/account running；如果 `openclaw health --json` 总览字段不一致，只作为已知 warning，不把它写成失败或成功。

## 受控真实 DM 文案

发送给受控测试 bot 的 DM 使用固定脱敏请求，不写真实 `chat_id`、`open_id`、message id 或 token：

```text
请直接调用 fmc_memory_search 搜索 "Copilot live sandbox 验收口径"，
scope=project:feishu_ai_challenge，top_k=5。
current_context.permission 使用 demo tenant/org、reviewer actor、
request_id=req_feishu_dm_live_20260429_1104、
trace_id=trace_feishu_dm_live_20260429_1104。
```

预期看到：

- 飞书机器人回复包含“通过，命中 5 条”或同等 allow-path 成功摘要。
- 回复或审计详情包含 `request_id=req_feishu_dm_live_20260429_1104`。
- 回复或审计详情包含 `trace_id=trace_feishu_dm_live_20260429_1104`。
- 回复或审计详情包含 `permission_decision=allow/scope_access_granted`。
- 工具链路是 `fmc_memory_search` -> Python runner -> `handle_tool_request()` -> `CopilotService`。

如果失败，不改配置、不启动备用 listener，先按这三个字段定位：

| 现象 | 先看字段 | 判断 | fallback |
|---|---|---|---|
| bot 无回复或超时 | `request_id` 是否出现在 gateway / session 日志 | 没出现表示 DM 未进入当前 OpenClaw session；出现但无 final 可能是 LLM timeout 或 dispatch 卡住 | 回到 A 路线展示 replay，并记录 OpenClaw websocket / LLM timeout 风险 |
| 回复没有命中结果 | `trace_id` 和 `permission_decision` | `deny` / `missing_permission_context` / `scope_mismatch` 说明权限 fail closed 正常生效 | 展示 permission denied fallback，不补宽松权限 |
| 回复缺少审计字段 | `request_id`、`trace_id`、`permission_decision` | 说明用户主答案可读，但工程排障字段不足 | 展示 `reports/demo_replay.json` 或 handoff 里的 allow-path 读回 |

本路线只能证明一次受控 allow-path；不能对外说“真实 Feishu DM 已稳定自动调用所有工具”。

## 截图清单

不需要生成或提交截图二进制。现场截图只截脱敏材料，不截真实群 ID、用户 ID、token、app secret、`.env` 或真实私聊内容。

| 截图 | 内容 | 文件或入口 | 敏感边界 |
|---|---|---|---|
| 1 | README 顶部当前状态和不能 overclaim 边界 | `README.md` | 不截 `.env` 或本地账号信息 |
| 2 | 10 分钟脚本总览 | 本文档 | 不包含真实飞书 ID |
| 3 | Demo replay compact summary | `python3 scripts/demo_seed.py --json-output reports/demo_replay.json` 输出 | `reports/` 不提交 |
| 4 | 搜索结果 active 结论 | `reports/demo_replay.json` step 1 | 只截固定样例 `ap-shanghai` / `--canary` |
| 5 | 候选确认或版本解释 | `reports/demo_replay.json` step 2 | 不展示真实 reviewer open_id |
| 6 | prefetch context pack | `reports/demo_replay.json` step 3 | 不展示 raw events 全文 |
| 7 | heartbeat reminder candidate | `reports/demo_replay.json` step 4 | 确认敏感字段已脱敏 |
| 8 | Benchmark 指标表 | `docs/benchmark-report.md` | 明确 UX-06 残余风险 |
| 9 | 系统架构图 | `docs/diagrams/system-architecture.mmd` | 作为架构示意，不代表 production live |
| 10 | 产品交互流或 benchmark loop | `docs/diagrams/product-interaction-flow.mmd` / `docs/diagrams/benchmark-loop.mmd` | 不包含真实数据 |

## 10 分钟脚本

| 时间 | 输入 | 动作 | 预期输出 | 失败 fallback | 讲解词 |
|---|---|---|---|---|---|
| 0:00-1:00 | 无 | 打开 README 顶部和本文档 | 评委知道项目是 OpenClaw-native 企业记忆 Copilot | README 打不开时用 `docs/human-product-guide.md` 的“一句话产品定义” | “飞书里不是缺搜索，而是缺当前有效、带证据、可审计的团队记忆。” |
| 1:00-2:00 | `上次定的生产部署 region 是哪个？` | 展示 `memory.search` replay、飞书 sandbox 搜索卡，或受控 DM allow-path 读回 | 返回 active 结论：`ap-shanghai` + `--canary`，带 evidence quote 和用户可读原因；受控 DM 读回还应包含 `request_id`、`trace_id`、`permission_decision` | OpenClaw / 飞书不稳时展示 `reports/demo_replay.json` step 1；真实 DM 失败时按上面的三个字段定位 | “这里不是把聊天记录全丢给评委，而是给当前有效结论；工程字段只用于审计和排障。” |
| 2:00-3:00 | `记住：生产部署必须加 --canary，region 用 ap-shanghai。` | 展示 candidate 创建回复 | 系统说明已生成待确认记忆，不会自动 active | 真实入口不稳时展示 `agent_adapters/openclaw/examples/conflict_update_flow.json` | “真实飞书来源先进入 candidate，避免一句话直接污染企业记忆。” |
| 3:00-4:00 | `确认这条` | 展示最近 candidate 的确认路径 | 用户不复制内部 ID 也能完成确认；内部仍走 `memory.confirm` / `CopilotService` | 无法定位最近 candidate 时说明 `/confirm <candidate_id>` 只是工程 fallback | “评委看到的是自然动作；审计字段仍保留给排障。” |
| 4:00-5:00 | `为什么之前的 cn-shanghai 不用了？` | 展示 `memory.explain_versions` 或版本解释卡 | 当前版本、旧版本、覆盖原因和证据可读 | 无法定位主题时先展示 search，再展示 replay step 2 | “旧值不会被删除，但默认搜索不会把旧值当当前答案。” |
| 5:00-6:00 | `帮我准备今天上线前 checklist。` | 展示 `memory.prefetch` context pack | 返回 compact context pack、相关 active 记忆、风险和缺失信息 | 上下文不足时展示缺失项，不编造规则 | “Agent 开始任务前拿的是短上下文包，不是全部 raw events。” |
| 6:00-7:00 | 无 | 展示 heartbeat reminder candidate | 只生成 reminder candidate，可确认、忽略、延后或关闭同类提醒 | 若 reminder replay 不可用，展示 `docs/benchmark-report.md` heartbeat 指标 | “主动提醒是受控候选，不是真实群推送，也不会自动 active。” |
| 7:00-8:00 | 无 | 打开 `docs/benchmark-report.md` 的 PRD 指标映射和 UX-06 样本 | 评委看到 Recall@3、误记率、误提醒率、确认负担、解释覆盖率、旧值泄漏率 | 不现场重跑重 benchmark，只展示已有 runner 命令 | “UX-06 指标有通过项，也保留旧值泄漏等残余风险。” |
| 8:00-9:00 | 无 | 打开三张架构入口图 | 系统架构、产品交互流、benchmark loop 都能定位 | Mermaid 渲染失败时直接展示 `.mmd` 源码 | “OpenClaw Agent 调 memory tools，Copilot Core 统一做权限、治理、检索和审计。” |
| 9:00-10:00 | 无 | 回到不能 overclaim 边界和下一步 | 评委知道当前是 demo / sandbox / pre-production，另有一次受控真实 DM allow-path 证据，但不是 production live | 如果现场追问 live DM，明确只完成一次 `fmc_memory_search` allow-path；还缺更多工具动作和长期稳定性验收 | “当前价值已经可复现，也补了一次真实 DM 读回证据；生产部署、全量接入和长期运行仍是后续项。” |

## Benchmark 和安全边界讲法

评委版只讲三类指标：

| 指标组 | 讲什么 | 当前口径 |
|---|---|---|
| 召回与证据 | Recall@3、Evidence Coverage、Stale Leakage Rate | recall runner 可复现；2026-04-29 扩样后 Recall@3 = 0.9250，但 stale leakage 仍是残余风险 |
| UX-06 真实表达样本 | Real Expression Recall@3、误记率、误提醒率、确认负担、解释覆盖率、旧值泄漏率 | 脱敏样本 25 条，当前 baseline pass rate = 0.7600；不是生产真实用户稳定可用结论 |
| 安全与提醒 | Unauthorized Value Leakage Rate、Sensitive Reminder Leakage Rate、False / Duplicate Reminder Rate | 权限拒绝和提醒脱敏已有测试 / benchmark 入口；reminder 仍只生成 candidate，不真实群推送 |

不要说：

- “生产已经上线。”
- “真实 Feishu DM 已稳定自动调用本项目 `fmc_*` / `memory.*` 工具。”
- “已全量接入企业飞书 workspace。”
- “长期 embedding 服务已完成。”
- “benchmark 全部达标。”
- “真实飞书来源会自动变成 active memory。”
- “一次受控 `fmc_memory_search` 成功等于所有工具动作和长期路由都稳定。”

## 架构图入口

| 图 | 入口 | 现场用途 |
|---|---|---|
| 系统架构 | [diagrams/system-architecture.mmd](diagrams/system-architecture.mmd) | 解释 OpenClaw Agent -> memory tools -> Copilot Core -> governance / retrieval / audit |
| 产品交互流 | [diagrams/product-interaction-flow.mmd](diagrams/product-interaction-flow.mmd) | 解释用户从搜索、候选确认、版本解释到任务前 prefetch 的路径 |
| Benchmark loop | [diagrams/benchmark-loop.mmd](diagrams/benchmark-loop.mmd) | 解释样本、runner、指标、失败分类和修复闭环 |

## 计时验收记录

| 日期 | 方式 | 结果 | 失败点 | 替代路线 |
|---|---|---|---|---|
| 2026-04-29 | 本地文档计时走查：按本文档从问题定义、replay、benchmark 到架构边界完整走一遍 | 9 分 40 秒内可完成，不含现场问答 | Mermaid 渲染或飞书 sandbox 不稳定会拖慢现场节奏 | 直接展示 `.mmd` 源码、`reports/demo_replay.json` 和 `docs/benchmark-report.md`，并明确这些是 replay / sandbox / 本机 staging 证据 |
| 2026-04-29 | 受控真实 DM allow-path 证据整理：把 11:04-11:07 的真实 DM 读回固化为可复测入口 | 已给出固定 DM、准备检查、预期字段和失败 fallback | 只覆盖 `fmc_memory_search` allow-path，不覆盖长期稳定性或所有工具动作 | 现场不可用时回到 replay；不能为了演示启动第二个 listener 或写入真实 ID |

## 验收命令

UX-07 文档封包完成后运行：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_demo_readiness.py --json
python3 scripts/check_copilot_health.py --json
git diff --check
ollama ps
```

本轮只更新文档，不改 runner 或 benchmark 样本；已有 UX-06 runner 命令保留在 [benchmark-report.md](benchmark-report.md)。
