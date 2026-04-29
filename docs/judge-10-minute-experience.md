# 10 分钟评委体验包

日期：2026-04-29
主线：OpenClaw-native Feishu Memory Copilot
适用场景：评委现场走查、答辩录屏、队友复盘

## 先看这个

1. 这条路线只用固定演示数据、脱敏截图清单和本地可复现证据。
2. 评委不需要理解 `candidate_id`、`trace_id` 或 `memory_id`，这些字段只放在审计详情或工程 fallback。
3. 当前可说 demo / sandbox / pre-production / 本机 staging；不能说 production live、全量 Feishu workspace 接入或真实 Feishu DM 到本项目 `fmc_*` / `memory.*` live E2E 已完成。
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
| 1:00-2:00 | `上次定的生产部署 region 是哪个？` | 展示 `memory.search` replay 或飞书 sandbox 搜索卡 | 返回 active 结论：`ap-shanghai` + `--canary`，带 evidence quote 和用户可读原因 | OpenClaw / 飞书不稳时展示 `reports/demo_replay.json` step 1 | “这里不是把聊天记录全丢给评委，而是给当前有效结论。” |
| 2:00-3:00 | `记住：生产部署必须加 --canary，region 用 ap-shanghai。` | 展示 candidate 创建回复 | 系统说明已生成待确认记忆，不会自动 active | 真实入口不稳时展示 `agent_adapters/openclaw/examples/conflict_update_flow.json` | “真实飞书来源先进入 candidate，避免一句话直接污染企业记忆。” |
| 3:00-4:00 | `确认这条` | 展示最近 candidate 的确认路径 | 用户不复制内部 ID 也能完成确认；内部仍走 `memory.confirm` / `CopilotService` | 无法定位最近 candidate 时说明 `/confirm <candidate_id>` 只是工程 fallback | “评委看到的是自然动作；审计字段仍保留给排障。” |
| 4:00-5:00 | `为什么之前的 cn-shanghai 不用了？` | 展示 `memory.explain_versions` 或版本解释卡 | 当前版本、旧版本、覆盖原因和证据可读 | 无法定位主题时先展示 search，再展示 replay step 2 | “旧值不会被删除，但默认搜索不会把旧值当当前答案。” |
| 5:00-6:00 | `帮我准备今天上线前 checklist。` | 展示 `memory.prefetch` context pack | 返回 compact context pack、相关 active 记忆、风险和缺失信息 | 上下文不足时展示缺失项，不编造规则 | “Agent 开始任务前拿的是短上下文包，不是全部 raw events。” |
| 6:00-7:00 | 无 | 展示 heartbeat reminder candidate | 只生成 reminder candidate，可确认、忽略、延后或关闭同类提醒 | 若 reminder replay 不可用，展示 `docs/benchmark-report.md` heartbeat 指标 | “主动提醒是受控候选，不是真实群推送，也不会自动 active。” |
| 7:00-8:00 | 无 | 打开 `docs/benchmark-report.md` 的 PRD 指标映射和 UX-06 样本 | 评委看到 Recall@3、误记率、误提醒率、确认负担、解释覆盖率、旧值泄漏率 | 不现场重跑重 benchmark，只展示已有 runner 命令 | “UX-06 指标有通过项，也保留旧值泄漏等残余风险。” |
| 8:00-9:00 | 无 | 打开三张架构入口图 | 系统架构、产品交互流、benchmark loop 都能定位 | Mermaid 渲染失败时直接展示 `.mmd` 源码 | “OpenClaw Agent 调 memory tools，Copilot Core 统一做权限、治理、检索和审计。” |
| 9:00-10:00 | 无 | 回到不能 overclaim 边界和下一步 | 评委知道当前是 demo / sandbox / pre-production，不是 production live | 如果现场追问 live DM，明确还缺真实 Feishu DM 到本项目工具链路的 live E2E 证据 | “当前价值已经可复现，但生产部署、全量接入和长期运行仍是后续项。” |

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
