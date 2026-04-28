# UX-05：主动提醒变成可控提醒体验

日期：2026-04-29
负责人：程俊豪
状态：待执行
上游总览：[用户体验产品化 TODO 清单](../user-experience-todo.md)
执行顺序：第 5 个

## 本轮要做什么

把 `heartbeat.review_due` 从“生成 reminder candidate 的 MVP 原型”升级为可控提醒体验：

```text
reminder candidate
  -> 审核队列
  -> 用户确认 / 忽略 / 延后 / 关闭同类提醒
  -> 写审计和冷却状态
```

reminder candidate 指“待确认提醒”。它不是自动群推送，也不是 active memory。

## 为什么现在做

主动提醒容易出价值，也容易出事故。当前项目已经有安全边界：只生成 reminder candidate，不直接真实群推送。本轮要把这个安全边界做成用户可理解、可控制、可审计的体验。

## 本阶段不用做

- 本阶段不用直接向真实群聊推送提醒。
- 本阶段不用做复杂个性化推荐。
- 本阶段不用把 reminder candidate 自动变成 active memory。
- 本阶段不用泄露 token、secret、password、private key 等敏感内容。

## 执行任务

| 顺序 | 任务 | 文件位置 | 完成标准 |
|---|---|---|---|
| 1 | 定义提醒动作契约 | `memory_engine/copilot/schemas.py`、`memory_engine/copilot/service.py` | reminder candidate 支持 confirm、ignore、snooze、mute_same_type 四类动作；字段向后兼容。 |
| 2 | 补冷却和去重状态 | `memory_engine/copilot/service.py`、`memory_engine/copilot/heartbeat.py` | 同类提醒在 cooldown 内不重复打扰；延后后有 next_review_at 或等价字段。 |
| 3 | 接入审核队列和卡片 | `memory_engine/feishu_cards.py`、`memory_engine/bitable_sync.py` | Reminder Candidate 能出现在审核队列；按钮或字段能表达确认、忽略、延后、关闭同类。 |
| 4 | 强化敏感内容处理 | `memory_engine/copilot/heartbeat.py`、`tests/test_copilot_heartbeat.py` | 敏感提醒只显示脱敏摘要；非 reviewer 或权限不足时 withheld / redacted。 |
| 5 | 增加 UX 指标 | `benchmarks/copilot_heartbeat_cases.json`、`docs/benchmark-report.md` | 指标包含误提醒率、敏感泄漏率、重复提醒率和用户确认负担。 |

## 提醒卡片信息

提醒主内容：

- 为什么提醒。
- 这条提醒和哪个 active memory / candidate 有关。
- 证据摘要。
- 建议处理人。
- 冷却时间。
- 风险等级。

可见动作：

| 动作 | 含义 |
|---|---|
| 确认提醒有用 | 记录 positive review，不自动 active 新记忆。 |
| 忽略本次 | 本次不再提示，但不关闭同类规则。 |
| 延后 | 写入下一次可提醒时间。 |
| 关闭同类提醒 | 对相同 subject / trigger type 写入 mute。 |

## 验收命令

代码实现后运行：

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_heartbeat tests.test_copilot_tools
python3 -m unittest tests.test_bitable_sync tests.test_feishu_interactive_cards
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
git diff --check
ollama ps
```

## 完成标准

- reminder candidate 能进入审核队列。
- 用户能忽略、延后或关闭同类提醒。
- cooldown 和 dedup 行为可测试。
- 敏感提醒不直接暴露敏感内容。
- 文档明确本阶段不是真实群推送。

## 失败处理

- 如果还不能安全实现 snooze / mute，先只保留 ignore，但文档必须标为未完成。
- 如果敏感字段识别不稳定，默认 redacted，不要为了体验暴露原文。
- 如果 reminder 误触发率升高，应优先扩 benchmark 和阈值规则，不急着接真实推送。

## 顺序执行出口

完成 UX-05 后再进入 [UX-06 真实用户表达样本评测](ux-06-real-user-expression-benchmark.md)。UX-06 会把提醒误触发和误记问题纳入真实表达评测。
