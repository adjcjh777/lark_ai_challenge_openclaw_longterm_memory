# Migration RFC：Scope-first -> Tenant-aware Storage

日期：2026-05-07
状态：Phase 1 contract freeze（文档冻结，待代码实现）
适用范围：后续数据库迁移脚本、repository fallback、benchmark fixture、demo seed。

## 1. 背景

当前仓库已经有可运行 MVP 和 benchmark，但底层模型仍是 `scope_type/scope_id`。完整产品要求真实 tenant / organization / visibility permission，必须做兼容迁移。

## 2. 迁移原则

1. **Idempotent**：重复执行不会重复加字段或破坏数据。
2. **Backward-compatible**：旧 Day1 fallback、existing `copilot_*` benchmark 和 demo seed 仍可跑。
3. **No destructive rewrite**：不删除旧列，不一次性迁走 legacy repository。
4. **Fail closed after contract**：迁移完成后，缺 permission context 的产品路径必须 deny。
5. **No real data committed**：真实飞书日志、数据库、token 不进入 git。

## 3. Default Values

旧数据迁移默认：

| 字段 | 默认值 | 说明 |
|---|---|---|
| `tenant_id` | `tenant:demo` | 本地 demo/benchmark 默认租户。 |
| `organization_id` | `org:demo` | 本地 demo/benchmark 默认组织。 |
| `workspace_id` | old `scope_id` | 若 scope 是 project/chat/doc，优先映射旧 scope。 |
| `visibility_policy` | `public_demo` 或 `team` | benchmark/replay 可用 `public_demo`；手动候选默认 `team`。 |
| `schema_version` | `2` | Phase 1 后目标版本。 |

## 4. Migration Steps

后续实现建议：

1. Add nullable columns to existing tables.
2. Backfill default tenant/org/visibility for existing rows.
3. Create new audit table.
4. Add indexes.
5. Run compatibility benchmark.
6. Switch product path permission check to fail-closed.
7. Keep legacy fallback scope-only path only for explicit demo/benchmark mode until later migration.

## 5. Rollback / Dry-run

迁移脚本必须支持：

```bash
python3 scripts/migrate_copilot_storage.py --dry-run
python3 scripts/migrate_copilot_storage.py --apply
```

Dry-run 输出至少包含：

- current schema version
- pending column additions
- rows needing default tenant/org/visibility
- whether audit table exists
- affected benchmark/demo rows count

Rollback：

- MVP 阶段不建议自动 drop columns。
- 如迁移失败，保留旧 columns 和 old data，产品路径降级到 seed/local demo，真实 ingestion 禁止启动。

## 6. Compatibility Tests

迁移后必须通过：

- `python3 -m memory_engine benchmark run benchmarks/day1_cases.json`
- 已存在 `copilot_*` benchmark。
- `tests.test_copilot_schemas` 和 `tests.test_copilot_tools`。
- 新增 migration idempotency test 后，重复运行 migration dry-run/apply 不应改变行数或重复列。

## 7. Acceptance Criteria

- 旧 demo 数据有 tenant/org/visibility。
- 旧 benchmark 可跑。
- schema version 可被 healthcheck 读取。
- migration failure 有明确 Not-tested / rollback 说明。
- Phase 4 limited ingestion 前必须完成 apply 或明确使用隔离测试库。
