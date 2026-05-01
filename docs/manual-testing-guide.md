# Feishu Memory Copilot 手动测试指南

日期：2026-04-29  
适用人群：项目负责人、评委演示负责人、队友复核、后续接手维护者  
范围：把自动测试里“人看不到”的结果，转成可以手动执行、截图、记录和复盘的验收流程。

## 先看这个

这份文档不是生产上线 runbook。它只用于验证当前 demo / sandbox / pre-production 能力：

- 本地 Copilot Core 是否健康。
- OpenClaw `fmc_*` 工具是否可见、可调用。
- 受控 Feishu DM 是否能进入 OpenClaw websocket，并完成一次 `fmc_memory_search` allow-path。
- 真实 Feishu 来源是否仍然只进入 candidate，不会自动 active。
- 权限缺失或畸形时是否 fail closed。
- 审计、告警和 evidence 是否能被人工读回。

进入手动测试前，先记住当前代码边界：

- `scripts/start_copilot_feishu_live.sh` 默认跑的是 allowlist 测试群的 Copilot lark-cli sandbox，不是全量 Feishu workspace 监听。
- 不在 allowlist 的 chat 会被直接忽略。
- allowlist 群里，非 `@Bot` 消息会做静默 candidate probe，但默认不回群消息；`@Bot` / 私聊才是主动交互路径。
- 问句不会因为命中“部署 / 负责人 / 截止”这类主题词就自动变成 candidate。
- OpenClaw websocket 下的受控 DM 验收，是另一条入口；不要把它和 `copilot-feishu listen` 的测试群入口混成一条链路。

不能把本指南的通过结果写成：

- 生产部署已完成。
- 全量接入飞书 workspace。
- 真实 Feishu DM 已稳定覆盖全部 `fmc_*` / `memory.*` 工具。
- 多租户企业后台、生产级监控或 productized live 长期运行已完成。

## 手动测试记录表

每次手动测试先复制这张表到本地笔记或飞书文档。不要把真实 `chat_id`、`open_id`、token、app secret、`.env`、真实私聊截图提交到仓库。

| 字段 | 填写 |
|---|---|
| 测试日期 |  |
| 测试人 |  |
| 当前 commit |  |
| OpenClaw 版本 |  |
| 测试入口 | 本地 / OpenClaw Agent / Feishu DM / Feishu API source |
| 是否单监听 | 是 / 否 |
| 通过用例 |  |
| 失败用例 |  |
| 失败摘要 |  |
| 是否有截图 | 是 / 否 |
| 是否包含敏感信息 | 否；如果是，不能外发 |
| 最终结论 | 通过 / 部分通过 / 不通过 |

## 0. 开始前检查

在仓库根目录执行：

```bash
git status --short
git log -1 --oneline
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
ollama ps
```

人工判断：

| 检查项 | 通过标准 | 失败处理 |
|---|---|---|
| 工作区 | `git status --short` 没有和本次测试无关的改动 | 先记录，不要提交测试产生的临时文件 |
| 最新提交 | 能看到当前 commit hash | 写进测试记录表 |
| OpenClaw 版本 | `OpenClaw version OK: 2026.4.24` | 不要升级 OpenClaw；先停止测试 |
| harness | `ok=true`，无 failures | 先修文档/入口规则，不继续扩测 |
| Ollama | 没有本项目模型残留，或测试后可清理 | 测试后再次 `ollama ps` |

## 1. 本地产品主路径可见性

目的：不用飞书也能看到产品主路径是否可复现。

执行：

```bash
python3 scripts/prepare_clean_demo_db.py --source-db data/memory.sqlite --output-db data/demo_clean.sqlite --force --json
python3 scripts/demo_seed.py --db-path data/demo_clean.sqlite --json-output reports/demo_replay.json
python3 scripts/check_demo_readiness.py --json
```

人工打开：

```text
reports/demo_replay.json
docs/judge-10-minute-experience.md
docs/demo-runbook.md
docs/benchmark-report.md
```

通过标准：

- `demo_seed.py` 输出中 `production_feishu_write=false`。
- `prepare_clean_demo_db.py` 返回 `ok=true`，`source_db_modified=false`，且 output DB 没有带入 `feishu_group_policies` 或非 `demo_seed` source type。
- replay 里能看到 5 个主要步骤：搜索当前结论、版本解释、prefetch、候选/确认、提醒候选。
- `check_demo_readiness.py --json` 返回 `ok=true`。
- 搜索结果包含固定样例：`ap-shanghai` 和 `--canary`。
- 文档里明确写着 demo / sandbox / pre-production，不写 production live。

截图建议：

- README 顶部项目状态。
- `demo_seed.py` compact 输出。
- `reports/demo_replay.json` 中搜索结果的 `current_value`、`evidence`、`trace`。

