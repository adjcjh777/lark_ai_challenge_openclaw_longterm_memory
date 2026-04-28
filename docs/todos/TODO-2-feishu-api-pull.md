# TODO-2: 接真实 Feishu API 拉取和扩充样本

日期：2026-04-28
优先级：P0（比赛核心竞争力）
状态：✅ 已完成

---

## 1. 目标

将飞书任务（Task）、会议（Meeting）、多维表格（Bitable）的真实 API 拉取接入 `memory_engine/document_ingestion.py` 的 candidate-only pipeline，使这些来源的真实数据能够：
1. 通过飞书 OpenAPI（经 `lark-cli`）拉取原始文本
2. 进入 `ingest_feishu_source()` 的 candidate 流程
3. 保留完整的 permission gate、source context validation、audit trace
4. 所有来源仍只进入 candidate，不自动 active

---

## 2. 当前状态分析

### 2.1 已有能力

| 来源类型 | source_type 标识 | 本地底座 | 真实 API | 说明 |
|---|---|---|---|---|
| 飞书消息 | `feishu_message` | ✅ | ✅（事件订阅） | `feishu_live.py` 通过 `lark-cli event +subscribe` 接收 |
| 飞书文档 | `document_feishu` / `lark_doc` | ✅ | ✅ | `fetch_feishu_document_text()` 通过 `lark-cli docs +fetch` 拉取 |
| 飞书任务 | `feishu_task` | ✅ | ❌ | 只有本地 fixture，无真实 API 调用 |
| 飞书会议 | `feishu_meeting` | ✅ | ❌ | 只有本地 fixture，无真实 API 调用 |
| 多维表格 | `lark_bitable` | ✅ | ❌ | `bitable_sync.py` 只做**写入** Bitable，不做读取 |

### 2.2 关键架构约束

**入口函数**：`ingest_feishu_source()`（document_ingestion.py:104）

**调用链**：
```
FeishuIngestionSource
  → check_scope_access()          # 权限门控
  → _check_limited_source_context() # source context 验证
  → extract_candidate_quotes()    # 提取候选文本
  → CopilotService.create_candidate() # 进入 candidate pipeline
  → 返回 candidate_id + trace
```

**已定义的 source metadata 字段**（schemas.py:44-58）：
- `source_task_id` — 飞书任务 ID
- `source_meeting_id` — 飞书会议 ID
- `source_bitable_app_token` / `source_bitable_table_id` / `source_bitable_record_id` — Bitable 三元组

**已有的 source context 映射**（document_ingestion.py:550-558）：
- `feishu_task` → `task_id`
- `feishu_meeting` → `meeting_id`
- `lark_bitable` → `bitable_record_id`

### 2.3 缺失部分

1. **任务 API 适配器**：没有从飞书任务 API 拉取任务详情（标题、描述、子任务、截止时间、负责人等）的实现
2. **会议 API 适配器**：没有从飞书会议/妙记 API 拉取会议纪要（总结、待办、章节、逐字稿）的实现
3. **Bitable 读取适配器**：`bitable_sync.py` 只做写入；没有从 Bitable 拉取记录文本的实现
4. **失败 fallback**：API 调用失败时的处理策略未定义（不能冒称成功）
5. **样本扩充**：每类来源的真实人工复核样本不足 10 条

---

## 3. 子任务清单

### 3.1 子任务 A：飞书任务 API 拉取

**目标**：实现从飞书任务 OpenAPI 拉取任务详情，提取文本进入 candidate pipeline

**lark-cli 命令参考**：
```bash
# 获取任务详情
lark-cli task +get-task --task-id <task_id>

# 获取任务列表（可按时间范围过滤）
lark-cli task +get-my-tasks --page-size 50
```

**需要新增的文件/函数**：
- `memory_engine/feishu_task_fetcher.py`（新文件）

**函数签名**：
```python
def fetch_feishu_task_text(
    task_id: str,
    *,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> FeishuIngestionSource:
    """从飞书任务 API 拉取任务详情，构造 FeishuIngestionSource。"""

def list_feishu_tasks(
    *,
    page_size: int = 50,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> list[dict[str, Any]]:
    """列出当前用户的任务列表，用于批量拉取。"""
```

