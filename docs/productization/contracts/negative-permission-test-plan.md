# Negative Permission Test Plan：Feishu Memory Copilot Phase 1

日期：2026-05-07
状态：Phase 1 contract freeze 已完成；第一批反例已实现到 `tests/test_copilot_permissions.py`（commit `b6b17b4`）
适用范围：后续 `tests/test_copilot_permissions.py`、OpenClaw examples、Feishu review surface tests、Product QA。

## 1. 目标

把“不能越权召回、不能越权确认、不能泄漏 evidence、不能静默通过缺失权限上下文”转成可执行反例。

## 2. Canonical Fixtures

建议最小 fixture：

| Fixture | tenant | organization | visibility | owner | status |
|---|---|---|---|---|---|
| `mem_team_a` | `tenant:a` | `org:a` | `team` | `u_owner_a` | active |
| `mem_private_a` | `tenant:a` | `org:a` | `private` | `u_owner_a` | active |
| `mem_org_a` | `tenant:a` | `org:a` | `organization` | `u_owner_a` | active |
| `mem_team_b` | `tenant:b` | `org:b` | `team` | `u_owner_b` | active |
| `cand_review_a` | `tenant:a` | `org:a` | `team` | `u_author_a` | candidate |
| `mem_revoked_a` | `tenant:a` | `org:a` | `team` | `u_owner_a` | stale/redacted |

Actors：

| Actor | tenant | organization | roles |
|---|---|---|---|
| `actor_owner_a` | `tenant:a` | `org:a` | member, owner |
| `actor_reviewer_a` | `tenant:a` | `org:a` | member, reviewer |
| `actor_member_a` | `tenant:a` | `org:a` | member |
| `actor_other_org` | `tenant:a` | `org:other` | member |
| `actor_tenant_b` | `tenant:b` | `org:b` | member |
| `actor_missing_context` | missing | missing | missing |

## 3. Required Negative Cases

| Case ID | Action | Setup | Expected |
|---|---|---|---|
| `perm_tenant_mismatch_search` | `memory.search` | `actor_tenant_b` reads `mem_team_a` | `permission_denied`, no evidence |
| `perm_org_mismatch_search` | `memory.search` | `actor_other_org` reads `mem_team_a` | `permission_denied` |
| `perm_private_non_owner` | `memory.search` | `actor_member_a` reads `mem_private_a` | deny or redact according to policy |
| `perm_missing_context_search` | `memory.search` | no `current_context.permission` | `permission_denied`, reason `missing_permission_context` |
| `perm_member_confirm_denied` | `memory.confirm` | `actor_member_a` confirms `cand_review_a` | candidate remains candidate |
| `perm_member_reject_denied` | `memory.reject` | `actor_member_a` rejects `cand_review_a` | candidate remains unchanged |
| `perm_explain_versions_leakage` | `memory.explain_versions` | unauthorized actor asks old values/evidence | deny or redact old value/evidence |
| `perm_prefetch_overreach` | `memory.prefetch` | actor asks task context across tenant/org | denied/empty pack |
| `perm_heartbeat_sensitive` | heartbeat | reminder contains secret-like text | suppressed/redacted; no push |
| `perm_source_context_mismatch` | any read | chat/doc restricted memory requested elsewhere | deny/redact |
| `perm_revoked_source_evidence` | search/explain | source deleted/revoked | evidence withheld or memory stale |

## 3.1 Implemented Negative Cases（2026-05-07）

已实现并通过：

- missing `current_context.permission` fails closed：`memory.search`、`memory.explain_versions`、`memory.prefetch`。
- malformed permission fails closed。
- tenant mismatch search denied。
- organization mismatch search denied。
- private visibility non-owner denied。
- member confirm/reject denied。
- member `create_candidate(auto_confirm=True)` 不能绕过 reviewer / owner / admin。
- 真实 Feishu document ingestion 缺失/畸形 permission 时在 fetch 前 fail closed。

仍待后续补齐：

- heartbeat sensitive reminder 的完整权限反例矩阵。
- revoked source evidence 的 redaction / stale 行为。
- 每个工具独立覆盖 requested_action mismatch、workspace mismatch 的机械矩阵。

## 4. Assertions

每个 case 至少断言：

- `ok` is false or result is redacted as expected。
- `error.details.reason_code` 或 audit reason_code 稳定。
- denied response 不含 `current_value` 明文或 evidence quote。
- target candidate/memory state 未被误改。
- audit event 记录 actor、action、decision、reason_code。

## 5. OpenClaw Example Requirements

Phase 2 前至少新增三类 examples：

1. allow：同 tenant/org reviewer 搜索或确认。
2. deny：tenant mismatch search。
3. redact：evidence source restricted 的 explain_versions。

## 6. Acceptance Criteria

- 反例覆盖 read、mutate、prefetch、heartbeat、review action。
- 缺权限上下文不再通过。
- confirm/reject 不再只依赖 `actor_id` 字符串。
- Product QA 能用这些 case 证明 Sensitive Reminder Leakage Rate = 0 和 unauthorized recall = 0。