## 2. OpenClaw 工具注册和本地 Agent 调用

目的：确认 OpenClaw Agent 能看到 first-class `fmc_*` 工具，不只是通过脚本间接跑。

执行：

```bash
openclaw plugins inspect feishu-memory-copilot --json
python3 scripts/check_feishu_dm_routing.py --json
```

可选人工测试：

```bash
openclaw agent --agent main --message "请调用 fmc_memory_search 搜索 Copilot live sandbox 验收口径，只返回 request_id、trace_id、permission_decision。" --json
```

通过标准：

- plugin inspect 能看到 7 个工具：
  - `fmc_memory_search`
  - `fmc_memory_create_candidate`
  - `fmc_memory_confirm`
  - `fmc_memory_reject`
  - `fmc_memory_explain_versions`
  - `fmc_memory_prefetch`
  - `fmc_heartbeat_review_due`
- `check_feishu_dm_routing.py --json` 返回 `ok=true`。
- Agent 本地调用结果里能看到工具调用摘要，且没有绕过 `handle_tool_request()` / `CopilotService`。

失败判断：

| 现象 | 说明 | 处理 |
|---|---|---|
| 工具列表缺 `fmc_*` | 插件未安装、未启用或 OpenClaw 配置不对 | 先按 handoff 复核 plugin 状态，不改业务代码 |
| 工具调用被权限拒绝 | 如果是 missing / malformed permission，这是正确 fail-closed | 不要为了演示加宽松默认权限 |
| LLM 长时间无响应 | 可能是 provider 卡住 | 记录 run id；必要时按本机 OpenClaw provider fallback 策略切换，不写 API key 到仓库 |

## 3. Feishu websocket 单监听检查

目的：真实飞书测试前确认同一个 bot 只有一个监听入口，避免 OpenClaw websocket、lark-cli sandbox 和 legacy listener 抢消息。

执行：

```bash
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
openclaw channels status --probe --json
```

通过标准：

- singleton 检查通过。
- `openclaw channels status --probe --json` 显示 Feishu channel/account running。
- 如果 `openclaw health --json` 的总览字段显示 Feishu running 不一致，只记录为已知 warning，以 channels status 和 gateway 日志为准。

失败处理：

- 不要同时启动 `python3 -m memory_engine feishu listen`。
- 不要同时启动 `python3 -m memory_engine copilot-feishu listen`。
- 不要同时启动直接的 `lark-cli event +subscribe`。
- 先停掉冲突 listener，再重新执行 singleton 检查。

## 4. 受控 Feishu DM 搜索测试

目的：让你在飞书里亲眼看到真实 DM -> OpenClaw websocket -> `fmc_memory_search` -> `CopilotService` 的 allow-path。

前置条件：

- 已通过“Feishu websocket 单监听检查”。
- 测试 bot 已在受控私聊或测试群可用。
- 不会截取或提交真实 `chat_id`、`open_id`、message id、token。

发送给 Feishu bot：

```text
请直接调用 fmc_memory_search 搜索 "Copilot live sandbox 验收口径"，
scope=project:feishu_ai_challenge，top_k=5。
current_context.permission 使用 demo tenant/org、reviewer actor，
request_id=req_manual_dm_search_YYYYMMDD_HHMM，
trace_id=trace_manual_dm_search_YYYYMMDD_HHMM。
只返回结论、命中数、request_id、trace_id、permission_decision。
```

把 `YYYYMMDD_HHMM` 换成测试时间，例如 `20260429_1530`。

通过标准：

- 飞书机器人有回复。
- 回复包含 `通过`、`ok=true` 或同等成功摘要。
- 回复包含命中数，期望 top_k=5 时命中 5 条，或明确说明实际命中数。
- 回复包含你发送的 `request_id`。
- 回复包含你发送的 `trace_id`。
- 回复包含 `permission_decision=allow` 或 `allow/scope_access_granted`。
- 回复不要包含真实 token、真实用户 ID、真实群 ID。

失败处理：

| 现象 | 先看什么 | 判断 | 下一步 |
|---|---|---|---|
| bot 没回复 | OpenClaw gateway 日志、session 是否生成 | DM 可能没进当前 websocket，或 LLM dispatch 卡住 | 不启动第二个 listener；先记录时间和 request_id |
| 回复说 `missing_permission_context` | 工具已进入，但权限缺失 | fail-closed 正常 | 修 prompt / adapter 注入，不放宽权限 |
| 回复说 `malformed_permission_context` | `current_context.permission` 格式不对 | fail-closed 正常 | 检查 JSON-string 兼容和字段结构 |
| 回复没有 request_id / trace_id | 用户答案可见，但工程审计字段不足 | 可读性通过，排障性不足 | 查 session / audit，并记录缺口 |
| MiMo / RightCode 卡住 | provider 或 LLM 调用慢 | 不是 Copilot 权限逻辑失败 | 记录 provider、run id 和时间 |

