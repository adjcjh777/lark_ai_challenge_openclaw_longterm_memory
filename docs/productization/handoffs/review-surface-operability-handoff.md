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
