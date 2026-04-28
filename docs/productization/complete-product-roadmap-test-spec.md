# Test Spec：Feishu Memory Copilot 完整产品路线验收规格

> **状态更新（2026-04-28）**：2026-05-05 及以前的 implementation plan 已经全部完成，不再作为后续执行入口；Phase A storage/audit 本地迁移已完成；Phase B 真实 OpenClaw Agent Runtime 受控证据已完成，见 `docs/productization/openclaw-runtime-evidence.md`；Phase D live embedding gate 已完成，见 `docs/productization/phase-d-live-embedding-handoff.md`；Phase E no-overclaim 审查已完成，见 `docs/productization/phase-e-no-overclaim-handoff.md`；后续 first-class OpenClaw 原生工具注册和 Agent 本地 `fmc_*` 工具调用验证已补本机证据，见 `docs/productization/first-class-openclaw-tools-handoff.md` 和 `docs/productization/handoffs/feishu-dm-routing-handoff.md`；OpenClaw Feishu websocket running 本机 staging 证据已补，见 `docs/productization/openclaw-feishu-websocket-handoff.md`；真实权限映射和 limited Feishu ingestion 本地底座已补，见 `docs/productization/real-feishu-permission-mapping-handoff.md` 和 `docs/productization/limited-feishu-ingestion-handoff.md`。后续若继续推进，优先补真实 Feishu DM live E2E、真实 API 拉取扩样和 productized live；当前不宣称这些已经完成。

Metadata:
- Workflow: `$ralplan --consensus --direct .omx/specs/deep-interview-complete-product-roadmap.md`（仓库可追踪副本）
- Date: 2026-04-27
- Paired PRD: `docs/productization/complete-product-roadmap-prd.md`
- Consensus: Planner revision -> Architect `APPROVE` -> Critic `APPROVE`
- Planning boundary: 原始 `$ralplan` 只定义测试和验收、不实现代码；本仓库副本作为后续 `$ralph` / `$team` 的验收输入。

---

## 1. Test Strategy

验收分四层：

1. **Artifact checks**：检查 PRD/RFC/README/runbook/whitepaper/benchmark report 是否描述一致，尤其不夸大 live。
2. **Unit tests**：锁住 schema、permission、governance、payload、heartbeat、migration 的最小契约。
3. **Integration/E2E tests**：验证 OpenClaw -> Copilot service、Feishu review surface -> service、limited ingestion -> candidate pipeline。
4. **Observability/QA checks**：验证 trace、audit、healthcheck、counters、安全日志和 claim audit。

所有产品化代码执行前仍必须遵循仓库现有基本验证：

```bash
python3 scripts/check_openclaw_version.py
git diff --check
```

触达 Python 代码、OpenClaw schema、benchmark runner 或测试数据时追加：

```bash
python3 -m compileall memory_engine scripts
python3 -m unittest discover tests
```

触达已存在 Copilot benchmark 时追加对应 runner；不要虚构尚未实现的命令。

---

## 2. Phase-by-phase Exit Criteria

### Phase 0：Submission Freeze Preservation

Required artifacts:
- README 顶部入口
- `docs/demo-runbook.md`
- `docs/benchmark-report.md`
- `docs/memory-definition-and-architecture-whitepaper.md`
- 录屏/截图/submission checklist（若存在）

Checks:
- [ ] 2026-05-06 / 2026-05-07 初赛提交材料没有被产品化任务覆盖。
- [ ] 所有 live claim 有标签：schema demo / dry-run / replay / OpenClaw live / Feishu live ingestion。
- [ ] README、runbook、report、whitepaper 没有互相矛盾。

Commands:

```bash
python3 scripts/check_openclaw_version.py
git diff --check
```

Fallback:
- 如果 OpenClaw runtime 不可用，只允许保留 schema demo / replay / dry-run 叙述，不能写成 live。

### Phase 0.5：Productization Baseline RFC

Required artifacts:
- `docs/productization/complete-product-roadmap-prd.md`
- `docs/productization/complete-product-roadmap-test-spec.md`
- Phase 1 standalone contract files：
  - [storage-contract.md](contracts/storage-contract.md)
  - [permission-contract.md](contracts/permission-contract.md)
  - [openclaw-payload-contract.md](contracts/openclaw-payload-contract.md)
  - [audit-observability-contract.md](contracts/audit-observability-contract.md)
  - [migration-rfc.md](contracts/migration-rfc.md)
  - [negative-permission-test-plan.md](contracts/negative-permission-test-plan.md)

Checks:
- [ ] RFC 写清 dry-run、seed/local service real call、limited ingestion、productized live 区别。
- [ ] Phase 0-7 gate 全部可测试。
- [ ] 不写代码、不接真实 Feishu API。

Commands:

