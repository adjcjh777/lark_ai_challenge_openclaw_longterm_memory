# UX-03：用户可理解的“为什么这样回答”解释层

日期：2026-04-29
负责人：程俊豪
状态：待执行
上游总览：[用户体验产品化 TODO 清单](../user-experience-todo.md)
执行顺序：第 3 个

## 本轮要做什么

把系统里的 evidence、trace、version chain 和 permission decision 翻译成用户能理解的解释层。

解释层不是审计日志。它要回答：

- 当前结论是什么。
- 为什么认为这是当前结论。
- 它来自哪条证据。
- 旧值为什么被覆盖。
- 如果不能看，原因是什么。

trace 是工程链路追踪 ID；permission decision 是权限判断结果。它们应该保留，但不应该抢占主答案。

## 为什么现在做

当前系统已经有 active / superseded 版本链、evidence quote、`why_ranked`、`request_id`、`trace_id` 和 `permission_decision`。这些字段对审计有用，但普通用户需要的是一句能信任的解释，而不是内部字段列表。

## 本阶段不用做

- 本阶段不用做完整审计 UI。
- 本阶段不用把未授权字段放进解释里。
- 本阶段不用返回所有历史版本；默认答案只返回 active 版本。
- 本阶段不用把 Cognee / embedding trace 当作用户主解释。

## 执行任务

| 顺序 | 任务 | 文件位置 | 完成标准 |
|---|---|---|---|
| 1 | 定义用户解释字段契约 | `memory_engine/copilot/service.py`、`memory_engine/copilot/schemas.py` | search、explain_versions、prefetch、permission denied 输出都有可选的用户解释字段；字段不破坏现有 schema。 |
| 2 | 把检索原因翻译成用户语言 | `memory_engine/copilot/retrieval.py`、`tests/test_copilot_retrieval.py` | `matched_via` / `why_ranked` 能生成“命中当前 active 记忆、证据完整、旧值已过滤”等可读原因。 |
| 3 | 把版本链翻译成用户语言 | `memory_engine/copilot/governance.py`、`memory_engine/copilot/service.py` | `memory.explain_versions` 输出当前版本、旧版本、覆盖原因和证据摘要；默认 search 不展示 superseded 明文。 |
| 4 | 把权限拒绝翻译成安全说明 | `memory_engine/copilot/permissions.py`、`tests/test_copilot_permissions.py` | deny response 说明不能查看的原因，但不包含未授权 `current_value`、`summary` 或 `evidence`。 |
| 5 | 接入飞书卡片和 benchmark | `memory_engine/feishu_cards.py`、`benchmarks/copilot_conflict_cases.json`、`docs/benchmark-report.md` | 卡片主答案使用用户解释；benchmark 或报告能检查旧值泄漏率和解释覆盖。 |

## 解释模板

### 搜索命中

建议口径：

```text
当前结论是：{current_value}
原因：这条记忆仍是 active 状态，并且证据来自 {source_summary}。
旧值处理：旧版本已被更新覆盖，默认不作为当前答案返回。
```

### 版本覆盖

建议口径：

```text
当前采用 {new_value}，因为 {updated_at} 的新证据覆盖了旧结论 {old_value}。
旧版本仍保留在版本链里，用于追溯，不会进入默认召回。
```

### 权限拒绝

建议口径：

```text
这条记忆属于其他 tenant / organization / private source，当前请求没有访问权限。
我不会显示具体内容或证据。如需查看，请让 owner 或 reviewer 在对应上下文中确认权限。
```

禁止口径：

```text
你不能看这条记忆：{敏感 current_value}
```

## 验收命令

代码实现后运行：

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_retrieval tests.test_copilot_permissions
python3 -m unittest tests.test_copilot_tools tests.test_feishu_interactive_cards
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
git diff --check
ollama ps
```

## 完成标准

- 搜索结果有用户可读解释。
- 版本解释能讲清 active / superseded 关系。
- 权限拒绝不会泄露未授权内容。
- 审计字段仍可查，但不占主答案。
- benchmark 保持 stale leakage 和 sensitive leakage 为可检查指标。

## 失败处理

- 如果解释层难以一次覆盖所有工具，先覆盖 search、explain_versions 和 permission denied。
- 如果某条解释缺 evidence，不能把它包装成可信结论，应返回“证据不足，建议进入 candidate 或补证据”。
- 如果测试发现旧值进入默认 search，应优先修 retrieval / governance，而不是只在卡片层隐藏。

## 顺序执行出口

完成 UX-03 后再进入 [UX-04 记忆收件箱 / 审核队列](ux-04-memory-inbox-review-queue.md)。UX-04 会把候选、冲突和高风险内容整理成可处理队列。
