# Real Feishu Interactive Cards Handoff

日期：2026-04-29

## 本轮完成什么

本轮补齐“真实飞书可点击卡片”的受控 sandbox/pre-production 路径。此前 `memory_engine/copilot/feishu_live.py` 在 `FEISHU_CARD_MODE=interactive` 时仍主要用 `build_card_from_text(reply)` 把回复文本包成通用卡片；现在 Feishu live 回复会消费 `CopilotService` / `handle_tool_request()` 的 typed output，并生成对应的真实 interactive card。

完成内容：

- `memory.search` 使用搜索结果卡。
- `memory.create_candidate` 使用候选审核卡。
- `memory.explain_versions` 使用版本链卡。
- `memory.prefetch` 使用任务前上下文卡。
- 候选审核卡支持点击 `确认保存`、`拒绝候选`、`要求补证据`、`标记过期`。
- card action value 只携带 action 和 candidate id，不内嵌 `current_context`。
- 点击卡片后，会按当前 operator / chat 重新构造 permission context，再进入 `handle_tool_request()` / `CopilotService`。
- 非 reviewer 或权限畸形时 fail closed，candidate 不会被改成 active。

## 改动文件

| 文件 | 说明 |
|---|---|
| `memory_engine/copilot/feishu_live.py` | Feishu live publish 改为按 tool result 生成 typed card；补 `/needs_evidence`、`/expire` 内部动作解析、格式化和上下文 candidate 解析。 |
| `memory_engine/copilot/tools.py` | 增加内部 request type，允许 Feishu card action 路由到 `CopilotService.needs_evidence()` / `expire_candidate()`；不扩展公开 `supported_tool_names()`。 |
| `memory_engine/feishu_events.py` | card action value 支持 `needs_evidence` / `expire` 转成内部 slash command。 |
| `tests/test_copilot_feishu_live.py` | 覆盖候选审核卡真实点击确认、非 reviewer 隐藏按钮、二级动作路由、伪造点击 fail closed。 |
| `tests/test_copilot_tools.py` | 锁住内部 card actions 不进入公开 OpenClaw supported tool list。 |
| `docs/manual-testing-guide.md` | 增加真实飞书互动卡片手动测试流程。 |

## 当前边界

可以说：

- 真实飞书可点击卡片的受控 sandbox/pre-production 路径已接入。
- 候选审核卡的四个动作都会通过 `handle_tool_request()` / `CopilotService`，不直接改 repository。
- 点击动作使用当前 operator 权限上下文；按钮 value 不保存可复用的权限上下文。
- 非 reviewer 点击或伪造点击会 fail closed。

不能说：

- 不能说生产级 Feishu card action 长期运行已完成。
- 不能说全量飞书 workspace 已接入。
- 不能说真实 Feishu DM 已稳定覆盖所有 `fmc_*` / `memory.*` 工具动作。
- 不能说 productized live 已完成。

## 手动测试入口

按 [手动测试指南](../../manual-testing-guide.md) 的“真实飞书互动卡片点击测试”执行：

1. 确认单监听。
2. 确认 `FEISHU_CARD_MODE=interactive`。
3. 向受控测试群或测试私聊发送 `/remember ...`。
4. 检查候选审核卡是否出现四个按钮。
5. 分别用新候选测试确认、拒绝、要求补证据、标记过期。
6. 用 `scripts/query_audit_events.py` 读回最近审计。

## 验证

已运行：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_feishu_live tests.test_feishu_interactive_cards -v
python3 -m unittest tests.test_copilot_tools tests.test_copilot_governance -v
git diff --check
ollama ps
```

结果摘要：

- OpenClaw version OK：`2026.4.24`。
- Agent harness OK：required docs、execution contract、OpenClaw lock、Cognee adapter boundary 均通过。
- compileall OK。
- `tests.test_copilot_feishu_live` + `tests.test_feishu_interactive_cards`：38 tests OK。
- `tests.test_copilot_tools` + `tests.test_copilot_governance`：39 tests OK。
- `tests.test_copilot_schemas` + `tests.test_copilot_permissions`：33 tests OK。
- `git diff --check` OK。
- `ollama ps` 初次发现 `qwen3-embedding:0.6b-fp16` 驻留，已执行 `ollama stop qwen3-embedding:0.6b-fp16`；复查 `ollama ps` 为空。

## 下一步

下一步不是扩展更多按钮，而是在受控测试群里做真实点击扩样：确认、拒绝、要求补证据、标记过期各至少一次，记录 request_id / trace_id / audit readback。扩样仍保持 candidate-only 和 no-overclaim。

## 飞书看板同步

已同步飞书共享任务看板，并读回确认：

- 任务描述：`2026-04-29 程俊豪：真实飞书可点击卡片受控路径`
- 状态：`已完成`
- 优先级：`P1`
- 指派给：`程俊豪`
- 任务截止日期：`2026-04-29`
- 记录 ID：`recvi9npnND5b8`
