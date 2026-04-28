# 真实飞书权限映射 handoff

日期：2026-04-28
阶段：产品后期打磨 P0
负责人：程俊豪

## 先看这个

1. 本阶段补的是第一批真实飞书权限映射，不是完整企业权限后台。
2. 已完成 sender open_id 到 tenant / organization 的本机配置映射，并把 chat / document source context mismatch 变成 fail closed。
3. 飞书 live sandbox 仍然只在受控测试群内使用，真实飞书来源仍只进入 candidate（待确认记忆）。
4. 下一步如果继续做权限，需要接真实组织通讯录、文档 ACL 和长期权限缓存；本阶段不用做。
5. 遇到问题先记录触发消息、`request_id`、`trace_id`、reason_code 和是否泄露 evidence/current_value。

## 做了什么

- `memory_engine/copilot/feishu_live.py` 支持按 `COPILOT_FEISHU_ACTOR_TENANT_MAP` 和 `COPILOT_FEISHU_ACTOR_ORGANIZATION_MAP` 把真实飞书 sender open_id 映射成 permission actor 的 tenant 和 organization。
- `memory_engine/copilot/permissions.py` 不再只接受 demo tenant / org；会接受项目配置里的真实 Feishu tenant / org，并继续拒绝未配置的 tenant / org。
- `memory_engine/copilot/retrieval.py` 在搜索结构化过滤阶段按每条 memory 的 tenant、organization、visibility 和 source context 再过滤，避免真实 actor 读到不属于自己的 demo / 其他租户记录。
- `current_context.chat_id` 与 `current_context.permission.source_context.chat_id` 不一致时返回 `permission_denied`，reason_code 为 `source_context_mismatch`。
- `current_context.metadata.document_id` 或 `source_doc_id` 与 permission source document 不一致时同样 fail closed。
- 拒绝响应仍不返回 `current_value`、`summary`、`evidence` 明文。

## 怎么配置

示例：

```bash
export COPILOT_FEISHU_ACTOR_TENANT_MAP="ou_xxx=tenant:feishu-real"
export COPILOT_FEISHU_ACTOR_ORGANIZATION_MAP="ou_xxx=org:feishu-real"
export COPILOT_FEISHU_TENANT_ID="tenant:feishu-real"
export COPILOT_FEISHU_ORGANIZATION_ID="org:feishu-real"
```

说明：

- `COPILOT_FEISHU_ACTOR_TENANT_MAP` 和 `COPILOT_FEISHU_ACTOR_ORGANIZATION_MAP` 是按真实飞书 open_id 做的窄映射。
- `COPILOT_FEISHU_TENANT_ID` 和 `COPILOT_FEISHU_ORGANIZATION_ID` 是当前 staging 允许的默认真实租户和组织。
- 没有配置进允许列表的 tenant / organization 会继续被拒绝。

## 验证命令

```bash
python3 scripts/check_openclaw_version.py
python3 -m unittest tests.test_copilot_permissions tests.test_copilot_feishu_live
python3 -m compileall memory_engine scripts
git diff --check
ollama ps
```

## 仍未完成

- 还没有接飞书通讯录 / 组织架构 API 做自动 tenant / organization 解析。
- 还没有接真实文档 ACL、群聊成员权限和权限缓存。
- 还没有把权限后台做成 productized live 的长期管理界面。
- 真实 Feishu DM 到本项目 first-class `memory.*` 工具路由仍是下一项 P0 风险，不在本阶段完成。