```bash
git diff --check
```

### Phase 1：Storage + Permission Contract Freeze

Required artifacts:
- [storage contract](contracts/storage-contract.md)
- [permission contract](contracts/permission-contract.md)
- [OpenClaw payload contract](contracts/openclaw-payload-contract.md)
- [audit/observability contract](contracts/audit-observability-contract.md)
- [migration RFC](contracts/migration-rfc.md)
- [negative permission test plan](contracts/negative-permission-test-plan.md)

Checks:
- [x] `tenant_id` / `organization_id` / `visibility_policy` 字段语义冻结。
- [x] service permission decision contract 冻结。
- [x] OpenClaw payload 决定：首版使用 `current_context.permission`。
- [x] 所有 tool/action fail-closed 行为写入权限矩阵。
- [x] Negative cases 进入测试计划。
- [x] Architect/Critic 无 blocker。

2026-05-07 补充：Phase 2 权限前置实现已把第一批 negative cases 转成 [tests/test_copilot_permissions.py](../../tests/test_copilot_permissions.py)，并更新 schema/service/permission 代码。2026-04-28 Phase A 已补齐 storage migration 和 audit table；Phase B 真实 OpenClaw Agent runtime 受控证据也已完成；后续 first-class OpenClaw 原生工具注册、Agent 本地 `fmc_*` 工具调用验证、Feishu websocket staging running 证据、真实权限映射和 limited Feishu ingestion 本地底座已补；仍不宣称 production live 或真实 Feishu DM 已稳定进入本项目 first-class `fmc_*` / `memory.*` tool routing live E2E。

Commands:

Docs-only freeze:

```bash
python3 scripts/check_openclaw_version.py
git diff --check
```

进入代码实现并触达 Python/schema/test 后追加：

```bash
python3 scripts/check_openclaw_version.py
git diff --check
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools
```

Pass/fail:
- Pass：contract freeze 文档完成；进入实现后，schema/tests 反映冻结字段，missing permission context fail closed。
- Fail：仍只做 scope/allowed_scopes 级别权限，或 confirm/reject/explain 不受权限矩阵约束。

Fallback:
- 若 storage migration 未完成，不进入 Phase 2/3/4；保留 seed/local proof。

### Phase 2：OpenClaw Live Bridge

Required artifacts:
- OpenClaw tool schema 与 Phase 1 payload 对齐
- seed/local service bridge example
- trace/request id output

Checks:
- [x] OpenClaw 真实调用本地/seed Copilot service。
- [x] response 含 permission decision summary。
- [x] missing/malformed permission context fail closed。
- [x] 文档明确不是 Feishu live ingestion。

当前状态：permission fail-closed 和 OpenClaw live bridge 已完成，见 commit `cb21bc7`。Phase B runtime evidence 已补：OpenClaw Agent run `b252f11e-b49d-495c-a14f-0b823a888a5e` 通过 `exec` 调用证据脚本，三条 Copilot flow 全部 `ok=true`。后续 first-class OpenClaw 原生工具注册、Agent 本地 `fmc_*` 工具调用验证和 Feishu websocket staging running 证据已补。本阶段仍不是生产 Feishu live ingestion；真实 Feishu DM 到本项目 first-class `fmc_*` / `memory.*` tool routing live E2E 仍需继续验收。

Commands:

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_permissions tests.test_copilot_schemas tests.test_copilot_tools tests.test_document_ingestion
```

Fallback:
- OpenClaw runtime 不可用时，仅可展示 schema demo 或 replay，并标注 runtime not verified。

### Phase 3：Feishu UI / Review Surface

Required artifacts:
- review card / Bitable / doc page payload
- approve/reject service call path
- audit event output

Checks:
- [x] UI 只消费 permission-aware service output。
- [x] UI 不直接写 active/rejected/superseded。
- [x] non-reviewer approve/reject 被拒绝。
- [x] Bitable/card payload 不包含未授权 evidence。

Commands:

```bash
python3 -m unittest tests.test_feishu_interactive_cards tests.test_bitable_sync
```

Fallback:
- Feishu/lark-cli 写入失败时使用 dry-run payload，但必须标注未写真实空间。

### Phase 4：Limited Feishu Ingestion

Required artifacts:
- 指定测试群/文档/Bitable 行来源说明
- ingestion -> candidate 证据
- audit trail

Checks:
- [x] 本地底座支持真实 Feishu source 文本进入 candidate，不自动 active。
- [x] candidate 有 evidence quote/source metadata。
- [x] source context mismatch 在创建 candidate 前 fail closed。
- [x] source 权限撤销时 recall 降级/隐藏/标记 stale。
- [ ] 真实任务、会议、Bitable API 拉取和失败 fallback 仍需后续接入。

Commands:

```bash
python3 -m unittest tests.test_document_ingestion tests.test_copilot_governance
```

Fallback:
- Feishu API/lark-cli 权限失败时，保持 fixture/dry-run，不能声称 limited ingestion 通过。

### Phase 5：Heartbeat Controlled Reminder

Required artifacts:
- heartbeat candidate output
- cooldown decision
- permission/redaction decision

Checks:
- [ ] reminder candidate 有 reason/evidence/target actor/cooldown。
- [ ] sensitive content 被拦截或脱敏。
- [ ] permission deny 时 withheld/redacted。
- [ ] reminder 不自动 active。

Commands:

```bash
python3 -m unittest tests.test_copilot_heartbeat
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
```

Fallback:
- 只做 dry-run/card payload，不做正式推送。

### Phase 6：Deployability + Healthcheck

Required artifacts:
- healthcheck command/runbook
- configuration checklist
- smoke test output

Checks:
- [ ] OpenClaw version、Copilot service import、storage schema、Cognee adapter、embedding provider、permission contract 都可检查。
- [ ] schema version visible in healthcheck。
- [ ] provider 不可用时清楚报错或 fallback。
- [ ] 运行 Cognee/Ollama 验证后执行 `ollama ps` 并清理项目模型。

Commands:

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_live_embedding_gate.py --json
python3 scripts/check_embedding_provider.py
ollama ps
```

