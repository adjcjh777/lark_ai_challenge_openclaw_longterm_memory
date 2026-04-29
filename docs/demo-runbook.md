# 2026-05-04 OpenClaw-native Demo Runbook

目标：用 5 分钟证明 Feishu Memory Copilot 不是普通聊天搜索，而是能在 OpenClaw Agent 任务前主动调取“有证据、有版本、有状态”的企业协作记忆。

> **状态更新（2026-04-28）**：本 runbook 对应的 2026-05-04 Demo 固定任务已经完成，保留为可复现演示证据。后续不要从 2026-05-04 日期计划继续补任务；新的执行入口是 `docs/productization/full-copilot-next-execution-doc.md`。

> **UX-07 更新（2026-04-29）**：评委现场优先走 [10 分钟评委体验包](judge-10-minute-experience.md)。本文继续保留 5 分钟 demo replay 和飞书主路径脚本，作为 UX-07 的固定演示数据来源和失败 fallback。

> **真实 DM 证据更新（2026-04-29）**：已完成一次受控真实 Feishu DM -> OpenClaw websocket -> `fmc_memory_search` -> `CopilotService` allow-path 读回；该证据可作为评委现场可选验收，但仍不能写成生产部署、全量 workspace ingestion 或真实 DM 稳定长期路由。

## 执行前先看这个

1. 今天演示主入口是 OpenClaw tools，不是旧 CLI 或旧 Feishu Bot。
2. Cognee 是本地 knowledge / memory engine；企业记忆治理、candidate（待确认记忆）、active（当前有效记忆）、superseded（被新版本覆盖的旧记忆）、evidence（证据）和版本链由本项目 Copilot Core 负责。
3. 现场优先走 `agent_adapters/openclaw/examples/*.json` 和 `scripts/demo_seed.py` 的 dry-run；OpenClaw gateway 或飞书权限不稳时，不真实写飞书生产空间。
4. Demo 只展示可复现能力：历史决策召回、冲突更新、任务前 prefetch、heartbeat reminder candidate、benchmark 证明。
5. 若现场卡住，把失败命令、卡住步骤和替代路径写回当前产品化 handoff；`docs/plans/2026-05-04-handoff.md` 只作为历史交接证据。

## 演示前准备，60 秒

