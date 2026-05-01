# Feishu 非 @ 群消息事件 Gate Handoff

日期：2026-05-01
阶段：live passive message delivery 排障 gate

## 本轮完成了什么

- 新增 `scripts/check_feishu_passive_message_event_gate.py`，用于检查捕获到的 Feishu / OpenClaw NDJSON 或 JSON 事件日志里是否真的出现了非 `@Bot` 的群文本消息。
- gate 会区分四类关键结果：
  - `passive_group_message_seen`：捕获到普通非 @ 群文本，可继续判断 passive screening。
  - `reaction_only_no_passive_message_event`：只看到 reaction，说明当前 live 投递证据不覆盖普通群文本。
  - `only_at_mention_group_messages_seen`：只看到 @Bot 群消息。
  - `expected_chat_not_seen`：事件来自非目标群。
- 输出会脱敏 message/chat/sender id，只保留计数和短文本预览。
- 更新 `docs/manual-testing-guide.md` 和 `docs/productization/feishu-staging-runbook.md`，把该 gate 放到真实 Feishu 非 @ 群消息扩测流程里。

## 关键文件

| 文件 | 说明 |
|---|---|
| `scripts/check_feishu_passive_message_event_gate.py` | 从 stdin 或 `--event-log` 读取 NDJSON/JSON，复用 `message_event_from_payload()` 判断普通群文本是否到达。 |
| `tests/test_feishu_passive_message_event_gate.py` | 覆盖 passive pass、reaction-only、只 @Bot、目标群不匹配和 NDJSON wrapper。 |
| `docs/manual-testing-guide.md` | 新增“非 @ 群消息事件投递 gate”人工验收步骤。 |
| `docs/productization/feishu-staging-runbook.md` | 新增 reaction-only 症状的诊断和下一步。 |

## 验证

```bash
python3 -m unittest tests.test_feishu_passive_message_event_gate
python3 -m compileall scripts
```

## 边界

- 这个 gate 只检查捕获日志里的事件形态，不主动连接飞书，也不证明生产长期运行。
- 如果真实日志仍返回 `reaction_only_no_passive_message_event`，不能说非 @ 群消息 live 投递已打通。
- 通过该 gate 之后，还要继续读回 candidate / audit，才能证明 passive screening 的端到端链路。