## 5. 真实飞书互动卡片点击测试

目的：确认 Feishu live interactive 回复不是“文本伪卡片”，而是真实可点击的候选审核卡；点击动作仍按当前操作者权限进入 `handle_tool_request()` / `CopilotService`，不会把按钮里的旧上下文当成权限来源。

前置条件：

- 已通过“Feishu websocket 单监听检查”或 Copilot lark-cli sandbox 单监听检查。
- `FEISHU_CARD_MODE` 保持默认 `interactive`，或显式设置为 `interactive`。
- 当前操作者在本机环境的 `COPILOT_FEISHU_REVIEWER_OPEN_IDS` 中，或测试环境明确使用 `*`。
- 不截图提交真实 `chat_id`、`open_id`、message id、token。

发送给受控测试群或测试私聊 bot：

```text
群聊：@Bot /remember 决定：飞书记忆审核卡片必须可点击确认，点击后仍走 CopilotService。
私聊：/remember 决定：飞书记忆审核卡片必须可点击确认，点击后仍走 CopilotService。
```

通过标准：

- 飞书机器人回复的是 interactive card，不只是纯文本。
- 卡片标题是待确认记忆，能看到状态、审核状态、主题、新值、来源、证据、风险、冲突和审计详情。
- reviewer 能看到 4 个按钮：`确认保存`、`拒绝候选`、`要求补证据`、`标记过期`。
- 非 reviewer 或 permission denied 情况下不展示审核按钮，也不展示未授权 evidence/current_value。
- 点击按钮后，回复或审计里能看到对应动作：
  - `确认保存` -> `memory.confirm`，候选变 active。
  - `拒绝候选` -> `memory.reject`，候选变 rejected。
  - `要求补证据` -> `memory.needs_evidence`，候选变 needs_evidence。
  - `标记过期` -> `memory.expire`，候选变 expired。
- 按钮 payload 只应包含 action 和 candidate id；权限上下文必须由当前点击 operator 重新生成。

建议每次只测一个新候选，避免同一候选先确认后再测试其他状态。测试完读回审计：

```bash
python3 scripts/query_audit_events.py --json --limit 20
```

失败处理：

| 现象 | 判断 | 下一步 |
|---|---|---|
| 只发出纯文本，没有卡片 | 可能 `FEISHU_CARD_MODE=text` 或 card 发送失败后 fallback | 检查启动环境和 lark-cli card 发送错误，不宣称真实可点击路径通过 |
| 点击后 permission denied | 如果操作者不是 reviewer，这是正确 fail-closed | 复核 reviewer allowlist；不要把 `current_context` 塞进按钮 value 规避权限 |
| 点击确认但 candidate 没变 active | 状态流转或 candidate 定位失败 | 用审计 request_id / trace_id 查 `memory.confirm` 结果 |
| 非 reviewer 也能确认 | 严重权限问题 | 停止真实飞书测试，优先查 `feishu_live.py`、`feishu_events.py`、`permissions.py` |

本阶段只证明受控 sandbox/pre-production 可点击卡片路径，不代表生产级 card action 长期运行。

## 6. Candidate-only 手动测试

目的：确认真实飞书来源或拟真实来源不会直接写 active memory。

可用入口：

```text
/task <受控任务 ID 或测试资源占位>
/meeting <受控妙记 ID 或测试资源占位>
/bitable <受控 Bitable record ID 或测试资源占位>
```

如果你暂时没有真实资源 ID，不要伪造“live 成功”。先用本地 replay 或 dry-run 说明入口存在，等有受控资源再测。

通过标准：

- 权限 preflight 在真实 fetch 前执行。
- source_context mismatch 时 fail closed。
- Feishu API 失败时不创建 candidate。
- 成功读取的内容只进入 candidate，不自动 active。
- candidate 有 source metadata、evidence quote、request_id、trace_id。

人工读回：

```bash
python3 scripts/query_audit_events.py --summary --json
python3 scripts/query_audit_events.py --event-type ingestion_failed --json --limit 20
```

通过标准：

- 失败路径能在审计中看到 `ingestion_failed` 或 permission denied。
- 审计输出不包含 raw token、secret、完整真实私聊文本。

## 7. 权限 fail-closed 负面测试

目的：确认系统不会因为演示需要而泄露未授权记忆。

本地执行：

```bash
python3 -m unittest tests.test_copilot_permissions -v
```

手动 Feishu / OpenClaw 输入建议：

```text
请调用 fmc_memory_search 搜索 Copilot live sandbox 验收口径，但不要提供 current_context.permission。
```

通过标准：

