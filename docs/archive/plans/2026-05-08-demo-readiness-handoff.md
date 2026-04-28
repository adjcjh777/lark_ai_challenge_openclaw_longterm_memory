# 2026-05-08 Demo Readiness Handoff

阶段：Demo-ready + Pre-production Readiness 已完成本地闭环。

## 先看这个

1. 今天把 Phase 6 的 healthcheck（健康检查脚本）往前收口成 Demo readiness（演示前检查）：一个命令同时检查 OpenClaw 版本、healthcheck、Demo replay 和 provider 配置状态。
2. 我接下来从 [scripts/check_demo_readiness.py](../../scripts/check_demo_readiness.py) 开始；它会生成 [reports/demo_replay.json](../../reports/demo_replay.json)，并检查每个演示步骤是否为 `ok=true`。
3. 要交付的是本地可运行、可诊断、可给队友照着跑的演示前门禁，以及受控飞书测试群 live sandbox；不是生产部署、全量飞书空间接入或 productized live。
4. 判断做对：`python3 scripts/check_demo_readiness.py` 和 `python3 scripts/check_demo_readiness.py --json` 都通过；如果任一 replay step 失败，readiness 整体必须失败。
5. 遇到问题记录：失败 step 名称、provider 状态、OpenClaw 版本、是否触发 Ollama、以及是否有人把 demo/pre-production 写成生产 live。

## 已完成

- 更新 [scripts/demo_seed.py](../../scripts/demo_seed.py)，给 `memory.search`、`memory.explain_versions`、`memory.prefetch` 和 `heartbeat.review_due` 的 demo replay 输入补齐合法 `current_context.permission`。
- 新增 [scripts/check_demo_readiness.py](../../scripts/check_demo_readiness.py)，聚合 OpenClaw version、Phase 6 healthcheck、Demo replay step-level 和 provider configuration-only 检查。
- 新增 [tests/test_demo_seed.py](../../tests/test_demo_seed.py)，直接断言 replay 每个 step 都是 `ok=true`，并确认 replay 使用显式 permission context。
- 新增 [tests/test_demo_readiness.py](../../tests/test_demo_readiness.py)，锁住任一 step `ok=false` 时 readiness 必须失败，OpenClaw example contract 失败时也必须失败。
- 更新 [README.md](../../README.md) 顶部任务区和快速开始，把 `check_demo_readiness.py` 放到队友第一入口。
- 更新 [2026-05-07 handoff](2026-05-07-handoff.md)，把下一步指向本 handoff，避免继续泛泛重复 Phase 6 基线。
- 新增 [memory_engine/copilot/feishu_live.py](../../memory_engine/copilot/feishu_live.py)，把真实飞书测试群消息路由到 `handle_tool_request()` 和 `CopilotService`，不再走旧 Memory Engine bot handler。
- 新增 [scripts/start_copilot_feishu_live.sh](../../scripts/start_copilot_feishu_live.sh)，作为受控测试群一键启动入口：默认解析“Feishu Memory Engine 测试群”为群聊 allowlist，并把当前登录用户解析为 reviewer；不把真实 chat_id / open_id 写入仓库。
- 新增 [tests/test_copilot_feishu_live.py](../../tests/test_copilot_feishu_live.py)，覆盖 `/remember` candidate-only、`/confirm` 后 search、自然语言 prefetch、非 reviewer 拒绝、非 allowlist 群聊静默忽略和 health 不泄露真实 ID。

## 怎么运行

