# UX-02：重做记忆卡片信息架构

日期：2026-04-29
负责人：程俊豪
状态：已完成
上游总览：[用户体验产品化 TODO 清单](../user-experience-todo.md)
执行顺序：第 2 个

## 本轮要做什么

把飞书卡片从“调试字段展示”改成 4 类稳定的用户决策模板：

| 模板 | 用户第一眼要看懂什么 |
|---|---|
| 搜索结果卡 | 当前结论是什么，证据是什么，旧值是否已被过滤。 |
| 候选审核卡 | 这条候选能不能确认，风险和冲突是什么。 |
| 版本解释卡 | 当前版本为什么覆盖旧版本，时间线是什么。 |
| 任务前上下文卡 | Agent 做本次任务前必须带入哪些规则、风险和缺失信息。 |

卡片是飞书里的交互载体。它可以带按钮，但按钮必须真实可用；半成品按钮不能暴露给评委。

## 为什么现在做

当前 `candidate_review_payload()` 已有 confirm / reject / source / version 等基础字段，但还混有 `source`、`versions`、`needs_review` 等偏 dry-run 和调试的表达。评委看到卡片时应该先判断“我该不该确认”，而不是先解析系统内部状态。

## 本阶段不用做

- 本阶段不用做新的卡片美术系统或复杂 UI 设计器。
- 本阶段不用把 Bitable / card 写回说成生产级长期运行。
- 本阶段不用让卡片绕过服务层直接改 repository。
- 本阶段不用显示未授权 evidence、current_value 或 summary。

## 执行任务

| 顺序 | 任务 | 文件位置 | 完成标准 |
|---|---|---|---|
| 1 | 盘点现有卡片 payload 和字段 | `memory_engine/feishu_cards.py`、`tests/test_feishu_interactive_cards.py` | 已完成：用户主内容进入 `user_content`，`request_id`、`trace_id`、`permission_decision` 进入 `audit_details`；`source`、`needs_review`、reminder confirm/dismiss 这类不可用按钮不暴露给评委。 |
| 2 | 定义 4 类卡片 payload builder | `memory_engine/feishu_cards.py` | 已完成：`search_result_payload()`、`candidate_review_payload()`、`version_chain_payload()`、`prefetch_context_payload()` 形成稳定 builder；搜索和 prefetch 新增对应 card builder，旧 candidate/version/reminder 入口保持兼容。 |
| 3 | 收敛按钮行为 | `memory_engine/feishu_cards.py`、`memory_engine/copilot/feishu_live.py` | 已完成：评委可见按钮只保留现有可路由动作，候选卡为 confirm / reject，搜索卡为 versions；非 reviewer/owner/admin 不显示确认和拒绝。 |
| 4 | 对齐 Bitable 写回字段 | `memory_engine/bitable_sync.py`、`tests/test_bitable_sync.py` | 已完成：Candidate Review 和 Reminder Candidate 的 `sync_key`、状态、trace、permission 字段仍由现有 payload 生成并通过测试。 |
| 5 | 更新演示材料 | `docs/demo-runbook.md`、`docs/human-product-guide.md` | 已完成：已补 4 类卡片输入、输出、按钮含义、fallback 和 no-overclaim 边界。 |

## 本轮实现结果

4 类稳定 builder：

| Builder | 输入 | 主输出 | 审计详情 |
|---|---|---|---|
| `search_result_payload()` / `build_search_result_card()` | `memory.search` 的 service/tool 输出 | 当前结论、证据 quote、active 状态、旧值已过滤、用户可读排序理由 | `request_id`、`trace_id`、`permission_decision` |
| `candidate_review_payload()` / `build_candidate_review_card()` | `memory.create_candidate` 或 confirm/reject deny 输出 | 待确认新记忆、来源、证据、风险等级、冲突摘要、建议动作 | `request_id`、`trace_id`、`permission_decision` |
| `version_chain_payload()` / `build_version_chain_card()` | `memory.explain_versions` 输出 | 当前版本、旧版本、覆盖原因、时间线摘要 | `memory_id`、`request_id`、`trace_id`、`permission_decision` |
| `prefetch_context_payload()` / `build_prefetch_context_card()` | `memory.prefetch` 输出 | 本次任务、要带入的 active 规则、风险、deadline、缺失信息 | `request_id`、`trace_id`、`permission_decision` |

按钮收敛：

- 候选审核卡：只有 reviewer / owner / admin 才显示“确认保存”和“拒绝候选”；点击后仍走 `handle_tool_request()` / `CopilotService`。
- 搜索结果卡：只显示“解释版本”，触发已有 `versions` / `memory.explain_versions` 路径。
- 来源信息作为字段展示；本阶段不暴露半成品 `source` 按钮。
- reminder 仍是候选展示，不暴露 confirm/dismiss dry-run 按钮给评委。

## 卡片信息架构

### 搜索结果卡

第一屏字段：

- 当前结论。
- evidence quote。
- 版本状态：active / superseded filtered。
- 为什么排在前面：只展示用户可理解的理由，不直接展开 `why_ranked` 原始结构。

底部审计字段：

- request_id。
- trace_id。
- permission decision summary。

### 候选审核卡

第一屏字段：

- 待确认的新记忆。
- 来源和证据。
- 风险等级。
- 是否和已有 active memory 冲突。
- 建议动作：确认、拒绝、需补证据。

按钮规则：

- reviewer / owner / admin 才能看到确认和拒绝。
- 非 reviewer 只能看到状态和来源。
- 权限拒绝时不能显示明文 evidence。

### 版本解释卡

第一屏字段：

- 当前 active 版本。
- 被覆盖旧版本。
- 覆盖原因。
- 时间线摘要。

底部审计字段：

- memory_id 可以放审计详情，不占主答案。
- trace_id 和 permission decision 不作为标题。

### 任务前上下文卡

第一屏字段：

- 本次任务要带入的规则。
- 关键风险。
- deadline 或 owner。
- 缺失信息。

禁止行为：

- 不把所有 raw events 塞进卡片。
- 不把 superseded 旧值当作当前上下文。

## 验收命令

代码实现后运行：

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_feishu_interactive_cards tests.test_bitable_sync
python3 -m unittest tests.test_copilot_feishu_live tests.test_copilot_tools
git diff --check
ollama ps
```

如果只改文档或示例 payload，最低运行：

```bash
python3 scripts/check_openclaw_version.py
git diff --check
ollama ps
```

## 完成标准

- 4 类卡片都有稳定 builder 和单测覆盖。
- 卡片第一屏回答“这是什么、为什么重要、我该点什么”。
- 评委版不出现不可用按钮。
- confirm / reject / explain / source 动作仍进入 `handle_tool_request()` / `CopilotService`。
- 写回失败时文档和输出都不声称同步成功。

## 失败处理

- 如果飞书卡片能力不足以承载某个按钮，先隐藏按钮，并在主答案给出命令 fallback。
- 如果 Bitable 写回失败，保留本地 payload、错误摘要和 readback 失败状态。
- 如果卡片字段和 benchmark 字段冲突，以 Copilot service 输出为事实源，再适配展示层。

## 顺序执行出口

完成 UX-02 后再进入 [UX-03 用户可理解解释层](ux-03-user-facing-explanation-layer.md)。UX-03 会把卡片里的“为什么”抽成稳定解释口径。
