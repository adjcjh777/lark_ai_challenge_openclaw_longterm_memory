# Real Feishu Controlled Expansion Checklist

日期：2026-05-01

目标：把 deep research 报告里的“真实飞书受控扩样”落成可执行 gate。当前本地代码和 sandbox 路径已就绪，但本文件不宣称已经完成生产长期运行或全量 workspace ingestion。

## Gate 边界

- 只使用受控测试群、受控 reviewer / owner、受控 Feishu 资源 ID。
- 单次只启一个监听入口：Feishu websocket、Copilot lark-cli sandbox、legacy listener 三选一。
- 所有真实来源必须进入 `handle_tool_request()` / `CopilotService`。
- 低重要性、低风险、无冲突内容可由 review policy 自动确认；项目进展、重要角色、敏感、高风险或冲突内容必须停在 candidate。
- 不提交真实 chat_id、open_id、tenant token、app secret、真实群聊截图原文。

## Smoke Matrix

| 场景 | 前置条件 | 操作 | 通过标准 |
|---|---|---|---|
| allowlist 群静默 candidate probe | 测试群在 allowlist；只启 Copilot live listener | 群内发送一条企业记忆信号消息，不 `@Bot` | 命中 `memory.create_candidate`；低风险可 auto-confirm，高风险进入 reviewer DM；群内默认不刷屏 |
| 主动搜索 | 同上 | `@Bot 生产部署 region 是什么？` | 走 `memory.search`，返回 active 结论、evidence、审计尾部信息 |
| 冲突更新 | 已有 active 旧值 | 群内发送“改成/不对/最终”类更新 | 进入 conflict candidate；旧值默认 search 不泄漏；确认后版本链有 superseded |
| 审核卡片点击 | publisher DM 可达 reviewer / owner | 点击确认、拒绝、要求补证据、标记过期 | card action router 重新生成当前 operator 权限上下文；审计表可读回 |
| `/review` 收件箱 | 至少 1 条候选或冲突候选 | `/review`、`/review conflicts` | 只展示当前 actor 可见条目；mine/conflicts/high_risk 计数正确 |
| Task / Meeting / Bitable fetcher | 受控资源 ID 可读 | 触发 `/task` / `/meeting` / `/bitable` | fetch 前权限 fail-closed；成功结果进入 candidate gate；失败写 sanitized audit |
| Graph 可见价值 | 受控群产生 allowed/disallowed 事件 | 运行 health/admin read-only view | graph node/edge 计数更新；disallowed 群只记录最小 chat 节点，不摄入内容 |

## 读回证据

每个 smoke 至少读回以下证据：

- `memory_audit_events` 中对应 action、permission_decision、reason_code。
- `memory.explain_versions` 对冲突更新的 active / superseded 版本链。
- `scripts/check_copilot_health.py --json` 的 storage / audit / graph 状态。
- 如涉及 dashboard，只使用 read-only admin view，不开放写操作。

## Readiness Check

真实 smoke 前先运行 readiness gate。它只检查前置条件，不打印环境变量值或资源 ID：

```bash
python3 scripts/check_real_feishu_expansion_gate.py \
  --planned-listener copilot-lark-cli \
  --task-id <controlled_task_id> \
  --json
```

也可以用 `--minute-token` 或完整的 `--bitable-app-token` / `--bitable-table-id` / `--bitable-record-id` 组合替代 `--task-id`。返回 `status=pass` 才能进入真实 Feishu smoke。

## 当前状态

- Readiness gate 已用受控测试群、受控 reviewer open_id 和受控 Task GUID 跑通；脚本不打印环境变量值或资源 ID。
- 受控真实 Feishu Task fetch -> candidate smoke 已跑通：Task API 可读，`feishu.fetch_task` 进入 `memory.create_candidate`，生成 1 条 pending candidate；evidence source 为 `feishu_task`，audit 为 `limited_ingestion_candidate / allow`。
- 过程中修正了 Task fetcher 的当前 CLI 兼容性：任务详情读取使用 `lark-cli task tasks get`，不再依赖已不可用的 `task +get-task` shortcut。
- 仍不宣称生产长期运行、全量 workspace ingestion、真实 DM 长期稳定路由或 productized live 完成；后续扩样应继续覆盖 Meeting / Bitable、卡片点击和 `/review` 真实交互。
