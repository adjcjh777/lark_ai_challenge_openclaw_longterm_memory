# UX-04：记忆收件箱 / 审核队列

日期：2026-04-29
负责人：程俊豪
状态：待执行
上游总览：[用户体验产品化 TODO 清单](../user-experience-todo.md)
执行顺序：第 4 个

## 本轮要做什么

把 candidate-only 治理能力整理成用户可处理的“记忆收件箱”：

| 视图 | 目的 |
|---|---|
| 待我审核 | 需要当前 reviewer 确认或拒绝的候选。 |
| 冲突需判断 | 新候选可能覆盖已有 active memory，需要人工选择。 |
| 高风险暂不建议确认 | 涉及敏感、权限不足、证据不完整或误记风险的候选。 |

审核队列可以先落在 Bitable 或文档入口里，但必须保持 Copilot Core 是事实源。

## 为什么现在做

candidate-only 是本项目和普通聊天 Bot 的关键差异。当前治理层已经能 create / confirm / reject candidate，Bitable 写回也已有本地闭环，但用户还缺一个清晰视图去处理“哪些记忆需要我判断”。

## 本阶段不用做

- 本阶段不用做完整企业后台。
- 本阶段不用让 Bitable 成为 source of truth。
- 本阶段不用把所有真实飞书来源自动 active。
- 本阶段不用在写回失败时声称同步成功。

## 执行任务

| 顺序 | 任务 | 文件位置 | 完成标准 |
|---|---|---|---|
| 1 | 定义审核队列字段和状态 | `memory_engine/copilot/governance.py`、`memory_engine/bitable_sync.py` | 每条候选至少有状态、来源、风险、冲突、建议动作、reviewer、最后处理人和最后处理时间。 |
| 2 | 建立三类队列视图 | `memory_engine/bitable_sync.py`、`docs/reference/` 或新 handoff | 待我审核、冲突需判断、高风险暂不建议确认三类视图可通过字段筛选复现。 |
| 3 | 补状态流转动作 | `memory_engine/copilot/governance.py`、`memory_engine/copilot/tools.py` | 新候选 -> 待审核 -> 已确认 / 已拒绝 / 需补证据 / 已过期 的流转可审计。 |
| 4 | 接入卡片和 Bitable upsert/readback | `memory_engine/feishu_cards.py`、`memory_engine/bitable_sync.py`、`tests/test_bitable_sync.py` | Candidate Review 行可幂等 upsert；写入后读回确认；失败时返回错误摘要。 |
| 5 | 写清操作 runbook | `docs/productization/handoffs/review-surface-operability-handoff.md` 或新 handoff | 人类知道如何查看队列、确认、拒绝、要求补证据和判断失败。 |

## 队列字段建议

| 字段 | 说明 |
|---|---|
| sync_key | Bitable 幂等写回键。 |
| candidate_id | 内部候选 ID，可放审计详情，不作为用户主操作入口。 |
| subject | 候选主题。 |
| proposed_value | 候选新结论。 |
| source_type | feishu_message / lark_doc / feishu_task / feishu_meeting / lark_bitable 等。 |
| risk_level | low / medium / high。 |
| conflict_status | no_conflict / possible_conflict / overrides_active。 |
| review_status | pending / confirmed / rejected / needs_evidence / expired。 |
| reviewer | 当前建议处理人。 |
| permission_decision | allow / deny / redacted，用于审计和展示控制。 |
| trace_id | 审计追踪。 |

## 状态流转规则

```text
new candidate
  -> pending review
  -> confirmed
  -> rejected
  -> needs_evidence
  -> expired
```

规则：

- confirmed 后才能进入 active memory。
- rejected 不能进入 recall。
- needs_evidence 不能作为可信结论展示。
- expired 应保留审计，但默认不进入待处理主队列。

## 验收命令

代码实现后运行：

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_governance tests.test_copilot_tools
python3 -m unittest tests.test_bitable_sync tests.test_feishu_interactive_cards
git diff --check
ollama ps
```

如果触达真实 Bitable 空间：

```bash
lark-cli base +record-list
```

并在 handoff 里写清读回结果。真实 token、chat_id、open_id 不写入仓库。

## 完成标准

- 用户能按状态查看候选。
- 冲突、高风险和普通待审候选不会混在同一不可读列表里。
- confirm / reject / needs_evidence / expired 都有审计。
- Bitable 写回失败不会被包装成成功。
- 队列视图不显示未授权敏感内容。

## 失败处理

- 如果真实 Bitable 写入失败，保留 dry-run payload 和错误摘要，不更新状态为已完成。
- 如果状态机字段不够，先在 governance 层补状态，再适配 Bitable。
- 如果权限拒绝导致无法展示候选明文，只显示安全说明和处理入口。

## 顺序执行出口

完成 UX-04 后再进入 [UX-05 可控提醒体验](ux-05-controlled-reminder-experience.md)。UX-05 会把 heartbeat reminder candidate 接入同一套审核和控制体验。
