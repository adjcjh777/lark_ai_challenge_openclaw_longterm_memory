# Review Surface Operability Handoff

日期：2026-04-28

## 本轮完成什么

本轮推进 `launch-polish-todo.md` 第 7 项：把 review surface 从 dry-run payload 推到更可操作、可追踪、可回滚的本地闭环。

完成内容：

- Candidate Review / Reminder Candidate Bitable 行新增稳定 `sync_key`。
- 非 dry-run 写入前会用 `lark-cli base +record-list` 按 `sync_key` 读取已有记录。
- 如果已有记录存在，写入改用 `lark-cli base +record-upsert --record-id <record_id>` 更新；否则创建新记录。
- 写入成功后再次 `+record-list` 读回确认本轮 `sync_key` 已存在。
- 读已有记录、写入、读回任一步失败时，`sync_payload()` 返回 `ok=false` 和错误摘要，不声称同步成功。

## 改动文件

| 文件 | 说明 |
|---|---|
| `memory_engine/bitable_sync.py` | 给 Candidate Review / Reminder Candidate 增加 `sync_key`，补 upsert、重试和读回确认。 |
| `tests/test_bitable_sync.py` | 增加稳定写回键、已有记录更新、读回确认测试。 |
| `docs/productization/launch-polish-todo.md` | 标记第 7 项本地闭环完成，并写清边界。 |

## 当前边界

可以说：

- Bitable review 写回已有本地可验证的幂等、失败重试和读回确认闭环。
- card action / Bitable review surface 继续只消费 Copilot service 输出，confirm / reject 仍走 `handle_tool_request()` / `CopilotService`。
- permission denied 时不会在 card / Bitable 中展示未授权 evidence 或 current_value。

不能说：

- 不能说真实飞书 card action 已完成生产级长期运行。
- 不能说真实 Feishu DM 已稳定路由到本项目 first-class `memory.*` 工具。
- 不能说 productized live 已完成。

## 验证

已运行：

```bash
python3 scripts/check_openclaw_version.py
python3 -m unittest tests.test_bitable_sync
python3 -m unittest tests.test_feishu_interactive_cards tests.test_copilot_tools tests.test_bitable_sync
python3 -m compileall memory_engine scripts
git diff --check
ollama ps
```

结果摘要：OpenClaw version OK；`tests.test_bitable_sync` 11 tests OK；目标 Feishu / Bitable / Copilot tool 回归 50 tests OK；compileall OK；`git diff --check` OK；`ollama ps` 无本项目模型驻留。

## 飞书看板同步

已同步飞书共享任务看板，并读回确认：

- 任务描述：`2026-04-28 程俊豪：Review surface 可操作写回闭环`
- 状态：`已完成`
- 优先级：`P1`
- 指派给：`程俊豪`
- 任务截止日期：`2026-04-28`
- 记录 ID：`recvi51uDt5kH6`

## 下一步

按 `launch-polish-todo.md` 顺序，下一项是 P1 审计、监控和运维面：把 `memory_audit_events` 从 smoke test 表升级为可查询、可告警、可复盘的运维入口。

---

## 2026-04-29 追加：真实飞书可点击卡片

已补 [real-feishu-interactive-cards-handoff.md](real-feishu-interactive-cards-handoff.md)。Feishu live `card_mode=interactive` 现在按 `CopilotService` 输出生成 typed card；候选审核卡的确认、拒绝、要求补证据、标记过期会从 card action 回到当前 operator 权限上下文，再进入 `handle_tool_request()` / `CopilotService`。这补的是受控 sandbox/pre-production 路径，仍不是生产级 card action 长期运行。

---

## UX-04 追加：记忆收件箱 / 审核队列

日期：2026-04-29

本轮只推进 UX-04，不进入 UX-05 可控提醒体验。

### 队列字段

Candidate Review 行现在可表达审核队列所需字段：

| 字段 | 用途 |
|---|---|
| `review_status` | `pending` / `confirmed` / `rejected` / `needs_evidence` / `expired`。 |
| `source_type` | 候选来源，如 `feishu_message`、`lark_doc`、`feishu_task`、`feishu_meeting`、`lark_bitable` 或测试来源。 |
| `risk_level` | `low` / `medium` / `high`，用于区分高风险暂不建议确认。 |
| `conflict_status` | `no_conflict` / `possible_conflict` / `overrides_active`。 |
| `queue_view` | 可直接筛选的中文视图标签。 |
| `reviewer` | 当前建议处理人，来自 permission actor。 |
| `last_handler` / `last_handled_at` | 最近一次服务层状态处理人和处理时间。 |

### 三类队列视图

在 Bitable 的 `Candidate Review` 表中按字段筛选即可复现：

| 视图 | 筛选方式 | 处理建议 |
|---|---|---|
| 待我审核 | `review_status=pending`，必要时再筛 `reviewer=当前 reviewer` | 可以确认、拒绝、要求补证据或标记过期。 |
| 冲突需判断 | `conflict_status=possible_conflict` 或 `conflict_status=overrides_active` | 先看 `old_value` 和证据，再决定是否确认覆盖。 |
| 高风险暂不建议确认 | `risk_level=high` 或 `queue_view` 包含“高风险暂不建议确认” | 默认不要确认；优先要求补证据或拒绝。 |

这些视图只是 review surface。Copilot Core / SQLite ledger 仍是事实源，Bitable 不能直接决定 active / rejected / expired。

### 状态动作

当前服务层状态流转：

```text
new candidate
  -> pending
  -> confirmed
  -> rejected
  -> needs_evidence
  -> expired
```

操作入口：

| 动作 | 服务层入口 | 结果 |
|---|---|---|
| 确认 | `CopilotService.confirm()` / `memory.confirm` | 候选变 active，可进入默认 recall。 |
| 拒绝 | `CopilotService.reject()` / `memory.reject` | 候选变 rejected，不进入默认 recall。 |
| 要求补证据 | `CopilotService.needs_evidence()` | 候选变 needs_evidence，不作为可信结论展示。 |
| 标记过期 | `CopilotService.expire_candidate()` | 候选变 expired，保留审计但默认不进主待办队列。 |

所有动作都需要有效 `current_context.permission`。缺失、畸形、非 reviewer 权限必须 fail closed。

### 卡片和 Bitable

- Feishu 候选审核卡片展示状态、队列视图、来源、风险、冲突、建议动作和审计 trace。
- reviewer 可见四个动作入口：确认保存、拒绝候选、要求补证据、标记过期。
- 非 reviewer 或 permission denied 时不展示操作按钮，也不展示未授权 evidence / current_value。
- Candidate Review 写回继续使用稳定 `sync_key` 幂等 upsert。
- 非 dry-run 写入会先 `record-list` 查已有记录，写后再次读回确认。
- 任一步失败时 `sync_payload()` 返回 `ok=false`、`errors` 和 `error_summary`；不能声称同步成功。

### 失败处理

- 写 Bitable 失败：保留 dry-run payload 和 `error_summary`，不要把行状态写成已完成。
- 权限失败：只展示安全说明、`request_id`、`trace_id`、`permission_reason`，不展示候选明文。
- 证据不足：用“要求补证据”进入 `needs_evidence`，不要确认成 active。
- 候选已过期：用“标记过期”进入 `expired`，保留审计，不进入默认 recall。