**文本提取策略**：
- 任务标题 → subject
- 任务描述 → 主文本
- 子任务列表 → 补充文本
- 截止时间 + 负责人 → metadata
- 合并为一段 markdown 文本送入 `extract_candidate_quotes()`

**source metadata**：
```python
FeishuIngestionSource(
    source_type="feishu_task",
    source_id=task_id,
    title=task_title,
    text=combined_markdown,
    actor_id=task_creator_id,
    source_url=f"https://feishu.cn/tasks/{task_id}",
    metadata={
        "due_at": due_timestamp,
        "assignee_id": assignee_id,
        "task_status": task_status,
    },
)
```

**验收标准**：
- [x] `fetch_feishu_task_text("task_id")` 能拉取真实任务并构造 `FeishuIngestionSource`
- [x] 拉取的文本能通过 `extract_candidate_quotes()` 提取出候选
- [x] 错误处理：task_id 不存在、权限不足、网络超时均返回明确错误

---

### 3.2 子任务 B：飞书会议/妙记 API 拉取

**目标**：从飞书妙记 API 拉取会议纪要，提取文本进入 candidate pipeline

**lark-cli 命令参考**：
```bash
# 查询妙记列表
lark-cli minutes +list --start-time <ts> --end-time <ts>

# 获取妙记详情（含 AI 总结、待办、章节）
lark-cli minutes +get --minute-token <token>

# 获取妙记 AI 产物
lark-cli minutes +get-ai-content --minute-token <token>
```

**需要新增的文件/函数**：
- `memory_engine/feishu_meeting_fetcher.py`（新文件）

**函数签名**：
```python
def fetch_feishu_meeting_text(
    minute_token: str,
    *,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> FeishuIngestionSource:
    """从飞书妙记 API 拉取会议纪要，构造 FeishuIngestionSource。"""

def list_feishu_meetings(
    *,
    start_time: str | None = None,
    end_time: str | None = None,
    page_size: int = 50,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> list[dict[str, Any]]:
    """列出妙记列表，用于批量拉取。"""
```

**文本提取策略**：
- AI 总结 → 主文本（最有价值）
- 待办事项 → 补充文本
- 章节标题 → 补充文本
- 如果 AI 产物不可用，降级使用逐字稿前 N 段
- 合并为 markdown 文本送入 `extract_candidate_quotes()`

**source metadata**：
```python
FeishuIngestionSource(
    source_type="feishu_meeting",
    source_id=minute_token,
    title=meeting_title,
    text=combined_markdown,
    actor_id=meeting_creator_id,
    source_url=f"https://feishu.cn/minutes/{minute_token}",
    metadata={
        "duration_seconds": duration,
        "participant_count": participant_count,
        "meeting_date": meeting_date,
    },
)
```

**验收标准**：
- [x] `fetch_feishu_meeting_text("minute_token")` 能拉取真实妙记并构造 `FeishuIngestionSource`
- [x] AI 总结可用时优先使用；不可用时降级到逐字稿
- [x] 错误处理：token 不存在、权限不足、妙记未结束均返回明确错误

---

### 3.3 子任务 C：Bitable 记录读取

**目标**：从飞书多维表格 API 拉取记录内容，提取文本进入 candidate pipeline

**lark-cli 命令参考**：
```bash
# 列出 Bitable 表格列表
lark-cli base +table-list --base-token <app_token>

# 列出记录
lark-cli base +record-list --base-token <app_token> --table-id <table_id> --limit 100

# 获取单条记录
lark-cli base +record-get --base-token <app_token> --table-id <table_id> --record-id <record_id>
```

**需要新增的文件/函数**：
- `memory_engine/feishu_bitable_fetcher.py`（新文件）

**函数签名**：
```python
def fetch_bitable_record_text(
    app_token: str,
    table_id: str,
    record_id: str,
    *,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> FeishuIngestionSource:
    """从 Bitable API 拉取单条记录，构造 FeishuIngestionSource。"""

def list_bitable_records(
    app_token: str,
    table_id: str,
    *,
    limit: int = 100,
    lark_cli: str = "lark-cli",
    profile: str | None = None,
    as_identity: str | None = None,
) -> list[dict[str, Any]]:
    """列出 Bitable 表格记录，用于批量拉取。"""
```

