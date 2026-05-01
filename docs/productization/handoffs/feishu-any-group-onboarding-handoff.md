# Feishu Any-Group Onboarding Handoff

日期：2026-05-01

## 结论

本轮完成的是“任意群可 onboarding / 可显式启用”的本地/pre-production 闭环，不是“拉 bot 到任意群后自动开始记忆”。

当前行为：

- 新群进入 Feishu live 入口后，会登记最小 `feishu_chat` 图谱节点，并写入 `feishu_group_policies` 的 `pending_onboarding` 策略。
- 未在 allowlist、且未启用群策略的群，不写 `raw_events`，不创建 candidate，不记录消息正文。
- `@Bot /settings` 或 `/group_settings` 可以在未启用群里查看 onboarding 状态和运行边界。
- reviewer/admin 可在当前群执行 `@Bot /enable_memory`，把该群策略设为 `active` 且 `passive_memory_enabled=true`；之后非 `@Bot` 群消息才会做静默 candidate probe。
- reviewer/admin 可执行 `@Bot /disable_memory` 关闭当前群静默候选筛选。
- OpenClaw gateway 本地 `route_gateway_message()` 现在也覆盖 `/settings`、`/enable_memory`、`/disable_memory`：如果 gateway 抢到群设置事件，会进入同一 `feishu_group_policies` 读写和 audit 路径，而不是必然回落旧 agent。审计 `source_context.entrypoint` 标为 `openclaw_gateway_live`。
- 启用、关闭和无权限写入都会写 `memory_audit_events`。
- Admin dashboard 新增 Groups 视图/API，可查看群策略状态，但仍是本地/pre-production 后台，不是生产级企业配置后台。

## 代码位置

| 文件 | 变更 |
|---|---|
| `memory_engine/db.py` | `SCHEMA_VERSION=5`；新增 `feishu_group_policies` 表和索引。 |
| `memory_engine/copilot/group_policies.py` | 新增群策略读写、启用、禁用、审计 helper。 |
| `memory_engine/copilot/feishu_live.py` | 非 allowlist 群允许 settings/onboarding 命令；新增 `/enable_memory`、`/disable_memory`；群策略启用后可放行静默 candidate probe。 |
| `scripts/openclaw_feishu_remember_router.py` | OpenClaw gateway 本地路由新增群设置、启用、禁用入口；reviewer/admin allow，member deny 并写审计。 |
| `memory_engine/feishu_cards.py` | 群设置卡展示当前群状态、onboarding policy 和启停命令。 |
| `memory_engine/copilot/admin.py` | Summary/metrics/API/Groups tab 展示 `feishu_group_policies` 状态。 |
| `tests/test_copilot_feishu_live.py` | 覆盖非 allowlist 群 settings、授权启用、无权拒绝、禁用后停止静默筛选。 |
| `tests/test_copilot_admin.py` | 覆盖群策略 API、summary、metrics 和 dashboard tab。 |

## 验证

已跑：

```bash
python3 -m unittest tests.test_copilot_feishu_live
python3 -m unittest tests.test_copilot_admin
python3 -m unittest tests.test_openclaw_feishu_remember_router
```

收尾仍需按 AGENTS 追加完整必跑验证后再提交。

## 不能对外声称

- 不能说已经全量接入 Feishu workspace。
- 不能说 bot 拉进任意群会自动记录和存储记忆。
- 不能说这是生产级群配置后台或长期 live 运行。
- 不能说真实群启停和长期 DM 投递已经完成生产验证；当前是本地/pre-production 闭环。