Fallback:
- 无 Ollama/Cognee 时降级到 repository fallback，并记录 Not-tested。

### Phase 7：Product QA

Required artifacts:
- Product QA report
- claim audit list
- release readiness summary

Checks:
- [ ] README/runbook/whitepaper/report/examples 中所有 live claim 分类一致。
- [ ] Negative permission cases 通过。
- [ ] Candidate-only ingestion 通过。
- [ ] Review surface 不越权。
- [ ] Logs 不泄漏 token/secret/private raw memory。

Commands:

```bash
python3 scripts/check_openclaw_version.py
git diff --check
python3 -m compileall memory_engine scripts
python3 -m unittest discover tests
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine benchmark run benchmarks/day7_anti_interference.json --markdown-output docs/benchmark-report.md
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_layer_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
```

Fallback:
- 尚未实现的 runner 不得假装通过；写入 Not-tested 和 blocker/fallback。

---

## 3. Unit Test Matrix

| Area | Required cases |
|---|---|
| Schema validation | `tenant_id`、`organization_id`、`visibility_policy`、evidence fields、audit fields、ToolError |
| Permission context | missing context fail closed、malformed actor deny、missing tenant/org deny、unknown visibility deny |
| Permission decision | allow same tenant/org；deny tenant mismatch；deny organization mismatch；deny private non-owner；deny source context mismatch |
| Review permissions | candidate approve/reject without reviewer role deny；owner/reviewer allow |
| Governance | candidate -> active only through review；candidate -> rejected；active -> superseded；archived 不默认召回；revoked source -> stale/hidden/redacted |
| OpenClaw payload | required permission fields present；compat current_context.permission；missing actor fails closed；response includes trace/request id；error format stable |
| Heartbeat | cooldown；reminder candidate only；permission-aware filtering；sensitive redaction |
| Migration | default tenant/org/visibility；idempotent；schema version；old benchmark compatibility |

---

## 4. Negative Permission Test Plan

1. **tenant mismatch**：A tenant actor 请求 B tenant memory，必须 deny 且不返回 evidence。
2. **organization mismatch**：同 tenant 不同 organization，visibility 不允许跨组织时 deny。
3. **private non-owner**：非 owner 请求 private memory，deny 或字段脱敏。
4. **review without role**：普通 member confirm/reject candidate，deny，candidate 不变。
5. **deleted/revoked source**：source 删除或权限撤销后 recall 降级/隐藏/标记 stale。
6. **missing permission context**：OpenClaw/Feishu UI 缺 actor/tenant/org，fail closed。
7. **source context mismatch**：chat/doc restricted memory 在其他上下文请求，deny 或 redacted。
8. **explain_versions leakage**：旧版本/evidence 对无权限 actor 不可见。
9. **prefetch overreach**：prefetch 不得带出无权限 memory。
10. **heartbeat leakage**：敏感 reminder 对无权限 actor withheld/redacted。

---

## 5. Integration Test Matrix

| Flow | Required checks |
|---|---|
| OpenClaw adapter -> Copilot service | seed/local search；permission allow；permission deny；tool error propagation；trace id |
| Service -> storage | active search；candidate creation；evidence attachment；audit write；schema version |
| Service -> Cognee adapter | adapter available；adapter unavailable fallback；no direct Cognee import outside adapter |
| Feishu review surface -> service | card loads permission-aware output；approve allowed reviewer；approve denied member；reject candidate；UI no direct mutation |
| Bitable/card payload | consumes service output only；redacted fields stay redacted；state_mutation 不绕过 service |
| Limited ingestion -> candidate | Feishu source -> evidence -> candidate；no auto active；audit recorded |
| Failure fallback | lark-cli/Feishu API permission denied；OpenClaw runtime unavailable；Cognee unavailable；embedding unavailable |

