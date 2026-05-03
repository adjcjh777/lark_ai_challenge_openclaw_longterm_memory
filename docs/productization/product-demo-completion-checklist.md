# 产品展示完成清单

日期：2026-05-02

用途：把“完整产品展示还差什么”收成一张可执行清单。本文只覆盖 demo / sandbox / pre-production 展示，不把当前状态写成生产部署、全量 Feishu workspace 接入或 productized live 长期运行。

## 1. 四件事总表

| 顺序 | 要完成的事 | 当前状态 | 完成标准 | 验证入口 |
|---|---|---|---|---|
| 1 | 修掉会让展示翻车的硬问题 | 已补本地代码和回归测试 | 跨租户不能按 ID 确认/解释别人的记忆；同 scope 同 subject 可在不同 tenant/org 并存；gateway `/enable_memory` 后的群策略能放行非 allowlist 群的静默候选识别 | `python3 -m unittest tests.test_copilot_permissions tests.test_copilot_governance tests.test_openclaw_feishu_remember_router` |
| 2 | 准备一条评委能看懂的 Demo 路线 | 已收敛为 8 步脚本 | 不要求评委复制内部 ID；能看到群策略开启、被动识别、候选审核、确认、搜索、版本解释、prefetch 和审计边界 | 本文 `2. 评委 8 步路线` |
| 3 | 补真实 Feishu / OpenClaw 证据 | 2026-05-02 受控 live evidence packet 已覆盖四类核心 Feishu/OpenClaw 证据；后续仍要继续扩样 | 不伪造 live；用同一单监听入口导出日志，并让 evidence packet 和 completion audit gate 读到 pass reason | 本文 `3. 真实证据采集` |
| 4 | 准备评委材料 | 已有入口；本文补齐最终讲法 | 10 分钟脚本、架构图、边界页、验收命令和 fallback 都能定位 | `docs/judge-10-minute-experience.md`、`docs/human-product-guide.md`、`docs/diagrams/` |

## 2. 评委 8 步路线

这条路线是现场主线。真实飞书不稳定时，回退到 `reports/demo_replay.json` 和固定文档截图，但不能把 replay 说成 live。

| 步骤 | 操作 | 评委应该看到 |
|---|---|---|
| 1 | 在受控测试群发送 `/settings` | 当前群状态、allowlist / group policy、auto-confirm policy、review delivery 和 no-overclaim 边界 |
| 2 | reviewer/admin 发送 `/enable_memory` | 群策略变成 active，`passive_memory_enabled=true`，并写 audit |
| 3 | 群里不 @ Bot 直接说：`决定：上线窗口固定为每周四下午，回滚负责人是程俊豪。` | 系统静默进入 candidate probe，不回群打扰 |
| 4 | reviewer 打开 `/review` | 私聊审核卡片或本地 gate 证据显示候选进入审核队列 |
| 5 | 点击或执行确认 | candidate 变 active，审计记录能看到 actor、request_id、trace_id、permission decision |
| 6 | 用 `fmc_memory_search` / `/recall 上线窗口` 搜索 | 返回当前 active 结论和 evidence，不返回无关 raw events |
| 7 | 再输入一条冲突更新，例如 `不对，统一改成每周五上午。` | 进入 conflict candidate；版本解释能说明旧值为什么被覆盖 |
| 8 | 用 `fmc_memory_prefetch` / `/prefetch 生成上线 checklist` | 返回 compact context pack、风险、deadline 和相关 active memory |

## 3. 真实证据采集

这一步必须用真实飞书受控账号和当前单监听入口完成，不能由本地单测代替。2026-05-02 受控 live packet 已完成一轮四类核心证据；后续 demo 前仍建议按同一流程重跑扩样。