**文本提取策略**：
- 遍历记录的所有字段
- 文本类字段（text、url、选项等）拼接为可读文本
- 跳过空值和系统字段（created_by、created_at 等）
- 每条记录构造一个 `FeishuIngestionSource`

**source metadata**：
```python
FeishuIngestionSource(
    source_type="lark_bitable",
    source_id=record_id,
    title=f"Bitable Record {record_id}",
    text=fields_text,
    actor_id="bitable_fetch",
    metadata={
        "app_token": app_token,
        "table_id": table_id,
        "record_id": record_id,
        "field_names": list(field_names),
    },
)
```

**与 bitable_sync.py 的关系**：
- `bitable_sync.py` 负责**写入**（Memory Ledger → Bitable）
- 新模块负责**读取**（Bitable → candidate pipeline）
- 两者独立，不互相依赖

**验收标准**：
- [x] `fetch_bitable_record_text(...)` 能拉取真实记录并构造 `FeishuIngestionSource`
- [x] 字段拼接逻辑能处理 text、number、select、multi-select 等常见字段类型
- [x] 错误处理：app_token 不存在、table_id 不存在、record_id 不存在均返回明确错误

---

### 3.4 子任务 D：统一 API 调用层和失败 Fallback

**目标**：为所有 API 调用提供统一的失败处理机制，确保不会冒称成功

**需要新增的文件/函数**：
- `memory_engine/feishu_api_client.py`（新文件，统一 API 调用层）

**设计原则**：
1. **fail closed**：API 调用失败时返回明确错误，不创建 candidate
2. **不冒称成功**：如果 `lark-cli` 返回非零退出码或解析失败，必须视为失败
3. **区分错误类型**：
   - `permission_denied`：无权访问该资源
   - `resource_not_found`：资源不存在
   - `api_error`：API 调用失败（网络超限、服务端错误等）
   - `parse_error`：返回值解析失败

**函数签名**：
```python
@dataclass(frozen=True)
class FeishuApiResult:
    ok: bool
    data: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    raw_stdout: str = ""
    raw_stderr: str = ""
    returncode: int = 0

def run_lark_cli(
    argv: list[str],
    *,
    retries: int = 2,
    timeout_seconds: int = 30,
) -> FeishuApiResult:
    """统一的 lark-cli 调用入口，带重试和错误分类。"""
```

**Fallback 策略**：

| 错误场景 | 处理方式 |
|---|---|
| 任务/会议/Bitable 不存在 | 返回 `resource_not_found`，不创建 candidate |
| 权限不足 | 返回 `permission_denied`，不创建 candidate |
| 网络超时/限流 | 重试最多 2 次，仍失败返回 `api_error` |
| 返回值 JSON 解析失败 | 尝试作为纯文本处理；仍失败返回 `parse_error` |
| lark-cli 未安装 | 返回明确错误，提示安装 |

**验收标准**：
- [x] 所有 API 调用通过 `run_lark_cli()` 统一入口
- [x] 失败场景均有明确错误码和错误消息
- [x] 重试机制正常工作
- [x] 不会在 API 失败时创建 candidate

---

### 3.5 子任务 E：集成到 feishu_live.py 和批量拉取脚本

**目标**：将新的 API 拉取能力集成到现有系统

**需要修改的文件**：
- `memory_engine/copilot/feishu_live.py` — 新增 slash command 支持
- `scripts/feishu_batch_ingest.py`（新文件）— 批量拉取脚本

**feishu_live.py 新增命令**：
```
/task <task_id>        — 拉取指定任务进入 candidate pipeline
/meeting <minute_token> — 拉取指定会议进入 candidate pipeline
/bitable <app_token> <table_id> <record_id> — 拉取指定 Bitable 记录
```

