# 生产存储、索引和迁移方案 Handoff

日期：2026-04-28
状态：后期打磨 P1 已完成本地迁移入口和上线试点方案；仍不是生产数据库部署。

## 先看这个

1. 今天做的是后期打磨 P1 第 4 项：把已经有的本地 SQLite schema / audit table 补成可检查、可重复执行、可交接的迁移流程。
2. 我接下来从 [launch-polish-todo.md](launch-polish-todo.md) 的第 5 项继续：扩大真实 Feishu ingestion 范围，但仍必须 candidate-only（待确认记忆，不自动生效）。
3. 交付物是迁移检查模块、迁移脚本、healthcheck 的索引/审计状态、合同文档和本 handoff。
4. 判断做对：`scripts/migrate_copilot_storage.py --dry-run --json` 能报告待迁移项但不改库；`--apply --json` 可重复执行；`scripts/backup_copilot_storage.py --json` 能生成带 manifest 的 SQLite staging 备份并可 verify / restore-to；healthcheck 能看到 schema version、index status、audit status。
5. 遇到问题记录：数据库路径、dry-run JSON、apply JSON、回滚入口、是否有真实飞书监听仍在写入。

## 本阶段做了什么

- 新增 `memory_engine/storage_migration.py`：提供 `inspect_copilot_storage()` 和 `apply_copilot_storage_migration()`，统一检查 schema version、缺失列、缺失表、缺失索引、需要补默认 tenant / organization / visibility 的行数，以及审计状态。
- 新增 `scripts/migrate_copilot_storage.py`：支持 `--dry-run` 和 `--apply`，并可用 `--json` 输出给 handoff 或看板备注。
- 新增 `memory_engine/storage_backup.py` 和 `scripts/backup_copilot_storage.py`：支持 SQLite staging backup、verify 和 restore-to，生成 `.manifest.json`，恢复覆盖必须显式 `--force`。
- 更新 `memory_engine/copilot/healthcheck.py`：`storage_schema` 现在包含 `index_status` 和 `audit_status`，能报告索引缺失、审计事件数量、权限拒绝数量和遮挡数量。
- 新增 `tests/test_copilot_storage_migration.py`：覆盖 dry-run 不修改旧库、apply 可重复执行、产品化索引存在。
- 新增 `tests/test_storage_backup.py`：覆盖备份、校验、恢复和拒绝隐式覆盖。
- 更新 `tests/test_copilot_healthcheck.py`：锁住 healthcheck 必须报告索引和审计状态。

## 生产 DB 选择和边界

- 当前仓库默认仍使用本地 SQLite，适合 demo、pre-production、本机 staging 和小规模试点前验证。
- 上线试点建议选择托管 PostgreSQL 作为生产 DB，原因是备份、恢复、并发写入、审计查询、权限索引和长期运维更稳。
- 本阶段没有把代码切到 PostgreSQL，也没有部署生产数据库；迁移脚本只保证 SQLite 事实源可检查、可重复迁移、可回滚到备份。
- 真实 Feishu ingestion 扩大前，先跑 dry-run；只有 dry-run 没有缺失结构和缺失索引，才允许进入受控 apply 或新测试库。

## 索引职责

- 结构化索引：`idx_memories_tenant_org_scope_status` 和 `idx_memories_visibility_status` 负责 tenant / organization / visibility / status 过滤，避免越权或 stale 结果进入当前答案。
- 来源索引：`idx_evidence_source` 负责按来源类型和来源事件追溯 evidence。
- 审计索引：`idx_audit_request_trace` 负责按 request_id / trace_id 复盘一次 tool call。
- 全文索引：本阶段仍由现有 keyword / retrieval 层承担，不新增 SQLite FTS5（全文搜索索引）；后续如果扩真实样本再评估。
- 向量索引：本阶段仍由 curated memory embedding / Cognee adapter 路径承担，不把 raw events 全量向量化。

## 备份、恢复和数据清理

- 备份：迁移真实数据库前运行 `python3 scripts/backup_copilot_storage.py --db-path data/memory.sqlite --backup-dir data/backups --json`；备份会使用 SQLite backup API、运行 integrity check、检查 Copilot schema/index/audit readiness，并写 `.manifest.json`。
- 恢复：迁移失败时停止 Feishu ingestion / OpenClaw websocket 写入入口，先 `--verify-backup`，再 `--restore-backup ... --restore-to ... --force` 恢复 SQLite；不要自动 DROP 新列或审计表。
- 审计保留：`memory_audit_events` 至少保留最近 90 天；提交材料和看板只写统计、request_id、trace_id，不写 token、secret 或 raw private memory。
- 数据删除：来源撤权或删除时先标记 source revoked / stale，recall 降级或隐藏；不要直接物理删除 evidence，除非后续产品策略明确要求。

## 验收证据

已运行：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/migrate_copilot_storage.py --dry-run --json
python3 scripts/backup_copilot_storage.py --db-path data/memory.sqlite --backup-dir data/backups --json
python3 scripts/check_copilot_health.py --json
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_healthcheck tests.test_copilot_permissions tests.test_copilot_storage_migration tests.test_storage_backup
git diff --check
ollama ps
```

## 下一步

下一阶段执行 [launch-polish-todo.md](launch-polish-todo.md) 第 5 项：扩大真实 Feishu ingestion 范围。

必须保持：

- 所有真实来源只进入 candidate，不自动 active。
- source metadata、evidence quote、去重策略和权限 gate 都要明确。
- lark-cli / OpenAPI 失败时不能冒称 live 成功。
- source 删除或权限撤销后，recall 要降级、隐藏或标记 stale。
