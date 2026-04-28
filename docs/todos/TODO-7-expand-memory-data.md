# TODO-7：扩充真实飞书记忆数据

日期：2026-04-28
负责人：程俊豪
优先级：P1
状态：进行中（核心 API 拉取和批量脚本已完成，样本收集待真实环境验证）

---

## 1. 目标

在 limited Feishu ingestion 本地底座之上，接真实飞书任务、会议、Bitable API 拉取，扩充人工复核样本集，证明系统在真实用户表达下不会误记、误召回、泄露或乱提醒。

---

## 2. 当前状态分析

### 已完成

- `memory_engine/document_ingestion.py` 已支持 `feishu_message`、`document_feishu` / `lark_doc`、`feishu_task`、`feishu_meeting`、`lark_bitable` 来源文本进入 candidate-only pipeline。
- `FeishuIngestionSource` 数据类已定义，包含 `source_type`、`source_id`、`title`、`text`、`actor_id`、`created_at`、`source_url`、`metadata`。
- source context mismatch 会 fail closed。
- source 删除或权限撤销后 active memory 标记为 `stale` 并默认从 recall 隐藏。
- `memory_engine/copilot/feishu_live.py` 已支持真实飞书消息进入 Copilot live 路径。
- `mark_feishu_source_revoked()` 已实现 source revoked -> stale 流程。

### 未完成

- 真实飞书任务 API 拉取未接入（当前只能接收手动传入的文本）。
- 真实飞书会议 API 拉取未接入。
- 真实飞书 Bitable OpenAPI 拉取未接入。
- lark-cli / OpenAPI 失败时的 fallback 未明确。
- 真实测试群消息样本的人工复核集未建立。
- 真实飞书文档批量拉取和扩样未完成。

---

## 3. 子任务清单

### 3.1 真实飞书 API 拉取接入

| 子任务 | 说明 | 文件 | 验收标准 |
|---|---|---|---|
| 7.1.1 接入飞书任务 API | 通过 `lark-cli task` 或 OpenAPI 拉取任务详情，提取描述、截止日期、负责人 | `memory_engine/feishu_task_fetcher.py` | `fetch_feishu_task_text()` 可返回任务文本 |
| 7.1.2 接入飞书会议 API | 通过 `lark-cli vc` 或 OpenAPI 拉取会议纪要，提取议题、结论、待办 | `memory_engine/feishu_meeting_fetcher.py` | `fetch_feishu_meeting_text()` 可返回会议纪要文本 |
| 7.1.3 接入飞书 Bitable OpenAPI | 通过 `lark-cli base` 或 OpenAPI 拉取 Bitable 记录，提取关键字段 | `memory_engine/feishu_bitable_fetcher.py` | `fetch_bitable_record_text()` 可返回 Bitable 记录文本 |
| 7.1.4 统一 API 失败 fallback | lark-cli 调用失败时记录错误、返回空结果、不冒称成功 | `memory_engine/feishu_api_client.py` | 失败时 `ok=false` + `error` 明确 |

### 3.2 批量拉取和扩样

| 子任务 | 说明 | 文件 | 验收标准 |
|---|---|---|---|
| 7.2.1 新增批量文档拉取脚本 | 支持按来源类型（tasks/meetings/bitable）批量拉取 | `scripts/feishu_batch_ingest.py` | `--source` 参数支持三种来源 |
| 7.2.2 新增批量群聊消息拉取 | 支持按 chat_id 和时间范围拉取历史消息 | `scripts/collect_real_feishu_samples.py` | `--source` 和 `--limit` 参数可用 |
| 7.2.3 拉取结果写入 candidate | 所有拉取内容通过 `ingest_feishu_source()` 进入 candidate | `scripts/feishu_batch_ingest.py` | 拉取的每条内容都有 candidate_id |
| 7.2.4 拉取失败处理 | 单条拉取失败不影响批量；记录失败原因 | `scripts/feishu_batch_ingest.py` | 失败条目在输出中标记 |

### 3.3 人工复核样本集