**批量拉取脚本**：
```python
# scripts/feishu_batch_ingest.py
"""
批量从飞书来源拉取数据进入 candidate pipeline。

用法：
  python3 scripts/feishu_batch_ingest.py --source tasks --limit 50
  python3 scripts/feishu_batch_ingest.py --source meetings --start-time 2026-04-01
  python3 scripts/feishu_batch_ingest.py --source bitable --app-token xxx --table-id yyy
"""
```

**验收标准**：
- [x] `/task <task_id>` 命令在飞书群聊中可用
- [x] `/meeting <minute_token>` 命令在飞书群聊中可用
- [x] 批量拉取脚本能一次性拉取多条记录
- [x] 所有来源仍只进入 candidate，不自动 active

---

### 3.6 子任务 F：扩充人工复核样本集

**目标**：每类来源至少 10 条真实样本通过人工复核

**样本要求**：
- 每条样本必须是真实飞书数据（非合成）
- 每条样本必须经过人工 confirm 或 reject
- 记录决策理由

**样本收集流程**：
1. 从真实飞书任务中拉取 15+ 条 → 人工复核 → 保留 10+ 条
2. 从真实飞书妙记中拉取 15+ 条 → 人工复核 → 保留 10+ 条
3. 从真实 Bitable 中拉取 15+ 条 → 人工复核 → 保留 10+ 条

**样本存储**：
- 候选记忆进入 SQLite（`data/memory.sqlite`）
- 复核结果同步到 Bitable（通过 `bitable_sync.py`）
- 样本清单记录到 `benchmarks/real_feishu_samples.json`

**验收标准**：
- [ ] 飞书任务样本 10+ 条已 confirm
- [ ] 飞书会议样本 10+ 条已 confirm
- [ ] Bitable 样本 10+ 条已 confirm
- [ ] 样本覆盖不同类型（决策、截止时间、负责人、风险等）

---

## 4. 依赖关系

```
D (统一 API 层)
├── A (任务 API)
├── B (会议 API)
└── C (Bitable 读取)
    │
    ▼
E (集成到 feishu_live.py + 批量脚本)
    │
    ▼
F (扩充人工复核样本)
```

**前置条件**：
- `lark-cli` 已安装并配置（参考 `docs/reference/local-lark-cli-setup.md`）
- 飞书应用已授权相关 API scope：
  - `task:task:read` — 任务读取
  - `minutes:minutes:read` — 妙记读取
  - `bitable:app:readonly` — Bitable 读取
- 测试飞书账号有可访问的任务、会议、Bitable 数据

**并行可能性**：
- A、B、C 可以并行开发（都依赖 D）
- D 需要先完成
- E 依赖 A、B、C 全部完成
- F 依赖 E 完成后才能收集真实样本

---

## 5. 风险和注意事项

### 5.1 API 权限风险

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 飞书应用未授权 task/minutes/bitable scope | API 调用 403 | 提前在飞书开放平台确认 scope 配置 |
| 用户无权访问特定任务/会议/Bitable | 拉取失败 | 实现 permission_denied 错误处理，不创建 candidate |
| lark-cli 不支持所需的 API 命令 | 无法调用 | 先验证 lark-cli 版本和命令支持；必要时使用原生 OpenAPI |

### 5.2 数据质量风险

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 任务描述为空 | 提取不出候选 | 跳过空文本，返回 not_candidate 而非报错 |
| 会议未结束/无 AI 总结 | 拉取不到有用文本 | 降级到逐字稿；仍无内容则跳过 |
| Bitable 记录字段全部为空 | 无候选 | 同上 |

### 5.3 工程风险

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| lark-cli 版本不兼容 | 命令参数不匹配 | 在 API 客户端中做版本检查 |
| API 限流 | 批量拉取失败 | 实现退避重试（指数退避，最多 3 次） |
| 大文本超出 candidate 处理能力 | 性能问题 | 限制单条文本最大长度（如 10000 字符） |

### 5.4 边界约束（必须遵守）

- **所有真实来源仍只进入 candidate，不自动 active**
- **confirm / reject 仍必须经过 CopilotService**
- **缺失或不匹配的 permission source context 会 fail closed**
- **本轮不是生产部署，不是全量 Feishu workspace ingestion**

---

## 6. 验证命令

### 6.1 单元测试

