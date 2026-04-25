# Day 5 实现计划：文档 ingestion 最小闭环

日期：2026-04-28  
阶段：Day 5  
目标：在 Day 1-4 的本地 Memory Engine、飞书 Bot、Bitable 台账基础上，补齐“飞书文档或 Markdown -> 候选记忆 -> 人工确认 -> 可召回并带证据”的最小闭环。

## 1. 当前基线

已具备能力：

- 本地 CLI：`remember`、`recall`、`versions`、`benchmark run`。
- 飞书 Bot：`/remember`、`/recall`、`/versions`、`/help`、`/health`。
- SQLite 已有 `raw_events`、`memories`、`memory_versions`、`memory_evidence`，可以保存证据 quote。
- `recall` 已返回 `source_type`、`source_id`、`quote`，适合扩展文档证据链。

缺口：

- 尚无 `/ingest_doc <url_or_token>` 或 CLI 文档入口。
- 无飞书文档权限时缺少可演示的 Markdown fallback。
- 候选记忆还不能被人工确认或拒绝。

## 2. P0 范围

1. 新增文档 ingestion 模块：
   - 支持本地 Markdown 文件。
   - 支持飞书文档 token/url，经 `lark-cli docs +fetch <token>` 读取纯文本。
   - 从文档行/段落中抽取含决策、流程、偏好、规则等信号的候选 quote。
2. 新增 CLI：
   - `python3 -m memory_engine ingest-doc <url_or_token>`
3. 保存候选记忆：
   - `memories.status = candidate`
   - `memory_versions.status = candidate`
   - `memory_evidence.quote = 文档摘录`
   - `raw_events.raw_json` 记录 `document_token`、`document_title`、`quote`
4. `recall` 对已确认记忆返回文档来源，而不是只显示系统来源。

## 3. P1 范围

1. 新增 CLI：
   - `python3 -m memory_engine confirm <candidate_id>`
   - `python3 -m memory_engine reject <candidate_id>`
2. 新增飞书 Bot 命令：
   - `/ingest_doc <url_or_token>`
   - `/confirm <candidate_id>`
   - `/reject <candidate_id>`
3. 增加 Markdown fixture，覆盖至少 5 条可抽取候选和多条干扰信息。
4. 增加文档 ingestion 和飞书 Day5 handler 测试。

## 4. 不做范围

- 不引入新依赖。
- 不做生产级文档解析、OCR、表格块解析或富文本块结构保真。
- 不自动把候选全部激活，避免文档噪声直接污染 active 记忆。
- 不依赖真实飞书文档权限；飞书权限阻塞时使用 Markdown fixture 演示闭环。

## 5. 验收命令

```bash
python3 -m compileall memory_engine scripts
python3 -m unittest discover -s tests
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine --db-path /tmp/day5.sqlite ingest-doc --limit 7 tests/fixtures/day5_doc_ingestion_fixture.md
python3 -m memory_engine --db-path /tmp/day5.sqlite confirm <candidate_id>
python3 -m memory_engine --db-path /tmp/day5.sqlite recall 生产部署参数
```

验收重点：

- Markdown fixture 至少导入 5 条 candidate。
- 未确认 candidate 不会被 `recall` 命中。
- `/confirm` 后 `recall` 能返回 active 记忆。
- `recall.source` 包含文档标题、文档 token/path 和 quote。