---

## 6. E2E Scenarios

1. **OpenClaw seed/local historical decision search**
   - User invokes `memory.search` through OpenClaw.
   - Service returns active memory, evidence, permission summary, trace id.
   - Missing permission context variant returns `permission_denied`.

2. **OpenClaw seed/local prefetch with permission-aware context**
   - User starts a task.
   - `memory.prefetch` returns compact context pack with relevant memories, risks/deadlines, evidence and trace summary.
   - Prefetch excludes unauthorized memories.

3. **Candidate review lifecycle**
   - `memory.create_candidate` creates candidate with evidence.
   - reviewer `memory.confirm` makes it active.
   - conflict candidate supersedes old active version.
   - `memory.reject` keeps rejected out of default recall.

4. **Limited Feishu ingestion**
   - Selected Feishu source is ingested.
   - It becomes candidate only.
   - Review surface displays service-approved fields.
   - Active happens only after confirm.

5. **Heartbeat reminder candidate**
   - Heartbeat generates reminder candidate with reason/evidence.
   - Cooldown prevents repeated noise.
   - Sensitive or unauthorized content is redacted/withheld.

6. **Failure-mode journey**
   - missing permission context -> fail closed。
   - tenant mismatch -> deny。
   - Cognee unavailable -> repository fallback / clear error。
   - lark-cli unavailable -> dry-run only。
   - Feishu write denied -> no claim of live write。
   - migration already applied -> idempotent success。

---

## 7. Observability Checks

| Area | Required output |
|---|---|
| Traceability | `request_id`, `trace_id`, actor, action, source_context |
| Audit | permission decisions, review actions, ingestion actions, redacted fields, denial reason_code |
| Healthcheck | OpenClaw version, service import, storage schema/version, Cognee adapter status, embedding provider status, permission contract loaded |
| Metrics/counters | search success/failure, permission allow/deny, candidate created/approved/rejected, reminders generated/suppressed, redaction count |
| Safe logs | no token/secret leakage, no raw private memory in denial logs, no redacted plaintext |
| OpenClaw trace | tool call payload label, response label, error format, runtime vs schema-demo distinction |
| Benchmark failures | failure category, expected vs actual, evidence missing, stale/superseded leakage |

---

## 8. No-overclaim Claim Audit

必须逐文件检查：

- `README.md`
- `docs/demo-runbook.md`
- `docs/benchmark-report.md`
- `docs/memory-definition-and-architecture-whitepaper.md`
- `agent_adapters/openclaw/examples/*`
- Feishu card/Bitable 文案
- submission checklist / recording script

Audit rules:

1. Phase 2 文档不得把 seed/local OpenClaw bridge 称为 “Feishu live ingestion”。
2. Feishu ingestion 未到 Phase 4 exit gate 前不得称为完成。
3. UI/Bitable/card 必须描述为 review surface，不是 source of truth。
4. 真实飞书 ingestion 必须写 candidate-only。
5. Dry-run/replay/live labels 在 README、runbook、whitepaper、benchmark report、submission checklist 中一致。
6. 未实现 live ability 必须写 Not-tested / future work，不得伪装成已完成。

---

## 9. Team Verification Path

`$team` 只允许在 Phase 1 Contract Freeze Gate 通过后启动。Team 退出前必须证明：

1. Contract tests first：schema、payload、permission decision contract 通过。
2. Permission negative cases second：tenant/org/private/reviewer/source mismatch 全部 fail closed。
3. OpenClaw seed/local bridge third：runtime tool call 到 service 有 trace 和 permission summary。
4. Feishu review surface fourth：UI/card/Bitable 只消费 service output。
5. Limited ingestion last：真实 Feishu source 只进入 candidate，不自动 active。

Ralph 接手 Team 后必须复核：
- `python3 scripts/check_openclaw_version.py`
- `git diff --check`
- 相关 unit/integration/e2e commands
- no-overclaim audit
- Ollama cleanup if embedding/Cognee tests ran

---

## 10. Final Approval Status

Critic verdict: `APPROVE`。

Mandatory conditions already applied in this file:
- Phase-by-phase exit criteria。
- Unit / integration / e2e / observability test matrix。
- service-action permission matrix in paired PRD。
- migration compatibility tests。
- no-overclaim verification。
- Team Contract Freeze Gate。

Planning workflow stops here unless user later invokes `$ralph` or `$team` with these plan artifacts.