```bash
# 运行 document_ingestion 测试（包含新来源测试）
python3 -m unittest tests.test_document_ingestion -v

# 运行 feishu_live 测试（包含新命令测试）
python3 -m unittest tests.test_copilot_feishu_live -v

# 运行所有相关测试
python3 -m unittest tests.test_document_ingestion tests.test_copilot_feishu_live tests.test_bitable_sync tests.test_copilot_schemas -v
```

### 6.2 集成验证

```bash
# 验证任务 API 拉取（替换为真实 task_id）
python3 -c "
from memory_engine.feishu_task_fetcher import fetch_feishu_task_text
source = fetch_feishu_task_text('TASK_ID_HERE')
print(f'Title: {source.title}')
print(f'Text length: {len(source.text)}')
print(f'Source type: {source.source_type}')
"

# 验证会议 API 拉取（替换为真实 minute_token）
python3 -c "
from memory_engine.feishu_meeting_fetcher import fetch_feishu_meeting_text
source = fetch_feishu_meeting_text('MINUTE_TOKEN_HERE')
print(f'Title: {source.title}')
print(f'Text length: {len(source.text)}')
"

# 验证 Bitable 记录拉取
python3 -c "
from memory_engine.feishu_bitable_fetcher import fetch_bitable_record_text
source = fetch_bitable_record_text('APP_TOKEN', 'TABLE_ID', 'RECORD_ID')
print(f'Title: {source.title}')
print(f'Text length: {len(source.text)}')
"
```

### 6.3 端到端验证

```bash
# 从任务到 candidate 的完整链路
python3 -c "
from memory_engine.db import connect, init_db
from memory_engine.repository import MemoryRepository
from memory_engine.feishu_task_fetcher import fetch_feishu_task_text
from memory_engine.document_ingestion import ingest_feishu_source
from memory_engine.copilot.permissions import demo_permission_context

conn = connect(':memory:')
init_db(conn)
repo = MemoryRepository(conn)

source = fetch_feishu_task_text('TASK_ID_HERE')
context = demo_permission_context('memory.create_candidate', 'project:feishu_ai_challenge')
result = ingest_feishu_source(repo, source, current_context=context)
print(f'OK: {result[\"ok\"]}')
print(f'Candidates: {result[\"candidate_count\"]}')
print(f'Duplicates: {result[\"duplicate_count\"]}')
"
```

### 6.4 批量拉取验证

```bash
# 批量拉取任务
python3 scripts/feishu_batch_ingest.py --source tasks --limit 10 --dry-run

# 批量拉取会议
python3 scripts/feishu_batch_ingest.py --source meetings --limit 10 --dry-run

# 批量拉取 Bitable
python3 scripts/feishu_batch_ingest.py --source bitable --app-token xxx --table-id yyy --limit 10 --dry-run
```

### 6.5 编译检查

```bash
python3 -m compileall memory_engine scripts
```

---

## 7. 预估工作量

| 子任务 | 预估时间 | 依赖 |
|---|---|---|
| D: 统一 API 层 | 2 小时 | 无 |
| A: 任务 API | 3 小时 | D |
| B: 会议 API | 3 小时 | D |
| C: Bitable 读取 | 2 小时 | D |
| E: 集成 + 批量脚本 | 3 小时 | A, B, C |
| F: 样本扩充 | 4 小时 | E |
| **总计** | **17 小时** | |

---

## 8. 完成标准

- [x] `fetch_feishu_task_text()` 能拉取真实飞书任务
- [x] `fetch_feishu_meeting_text()` 能拉取真实飞书妙记
- [x] `fetch_bitable_record_text()` 能拉取真实 Bitable 记录
- [x] 所有 API 调用失败场景有明确错误处理（不冒称成功）
- [x] feishu_live.py 支持 `/task`、`/meeting`、`/bitable` 命令
- [x] 批量拉取脚本可用
- [ ] 每类来源至少 10 条真实样本通过人工复核
- [x] 所有测试通过：`python3 -m unittest tests.test_document_ingestion tests.test_copilot_feishu_live -v`
- [x] 编译检查通过：`python3 -m compileall memory_engine scripts`