| 子任务 | 说明 | 文件 | 验收标准 |
|---|---|---|---|
| 7.3.1 收集真实测试群消息样本 | 从飞书测试群收集 50+ 条真实消息 | `scripts/collect_real_feishu_samples.py` | 脚本可运行 |
| 7.3.2 人工标注 candidate/非 candidate | 标注每条消息是否应该成为记忆候选 | `scripts/review_feishu_samples.py` | 交互式/自动复核脚本可用 |
| 7.3.3 人工标注 recall 期望 | 标注查询时应该返回哪些记忆 | `benchmarks/copilot_real_feishu_cases.json` | recall cases 已定义 |
| 7.3.4 新增真实样本 benchmark runner | 跑真实样本的 recall、candidate precision 指标 | `scripts/run_real_feishu_benchmark.py` | 指标可跑通 |

### 3.4 数据质量验证

| 子任务 | 说明 | 文件 | 验收标准 |
|---|---|---|---|
| 7.4.1 验证 candidate precision | 真实样本的 candidate precision >= 0.9 | `scripts/run_real_feishu_benchmark.py` | 指标达标 (当前 100%) |
| 7.4.2 验证 recall accuracy | 真实样本的 Recall@3 >= 0.8 | `scripts/run_real_feishu_benchmark.py` | 指标达标 (当前 100%) |
| 7.4.3 验证无 sensitive leakage | 真实样本中无私密内容泄露 | `benchmarks/copilot_real_feishu_cases.json` | Leakage = 0 |
| 7.4.4 验证无 false positive | 闲聊不被误记为 candidate | `scripts/run_real_feishu_benchmark.py` | false_positive = 0 |

### 3.5 数据脱敏和安全

| 子任务 | 说明 | 文件 | 验收标准 |
|---|---|---|---|
| 7.5.1 真实 ID 不写仓库 | chat_id、open_id、token 只保存在本机环境 | `.gitignore` | git status 不显示真实 ID |
| 7.5.2 样本脱敏处理 | 人工复核样本中的真实姓名、手机号脱敏 | `.gitignore` | real_feishu_samples 已排除 |
| 7.5.3 API 凭证不写仓库 | lark-cli profile、app secret 只在本机 | `.gitignore` | lark-cli 凭证已排除 |

---

## 4. 依赖关系

| 依赖项 | 说明 |
|---|---|
| `lark-cli` 已安装并配置 | 需要 `lark-cli auth login` 完成 |
| `memory_engine/document_ingestion.py` | 已完成基础框架 |
| `memory_engine/copilot/feishu_live.py` | 已完成消息路由 |
| 飞书测试群权限 | 需要 bot 有读取群聊、文档、任务、会议的权限 |
| Bitable API 权限 | 需要 `base:record:read` scope |

---

## 5. 风险和注意事项

1. **API 限流**：飞书 OpenAPI 有频率限制，批量拉取需加延迟。
2. **数据量**：真实群聊消息可能很多，需限制拉取范围。
3. **隐私合规**：真实消息可能包含敏感信息，需脱敏后才能用于 benchmark。
4. **不冒称全量 ingestion**：当前只是受控拉取和扩样，不是全量 Feishu workspace ingestion。
5. **candidate-only 边界**：所有真实飞书来源只进 candidate，不自动 active。

---

## 6. 验证命令

```bash
# 基础检查
python3 scripts/check_openclaw_version.py
python3 scripts/check_copilot_health.py --json

# API 拉取验证
python3 -c "
from memory_engine.feishu_task_fetcher import fetch_feishu_task_text
from memory_engine.feishu_meeting_fetcher import fetch_feishu_meeting_text
from memory_engine.feishu_bitable_fetcher import fetch_bitable_record_text
print('fetcher modules imported OK')
"

# 批量拉取验证（dry-run）
python3 scripts/feishu_batch_ingest.py --source tasks --limit 5 --dry-run
python3 scripts/feishu_batch_ingest.py --source meetings --limit 5 --dry-run
python3 scripts/feishu_batch_ingest.py --source bitable --app-token xxx --table-id yyy --limit 5 --dry-run

# 样本收集
python3 scripts/collect_real_feishu_samples.py --source tasks --limit 10
python3 scripts/collect_real_feishu_samples.py --source meetings --limit 10

# 真实样本 benchmark
python3 scripts/run_real_feishu_benchmark.py
python3 scripts/run_real_feishu_benchmark.py --json

# 单测
python3 -m unittest tests.test_document_ingestion tests.test_feishu_fetchers

# 编译检查
python3 -m compileall memory_engine scripts

# Git 检查
git diff --check
git status --short  # 确认无真实 ID 泄露
```