在仓库根目录运行：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/demo_seed.py --json-output reports/demo_replay.json
```

预期输出：

- `OpenClaw version OK: 2026.4.24`
- `production_feishu_write=false`
- `openclaw_example_contract_ok=true`
- 5 个步骤均为 `ok=true`

截图需求：

- 版本锁输出。
- `scripts/demo_seed.py` 输出的 compact summary。
- `reports/demo_replay.json` 中任意一个完整 tool response。

## UX-07 评委版固定入口

10 分钟评委体验包只引用脱敏、可复现材料：

- 入口文档：[judge-10-minute-experience.md](judge-10-minute-experience.md)。
- 固定数据：生产部署 region 从 `cn-shanghai` 覆盖为 `ap-shanghai`，并要求 `--canary`。
- replay 证据：`scripts/demo_seed.py --json-output reports/demo_replay.json`。
- benchmark 证据：[benchmark-report.md](benchmark-report.md) 中 UX-06 指标和残余风险。
- 架构图入口：[diagrams/system-architecture.mmd](diagrams/system-architecture.mmd)、[diagrams/product-interaction-flow.mmd](diagrams/product-interaction-flow.mmd)、[diagrams/benchmark-loop.mmd](diagrams/benchmark-loop.mmd)。
- 可选真实 DM 入口：按 [judge-10-minute-experience.md](judge-10-minute-experience.md) 的“受控真实 DM 文案”执行，只读回命中数、request_id、trace_id、permission_decision，不截真实 ID。

截图清单不包含真实 `chat_id`、`open_id`、token、app secret、`.env` 或真实私聊内容；不需要提交截图二进制。

计时验收记录：

| 日期 | 方式 | 结果 | 失败点 | 替代路线 |
|---|---|---|---|---|
| 2026-04-29 | 按 10 分钟评委体验包做本地文档计时走查 | 9 分 40 秒内可走完问题定义、搜索、候选确认、版本解释、prefetch、benchmark、架构和边界 | Mermaid 渲染或飞书 sandbox 不稳定会拖慢现场节奏 | 直接展示 `.mmd` 源码、`reports/demo_replay.json` 和 benchmark report；明确这些是 replay / sandbox / 本机 staging 证据，不是 production live |
| 2026-04-29 | 受控真实 DM allow-path 读回 | 真实 DM 进入 OpenClaw 后直接调用 `fmc_memory_search`，飞书机器人读回命中 5 条、request_id、trace_id、permission_decision=allow | 只覆盖单次 search 工具；主模型 timeout 后由 fallback model 完成 | 现场不稳时回到 replay / handoff；不启动第二个 listener |

## 5 分钟流程

## 飞书主路径普通话脚本

这组脚本用于 UX-01 验收：评委或真实用户不需要输入 `candidate_id`、`memory_id`、`trace_id`，也能走完搜索、候选确认、版本解释和任务前 prefetch。当前边界仍是 Feishu live sandbox / demo path，并补了一次受控真实 DM `fmc_memory_search` allow-path 读回；不要把它说成 production live，也不要说真实 Feishu DM 已稳定路由到本项目 first-class `fmc_*` / `memory.*` 工具链路。

| 路径 | 普通话输入 | 预期输出 | 失败 fallback | no-overclaim 边界 |
|---|---|---|---|---|
| 搜索当前结论 | `上次定的生产部署 region 是哪个？` | 主答案先给当前 active 结论、1 条 evidence quote 和下一步动作；`request_id`、`trace_id`、`permission_decision` 只在审计详情。 | 如果没有 active 记忆，提示“没有找到当前有效结论”，引导用户补充主题或先创建候选。 | 默认搜索不返回 superseded 旧值，也不返回 raw events。 |
| 创建并确认候选 | `记住：生产部署必须加 --canary，region 用 ap-shanghai。` -> `确认这条` | 第一条回复说明“已生成待确认记忆，不会自动 active”；第二条回复确认最近 candidate，不要求用户复制内部 ID。 | 如果无法解析最近 candidate，保留 `/confirm <candidate_id>` fallback，并说明没有绕过 `CopilotService`。 | 真实飞书来源只能 candidate-only，确认必须由 reviewer / owner / admin 触发。 |
| 版本解释 | `为什么之前的 cn-shanghai 不用了？` | 调用 `memory.explain_versions`，解释当前版本、旧版本、覆盖原因和证据。 | 如果无法解析最近 memory，保留 `/versions <memory_id>` fallback，并提示先搜索具体主题。 | 默认 search 不把旧值当当前答案；旧值只在版本解释里出现。 |
| 任务前 prefetch | `帮我准备今天上线前 checklist。` | 调用 `memory.prefetch`，返回 compact context pack、相关 active 记忆、缺失信息和风险。 | 如果上下文不足，返回空 pack 或缺失信息，不编造规则。 | prefetch 不返回全部 raw events，不代表长期 embedding 服务或生产工作流已完成。 |

## UX-02 记忆卡片信息架构

评委版卡片只展示稳定可用动作，不暴露半成品按钮。四类卡片都消费 `handle_tool_request()` / `CopilotService` 的输出；权限拒绝时只展示拒绝原因和审计 ID，不展示未授权结论或证据。

| 卡片 | 输入 | 预期输出 | 可见按钮 | fallback | no-overclaim 边界 |
|---|---|---|---|---|---|
| 搜索结果卡 | `memory.search` 输出 | 当前 active 结论、evidence quote、版本状态、旧值已过滤、用户可读排序理由；审计详情放底部。 | `解释版本`，进入现有 versions / `memory.explain_versions` 路径。 | 没找到时显示空状态，引导补主题或创建候选。 | 不展示 superseded 旧值或 raw events；受控真实 DM 证据只覆盖一次 `fmc_memory_search` allow-path，不代表稳定长期路由。 |
| 候选审核卡 | `memory.create_candidate` 输出 | 待确认新记忆、来源、证据、风险等级、冲突摘要、建议动作。 | reviewer / owner / admin 可见 `确认保存`、`拒绝候选`；非 reviewer 隐藏。 | 权限不足或 permission 畸形时 fail closed，只显示安全拒绝摘要。 | 真实飞书来源仍 candidate-only；按钮不绕过 `CopilotService`。 |
| 版本解释卡 | `memory.explain_versions` 输出 | 当前版本、被覆盖旧版本、覆盖原因、时间线摘要。 | 无新增半成品按钮。 | 无法定位 memory 时先搜索主题，或用 `/versions <memory_id>`。 | 旧值只用于解释，不作为默认 search 当前答案。 |
| 任务前上下文卡 | `memory.prefetch` 输出 | 本次任务、要带入的 active 规则、关键风险、deadline/owner、缺失信息。 | 无新增半成品按钮。 | 上下文不足时展示缺失信息，不编造规则。 | 不塞全部 raw events，不代表 production live 或长期 embedding 服务。 |

### 1. 先讲用户痛点，30 秒

讲解口径：

> 飞书群里同一个规则会被多次改口。普通搜索会把旧消息和新消息一起搜出来，评委很难知道现在该信哪条。Copilot 的目标是让 OpenClaw Agent 在做事前先问企业记忆：当前有效结论是什么、证据在哪里、旧版本为什么失效。

展示材料：

- README 顶部“今天先做这个：我的任务”。
- `docs/benchmark-report.md` 的 PRD 指标映射。

### 2. 历史决策召回：`memory.search`，60 秒

OpenClaw example：

```bash
sed -n '1,120p' agent_adapters/openclaw/examples/historical_decision_search.json
```

本地 dry-run：

```bash
python3 scripts/demo_seed.py --json-output reports/demo_replay.json
python3 - <<'PY'
import json
data = json.load(open("reports/demo_replay.json", encoding="utf-8"))
step = data["steps"][0]
print(json.dumps(step["output"], ensure_ascii=False, indent=2))
PY
```

预期输出要点：

- `tool=memory.search`
- `results[0].status=active`
- `results[0].current_value` 包含 `ap-shanghai` 和 `--canary`
- `results[0].evidence[0].quote` 存在
- `results[0].matched_via` 和 `results[0].why_ranked` 能解释为什么排在前面
- `trace.steps` 能看到分层召回路径

讲解口径：

> 这一步不是返回一堆聊天记录，而是返回当前可用的项目规则。Agent 可以直接把这条 active 记忆带入后续回答，同时把 evidence 展示给人看。

Benchmark 对应：

- `docs/benchmark-report.md` 中 `copilot_recall_deploy_region_001`
- Recall@3 = 1.0
- Evidence Coverage = 1.0
- Stale Leakage Rate = 0.0

### 3. 冲突更新和版本链：`memory.explain_versions`，75 秒

OpenClaw example：

```bash
sed -n '1,160p' agent_adapters/openclaw/examples/conflict_update_flow.json
```

本地 dry-run：

```bash
python3 - <<'PY'
import json
data = json.load(open("reports/demo_replay.json", encoding="utf-8"))
step = data["steps"][1]
print(json.dumps(step["output"], ensure_ascii=False, indent=2))
PY
```

预期输出要点：

- `active_version.value` 包含 `ap-shanghai`
- `versions` 同时包含 `superseded` 和 `active`
- `supersedes` 解释新版本覆盖旧值
- 默认 search 不把 `cn-shanghai` 作为当前答案返回

讲解口径：

> 企业记忆不应该删除历史，也不应该让旧值继续误导 Agent。版本链保留“以前说过什么”，但默认答案只用 active 当前值。

Benchmark 对应：

- `docs/benchmark-report.md` 中 `conflict_region_override_001`
- Conflict Update Accuracy = 1.0
- Superseded Leakage Rate = 0.0

### 4. 任务前预取：`memory.prefetch`，60 秒

OpenClaw example：

```bash
sed -n '1,140p' agent_adapters/openclaw/examples/task_prefetch_flow.json
```

本地 dry-run：

```bash
python3 - <<'PY'
import json
data = json.load(open("reports/demo_replay.json", encoding="utf-8"))
step = data["steps"][2]
pack = step["output"]["context_pack"]
print(json.dumps(pack, ensure_ascii=False, indent=2))
PY
```

预期输出要点：

- `context_pack.summary` 说明找到了 active 记忆
- `relevant_memories` 包含部署规则和 evidence
- `stale_superseded_filtered=true`
- `raw_events_included=false`
- `state_mutation=none`

讲解口径：

> 这一步像一个靠谱同事在任务开始前提醒：今天要上线，先看当前部署规则、风险和截止时间。它不会把所有聊天都塞给 Agent，只给短上下文包。

Benchmark 对应：

- `docs/benchmark-report.md` 中 `prefetch_stale_value_filtered`
- Agent Task Context Use Rate = 1.0
- Stale Leakage Rate = 0.0

### 5. Heartbeat reminder candidate，45 秒

本地 dry-run：

```bash
python3 - <<'PY'
import json
data = json.load(open("reports/demo_replay.json", encoding="utf-8"))
step = data["steps"][3]
print(json.dumps(step["output"], ensure_ascii=False, indent=2))
PY
```

预期输出要点：

- `status=dry_run`
- reminder 输出只生成 `candidate`
- `state_mutation=none`
- 敏感内容会被 `[REDACTED:...]` 遮挡
- 不真实发群、不绕过 confirm/reject 治理

讲解口径：

> 主动提醒不是自动骚扰群，也不是偷偷写入新记忆。MVP 只生成待确认提醒，先让人或后续 review surface 决定要不要采纳。

Benchmark 对应：

- `docs/benchmark-report.md` 中 `heartbeat_sensitive_redaction`
- Sensitive Reminder Leakage Rate = 0.0
- Reminder Candidate Rate = 1.0

### 6. 用 Benchmark 收口，50 秒

展示命令：

```bash
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
```

讲解口径：

> Demo 不是临场造的。每条演示能力都能在 benchmark 里找到 case、通过率、失败分类和 recommended fix。今天不追求复赛级压力测试，先保证初赛材料能自证。

截图需求：

- `docs/benchmark-report.md` 的 PRD 指标映射表。
- `docs/benchmark-report.md` 的样例证据表。
- 至少一条 benchmark 命令输出。

## 现场故障处理

| 现场问题 | 先做什么 | fallback |
|---|---|---|
| OpenClaw gateway 不稳定 | 展示 `agent_adapters/openclaw/examples/*.json` | 用 `scripts/demo_seed.py` 的 tool dry-run 输出证明 contract |
| 飞书权限或 Bitable 权限失败 | 不真实写生产空间 | 展示 `memory_engine/bitable_sync.py` dry-run 字段和 `docs/benchmark-report.md#bitable-dry-run-对齐` |
| Cognee / Ollama 没启动 | 不把 demo 说成长期 embedding 服务 | 说明当前 demo 验证 Copilot Core、状态机、hybrid retrieval 和 dry-run；Phase D live embedding gate 已单独证明本机 Ollama provider 可返回 1024 维，但这不等于 productized live |
| 旧 Bot 被问到 | 明确旧 Bot 是 fallback | 展示 README 的“旧 CLI / Bot 兜底”，但叙事保持 OpenClaw-first |
| benchmark 跑失败 | 保留失败输出 | 按 `failure_type`、case_id、recommended fix 记录到 handoff，不删除失败样例 |

## 敏感文件和提交边界

演示可以生成：

```text
reports/demo_replay.json
```

该目录已被 `.gitignore` 忽略，不提交。以下内容也不得提交：

- `.env`
- `.data/cognee/`
- `data/*.sqlite`
- `logs/`
- 真实飞书群聊 ID、用户 ID、token、app secret

## 最后一页口径

> Feishu Memory Copilot 把飞书协作里的“长期有效规则”从聊天噪声里提炼出来。OpenClaw Agent 用 tools 读取当前 active 记忆，Copilot Core 管状态和版本，Cognee 做本地 knowledge / memory substrate，飞书/Bitable/card 负责证据展示和审核。今天的 Demo 证明：它能记住当前结论、解释旧版本、任务前主动预取、生成克制的提醒候选，并且这些能力都有 benchmark 入口。当前可补充说明：OpenClaw Agent runtime 已有受控证据，Phase D live embedding gate 已通过；但 demo 仍不等于生产部署、全量 Feishu workspace ingestion 或长期 embedding 服务。
