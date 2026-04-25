# Day 5 Handoff

日期：2026-04-28

## 今日目标

D5 目标是完成文档 ingestion 最小闭环。优先 P0，完成后继续 P1。

P0：

- 实现 `/ingest_doc <url_or_token>` 的本地 handler 或 CLI 命令。
- 读取飞书文档纯文本，或用 `lark-cli docs +fetch` 作为第一版入口。
- 从文档中抽取候选记忆，默认保存为 `candidate`。
- 记录 evidence：文档 token、标题、摘录 quote。

P1：

- 增加 `/confirm <candidate_id>` 和 `/reject <candidate_id>` 的最小实现。
- 支持从 Markdown 文件导入，便于无飞书权限时演示。
- 增加文档 ingestion fixture。

## 已完成代码能力

- 新增 `memory_engine/document_ingestion.py`：
  - 本地 Markdown 文件读取。
  - 飞书文档 token/url 解析。
  - `lark-cli docs +fetch <token>` 纯文本读取入口。
  - 基于文档行/段落抽取候选 quote。
- 扩展 `MemoryRepository`：
  - `add_candidate(...)` 写入 `candidate` 记忆、候选版本和文档 evidence。
  - `confirm_candidate(...)` 将候选提升为 `active`。
  - `reject_candidate(...)` 将候选标记为 `rejected`。
  - `recall(...)` 返回 `document_title`、`document_token` 和 quote。
- 扩展 CLI：
  - `python3 -m memory_engine ingest-doc <url_or_token>`
  - `python3 -m memory_engine confirm <candidate_id>`
  - `python3 -m memory_engine reject <candidate_id>`
- 扩展飞书 Bot：
  - `/ingest_doc <url_or_token>`
  - `/confirm <candidate_id>`
  - `/reject <candidate_id>`
  - `/recall` 对文档来源显示 `文档《标题》/ token_or_path`。
- 新增 fixture：
  - `tests/fixtures/day5_doc_ingestion_fixture.md`
  - 内含 7 条可抽取候选和多条干扰信息。
- 新增测试：
  - `tests/test_document_ingestion.py`
  - `tests/test_feishu_day5.py`

## 演示命令

Markdown fallback 路径：

```bash
tmp_db=$(mktemp -t day5-memory.XXXXXX.sqlite)
python3 -m memory_engine --db-path "$tmp_db" ingest-doc --limit 7 tests/fixtures/day5_doc_ingestion_fixture.md
python3 -m memory_engine --db-path "$tmp_db" confirm <candidate_id>
python3 -m memory_engine --db-path "$tmp_db" recall 生产部署参数
rm -f "$tmp_db"
```

飞书 Bot dry-run/replay 可发送：

```text
@Feishu Memory Engine bot /ingest_doc tests/fixtures/day5_doc_ingestion_fixture.md
@Feishu Memory Engine bot /confirm mem_xxx
@Feishu Memory Engine bot /recall 生产部署参数
```

飞书文档权限就绪后可发送真实 token 或 URL：

```text
@Feishu Memory Engine bot /ingest_doc https://.../docx/<token>
```

底层会调用：

```bash
lark-cli docs +fetch <token>
```

## 验证结果

已通过：

```bash
python3 -m compileall memory_engine scripts
python3 -m unittest discover -s tests
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

专项验证：

- `python3 -m unittest discover -s tests -p 'test_document_ingestion.py'`：3 tests OK。
- `python3 -m unittest discover -s tests -p 'test_feishu_day5.py'`：1 test OK。
- CLI demo：从 `tests/fixtures/day5_doc_ingestion_fixture.md` 抽取 7 条 candidate，确认生产部署候选后，`recall` 返回：
  - `source_type = document_markdown`
  - `document_title = Day5 架构决策文档`
  - `quote = 决定：生产部署必须加 --canary --region cn-shanghai。`

Day 1 benchmark 仍为：

- `case_count = 10`
- `case_pass_rate = 1.0`
- `conflict_accuracy = 1.0`
- `evidence_coverage = 1.0`
- `stale_leakage_rate = 0.0`

## 队友今晚任务

1. 准备 2 份示例飞书文档：架构决策文档、项目周会纪要。
2. 每份文档埋入 5 条以上可抽取记忆，并加入 15 条以上干扰信息。
3. 用真实飞书文档 URL/token 跑一次 `/ingest_doc`；如果权限阻塞，记录 `lark-cli docs +fetch` 错误并改用 Markdown fixture。
4. 检查 Bot 回复里的候选列表是否评委能看懂，必要时调整文案。
5. 补白皮书“数据来源与证据链”段落，强调每条文档记忆都有 token/title/quote。

## 未验证项

- 尚未用真实飞书文档 token 验证 `lark-cli docs +fetch` 的权限链路。
- 当前抽取器是启发式规则，适合 Demo 文档和初赛闭环；后续如需复杂文档块结构，应接入更强的解析或人工确认 UI。
- 候选确认目前按 `candidate_id` 手动执行，尚无批量确认或卡片按钮。
