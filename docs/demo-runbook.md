# 2026-05-04 OpenClaw-native Demo Runbook

目标：用 5 分钟证明 Feishu Memory Copilot 不是普通聊天搜索，而是能在 OpenClaw Agent 任务前主动调取“有证据、有版本、有状态”的企业协作记忆。

> **状态更新（2026-04-28）**：本 runbook 对应的 2026-05-04 Demo 固定任务已经完成，保留为可复现演示证据。后续不要从 2026-05-04 日期计划继续补任务；新的执行入口是 `docs/productization/full-copilot-next-execution-doc.md`。

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

## 5 分钟流程

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