先做只读预检：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/prepare_feishu_live_evidence_run.py --json
```

现场执行四类动作：

| 证据 | 人工动作 | 合格信号 |
|---|---|---|
| 非 @ 群消息投递 | 在目标群发送普通非 @ 企业记忆句子 | `check_feishu_passive_message_event_gate.py` 返回 `passive_group_message_seen` |
| first-class tool routing | 用真实 DM / gateway 触发 `fmc_memory_search`、`fmc_memory_create_candidate`、`fmc_memory_prefetch` | `check_feishu_dm_routing.py --event-log` 读到对应 `fmc_*` success |
| 权限负例 | 第二个非 reviewer 用户发送 `/enable_memory` | `check_feishu_permission_negative_gate.py` 返回 `non_reviewer_enable_memory_denied` |
| `/review` DM/card | reviewer 执行 `/review` 并点击一次确认或拒绝 | `check_feishu_review_delivery_gate.py --event-log` 同时看到 private review DM、card action update 和 audit |

本轮已通过的收包和总审计：

```bash
python3 scripts/check_openclaw_feishu_productization_completion.py \
  --feishu-live-evidence-packet logs/feishu-live-evidence-runs/20260502T085247Z/feishu-live-evidence-packet.json \
  --feishu-event-diagnostics logs/feishu-live-evidence-runs/20260502T085247Z/00-feishu-event-diagnostics.json \
  --cognee-long-run-evidence logs/cognee-embedding-long-run/2026-05-02-sampler/cognee-long-run-evidence.json \
  --json
```

当前结果为 `goal_complete=true`、`blockers=[]`。如果后续扩样真实日志不齐，结论只能写“本地/pre-production gate 已准备好，live 证据缺口待补”，不能写“真实飞书长期稳定运行已完成”。

2026-05-02/2026-05-03 当前 preflight 结果：

- 2026-05-02 带目标群读权限证明的 event diagnostics 通过：enabled app scopes / target group probe 可支持受控非 @ 群消息采证。
- 2026-05-03 未带目标群证明的泛化 read-only preflight 会因 schema 只列 `im:message.p2p_msg:readonly` 而 fail closed，并写出 operator checklist / remediation guide；这是为了防止换群或换环境时误采证。
- 当前看到 `openclaw-gateway`，计划 listener 应保持 `openclaw-websocket`，不要再启动 lark-cli listener 抢同一个 bot。

## 4. 评委材料入口

| 材料 | 文件 | 用法 |
|---|---|---|
| 10 分钟脚本 | `docs/judge-10-minute-experience.md` | 现场按分钟讲产品主线和 fallback |
| 人话版产品说明 | `docs/human-product-guide.md` | 解释为什么不是普通搜索，以及用户怎么用 |
| 架构图 | `docs/diagrams/system-architecture.mmd` | 讲 OpenClaw Agent -> `fmc_*` -> `CopilotService` -> governance/retrieval/audit |
| 交互流 | `docs/diagrams/product-interaction-flow.mmd` | 讲搜索、候选、确认、版本解释、prefetch |
| benchmark 证据 | `docs/benchmark-report.md` | 讲 recall、误记、冲突、prefetch、提醒等指标 |
| 当前完成边界 | `README.md`、`docs/productization/prd-completion-audit-and-gap-tasks.md` | 回答“做到哪了”和“不能说什么” |

## 5. 展示前最后检查

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
python3 scripts/check_demo_readiness.py --json
python3 -m unittest tests.test_copilot_permissions tests.test_copilot_governance tests.test_openclaw_feishu_remember_router
git diff --check
```

展示话术边界：

- 可以说：MVP / Demo / Pre-production 闭环已完成，OpenClaw first-class 工具、本地 gateway、受控飞书测试群 sandbox、本地审计治理、2026-05-02 受控 live packet 和 Cognee 本地/staging 24h+ 长跑证据都已有。
- 不能说：生产部署、全量 Feishu workspace 接入、完整多租户后台、生产级长期 embedding 服务、真实 Feishu DM 长期稳定路由或 productized live 已完成。
