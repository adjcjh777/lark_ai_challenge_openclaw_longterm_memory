# 真实飞书权限映射 Handoff

日期：2026-04-28
负责人：程俊豪
阶段：后期打磨 P0

## 本阶段做了什么

把原先只接受 `tenant:demo` / `org:demo` 的本地权限判断，升级为真实飞书上下文映射：

- `current_context` 显式携带 `tenant_id`、`organization_id`、`visibility_policy` 和 `document_id`。
- Feishu live sandbox 从环境变量读取 `COPILOT_FEISHU_TENANT_ID`、`COPILOT_FEISHU_ORGANIZATION_ID`、`COPILOT_FEISHU_VISIBILITY`，并同步写入 `current_context.permission.actor`。
- `permissions.py` 用目标上下文判断 tenant / organization / chat / document 是否匹配，不再把 demo 常量作为唯一允许值。
- 真实飞书 candidate 写入 `raw_events`、`memories`、`memory_versions`、`memory_evidence` 时带上 tenant、organization、workspace 和 visibility。

## 完成标准

已完成：

- 非 demo 的真实飞书 tenant / organization 在目标上下文一致时允许进入 candidate-only 流程。
- tenant mismatch、organization mismatch、private non-owner、source context mismatch 都 fail closed。
- deny response 不返回 `current_value`、`summary`、`evidence` 明文。
- confirm / reject 仍要求 reviewer / owner / admin。
- 真实 Feishu document ingestion 仍在 fetch 前通过 permission gate。

## 验收证据

本阶段新增和覆盖的测试：

```bash
python3 -m unittest tests.test_copilot_permissions tests.test_copilot_feishu_live
```

新增覆盖点：

- `test_real_feishu_tenant_and_org_are_allowed_when_context_matches`
- `test_source_context_chat_mismatch_denies_without_evidence`
- `test_permission_context_maps_real_feishu_tenant_org_and_chat`

## 边界

这不是生产部署。

这也不代表全量 Feishu workspace ingestion 已完成。真实飞书来源仍只进入 candidate，不能自动 active。

真实 Feishu DM 到本项目 first-class `fmc_*` / `memory.*` tool routing 的 live E2E 仍未完成，仍是后续任务。