推荐顺序：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_copilot_health.py
python3 scripts/demo_seed.py --json-output reports/demo_replay.json
python3 scripts/check_demo_readiness.py
python3 scripts/check_demo_readiness.py --json
python3 -m unittest tests.test_demo_seed tests.test_demo_readiness
```

受控接入旧飞书测试群时运行新的 Copilot live sandbox。这个入口不是旧 Memory Engine handler：

```bash
python3 scripts/check_openclaw_version.py
scripts/start_copilot_feishu_live.sh
```

测试群里按这个顺序做真实消息验收：

```text
@Feishu Memory Engine bot /health
@Feishu Memory Engine bot /remember 决定：Copilot live sandbox 验收口径是 candidate 先确认再 active
@Feishu Memory Engine bot /confirm <candidate_id>
@Feishu Memory Engine bot Copilot live sandbox 验收口径是什么？
```

更完整的 Ralph 验收继续跑：

```bash
git diff --check
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_permissions tests.test_copilot_schemas tests.test_copilot_tools tests.test_copilot_healthcheck
python3 -m unittest tests.test_copilot_feishu_live
python3 -m unittest tests.test_copilot_cognee_adapter tests.test_copilot_prefetch tests.test_copilot_heartbeat
python3 -m unittest discover tests
ollama ps
```

## 当前验证结果

已运行并通过：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_copilot_health.py
python3 scripts/demo_seed.py --json-output reports/demo_replay.json
python3 scripts/check_demo_readiness.py
python3 scripts/check_demo_readiness.py --json
python3 -m unittest tests.test_demo_seed tests.test_demo_readiness
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools tests.test_copilot_healthcheck
python3 -m unittest tests.test_copilot_feishu_live
python3 -m unittest tests.test_copilot_tools tests.test_copilot_permissions tests.test_copilot_prefetch
```

结果摘要：

- OpenClaw version OK：`2026.4.24`。
- Phase 6 healthcheck：`ok=true`，`fail=0`；storage schema 和 embedding provider 仍是明确 warning，不假装迁移或 live embedding 已完成。
- Demo replay：5 个 step 全部 `ok=true`，并写出 `reports/demo_replay.json`。
- Demo readiness：`ok=true`；`openclaw_version=pass`，`phase6_healthcheck=pass`，`demo_replay=pass`，`provider_config=warning`。
- Feishu 测试群 live sandbox：真实旧测试群已完成 `/health`、`/remember`、`/confirm`、普通 @ 提问四步；`/remember` 先创建 candidate，`/confirm` 后才 active，普通提问走 `memory.search` 并返回 request_id、trace_id 和 hybrid retrieval trace。
- 安全边界：监听器只处理 allowlist 群聊；health 回复只显示 allowlist/reviewer 是否已配置，不展示真实 chat_id 或 open_id；本地启动脚本不再默认 reviewer `*`。

## 飞书共享看板

已同步一条程俊豪任务记录，并已用 `lark-cli base +record-list` 读回确认：

- 任务描述：`2026-04-28 程俊豪：旧飞书测试群接入新 Memory Copilot live sandbox`
- 状态：`已完成`
- 完成情况-程俊豪：`true`
- 指派给：`程俊豪`
- 备注：旧测试群已完成 `/health`、`/remember` candidate、`/confirm` active、普通 @ 提问 `memory.search`；验证包含 OpenClaw `2026.4.24`、`compileall`、46 个 Copilot/live/prefetch/permission/tool 单测和 `git diff --check`；仍不是生产部署、全量飞书空间接入或 productized live。

如果 lark-cli 权限失败，不能声称已同步；最终回复和看板备注替代入口里要写失败命令和错误摘要。

## 还没做

- 没有生产部署。
- 已有受控旧测试群 live sandbox，但还没有生产推送、全量飞书空间接入或长期运行部署。
- 没有完整 audit table migration。
- 没有完整多租户运维后台。
- 没有把 Cognee/Ollama live embedding 验证变成默认门禁；provider 当前仍是 configuration-only 检查。
- 没有把 replay / dry-run / demo readiness / 测试群 live sandbox 宣称为 productized live。

## 下一步从哪里开始

1. 继续 Phase 7 Product QA：做 no-overclaim claim audit，检查 README、runbook、benchmark report、whitepaper 是否都没有把 replay/dry-run 写成 live。
2. 如果要打磨 provider live check，先从 [scripts/check_embedding_provider.py](../../scripts/check_embedding_provider.py) 开始，运行后必须执行 `ollama ps` 并清理本项目模型。
3. 如果要继续接真实飞书证据，从 [memory_engine/copilot/feishu_live.py](../../memory_engine/copilot/feishu_live.py) 和 [scripts/start_copilot_feishu_live.sh](../../scripts/start_copilot_feishu_live.sh) 开始；继续保留 allowlist、candidate-only、permission fail-closed 和 `CopilotService` 统一入口。