- 系统拒绝执行或返回 permission denied。
- 错误原因是 `missing_permission_context`、`malformed_permission_context`、`scope_mismatch`、`tenant_mismatch` 或类似 fail-closed reason。
- 回复不包含未授权 `current_value`、evidence quote 或 raw events。

失败处理：

- 如果缺权限仍返回了具体记忆内容，立即停止真实飞书测试。
- 记录 request_id / trace_id。
- 优先检查 `memory_engine/copilot/permissions.py`、`memory_engine/copilot/service.py`、`agent_adapters/openclaw/plugin/`。

## 8. 审计和告警手动读回

目的：把自动化里的“审计通过”变成人能检查的 evidence。

执行：

```bash
python3 scripts/query_audit_events.py --summary --json
python3 scripts/query_audit_events.py --json --limit 20
python3 scripts/check_audit_alerts.py --json
python3 scripts/check_copilot_health.py --json
```

通过标准：

- `query_audit_events.py --summary --json` 能返回审计事件总览。
- 最近事件里能看到 permission denied、candidate/review、ingestion failure、embedding fallback 等事件类型中的至少一类。
- `check_audit_alerts.py` 如果在真实 DB 上返回非 0，要先读 JSON；critical alert 是业务告警，不一定是脚本坏了。
- `check_copilot_health.py --json` 的 `openclaw_websocket` 默认可以是 `skipped`；只有显式加 `--openclaw-websocket-check` 时才纳入 live staging 检查。

人工记录：

| 字段 | 填写 |
|---|---|
| audit event 总数 |  |
| 最近 request_id |  |
| 最近 trace_id |  |
| 是否有 critical alert |  |
| critical 是否可解释 |  |
| 是否泄露敏感信息 |  |

## 9. Review surface / Bitable 手动测试

目的：确认 review surface 是展示和操作入口，不是绕过 `CopilotService` 的事实源。

手动检查：

- Candidate Review 行有稳定 `sync_key`。
- 非 dry-run 写入前会查已有记录。
- 命中已有记录时更新，而不是重复创建。
- 写入成功后能读回确认。
- confirm / reject 最终仍走 `handle_tool_request()` / `CopilotService`。

本地验证：

```bash
python3 -m unittest tests.test_bitable_sync tests.test_feishu_interactive_cards -v
```

通过标准：

- 非 reviewer 操作被拒绝。
- candidate 状态不会被 Bitable 直接改坏。
- permission denied 时不展示未授权 evidence/current_value。

## 10. 手动截图清单

建议截图只保留脱敏内容：

| 截图 | 内容 | 不能出现 |
|---|---|---|
| README 当前状态 | MVP / Demo / Pre-production 已完成，production 未完成 | `.env`、token |
| 本地 replay | `reports/demo_replay.json` 搜索结果 | 真实用户 ID |
| OpenClaw 工具列表 | 7 个 `fmc_*` 工具 | 本机密钥 |
| Feishu DM 回复 | request_id、trace_id、permission_decision、命中数 | 真实 chat_id、open_id |
| Feishu 互动卡片 | 脱敏后的候选审核卡、按钮和点击后状态 | 真实 chat_id、open_id、候选原始敏感文本 |
| 审计 summary | event count、reason code summary | raw 私聊全文 |
| permission denied | fail-closed 错误和 request_id | 未授权 evidence/current_value |
| candidate-only | candidate 状态和 evidence quote 脱敏版本 | 真实敏感原文 |

截图文件不要提交到仓库，除非已经确认完全脱敏并放在明确允许的交付目录。

## 11. 最终人工验收口径

如果以上通过，可以说：

- 当前 demo / sandbox / pre-production 手动测试通过。
- OpenClaw `fmc_*` 工具可见，核心路径能进入 `CopilotService`。
- 受控 Feishu DM 可以做一次 `fmc_memory_search` allow-path 验收。
- 受控 Feishu interactive card 可以点击候选审核动作，并按当前 operator 权限进入 CopilotService。
- 权限缺失或畸形会 fail closed。
- 真实 Feishu 来源仍遵守 candidate-only。
- 审计和告警可以人工读回。

仍然不能说：

- 已生产部署。
- 已全量接入飞书 workspace。
- 已完成 productized live 长期运行。
- 已完成生产级 Prometheus/Grafana。
- 已完成多租户企业后台。
- 真实 Feishu DM 已稳定覆盖所有工具动作。
- 真实飞书 card action 已完成生产级长期运行。

## 12. 测试后收尾

执行：

```bash
git status --short
git diff --check
ollama ps
```

如果跑过真实 embedding / Cognee / Ollama 相关检查，确认没有本项目模型残留。  
如果生成了 `reports/*.json`、日志、截图或包含真实 ID 的临时文件，不要提交。  
如果手动测试发现新失败，用“测试日期 + request_id + trace_id + 失败现象 + 截图是否脱敏”记录到新的 handoff 或 issue。
