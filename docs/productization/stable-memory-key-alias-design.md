# Stable Memory Key / Alias Design

日期：2026-05-01  
阶段：OpenClaw-native Feishu Memory Copilot 产品化设计  
来源：`deep-research-report.md` 中“稳定 memory key / alias 层”建议

## 先看这个

1. 本文是小步设计文档，不改 Python 代码、不改 schema、不声明功能已上线。
2. 当前事实源仍以 `README.md`、`docs/productization/full-copilot-next-execution-doc.md`、`docs/productization/prd-completion-audit-and-gap-tasks.md` 和当前代码为准。
3. 当前能力边界仍是 MVP / Demo / Pre-production 本地闭环与受控 Feishu sandbox；不能把本文写成生产部署、全量 Feishu workspace ingestion、productized live 或真实 DM 稳定长期路由已完成。
4. 本设计的目标是降低 `wrong_subject_normalization` 和 `stale_value_leaked` 风险，让冲突更新从“句子是否相似”升级为“是否属于同一个业务槽位的新旧值”。

## 背景问题

当前治理层创建 candidate 时会先抽取 `subject` / `normalized_subject`，再用下列近似唯一性查已有记忆：

```text
scope_type + scope_id + tenant_id + organization_id + type + normalized_subject
```

当完全匹配时，新值会进入 conflict candidate；确认后旧 active version 被 superseded，新值成为 active。这个路径已经能支撑版本链和审计，但它把“同一业务槽位”的识别压力几乎全部压在 `normalized_subject` 上。

这带来两个风险：

| 风险 | 例子 | 用户可见坏结果 | benchmark 归因 |
|---|---|---|---|
| 同槽位被拆散 | “OpenClaw 部署区域”“生产 region”“线上部署机房”没有归到同一个 subject | 新值被当成新记忆，旧值仍可能在 search / prefetch 出现 | `wrong_subject_normalization`、`stale_value_leaked` |
| 不同槽位被误合并 | “OpenClaw 负责人”和“OpenClaw 周报接收人”都被归成 “openclaw人” | 确认一个候选时错误覆盖另一类事实 | `wrong_subject_normalization`、`keyword_miss` |
| 规则名丢失 | “Bitable 写入规则”与“Benchmark 结果写回规则”混成项目级规则 | 版本解释看似有链，但链上对象不一致 | `wrong_subject_normalization` |
| 自然语言 alias 不稳定 | “截止”“ddl”“周五前”“复赛材料时间点”无法稳定挂到同一 deadline slot | 冲突检测漏报，reviewer 需要人工比对旧值 | `wrong_subject_normalization` |

因此，稳定 key 不应该替代 `normalized_subject`，而应该作为治理层的补充身份层：`normalized_subject` 继续服务自然语言召回和展示，stable key 负责重要业务槽位的冲突与版本归并。

## 设计目标

- 为高价值、易冲突的企业记忆建立稳定业务键。
- 不破坏现有 `memories.normalized_subject` 和版本链语义。
- 首版只覆盖少量业务槽位，不追求通用 ontology。
- alias 解析必须带 evidence、权限上下文和审计线索，不能绕过 `CopilotService`。
- 默认只对 curated memory 做 embedding；alias 不用于向量化 raw events。
- 所有真实 Feishu 来源仍先进入 review policy；重要、敏感或冲突内容仍停在 candidate。

## 非目标

- 不做生产级多租户管理后台。
- 不做全量 Feishu workspace alias 自动学习。
- 不把 alias 自动解析结果直接写 active memory。
- 不升级 OpenClaw，不改变 `fmc_*` / `memory.*` 工具边界。
- 不引入新的 memory substrate，也不绕过 Cognee 窄 adapter。

## Stable Memory Key 模型

建议 stable key 用结构化、可解释、可人工复核的字符串，而不是 hash-only ID。首版格式：

```text
memkey:v1:{tenant_id}:{organization_id}:{scope_type}:{scope_id}:{project_slug}:{slot_type}:{slot_name}
```

字段说明：

| 字段 | 含义 | 示例 |
|---|---|---|
| `project_slug` | 项目或工作流对象，来自明确项目名或受控 alias | `openclaw-feishu-memory-copilot` |
| `slot_type` | 业务槽位类型 | `rule`、`owner`、`deadline`、`deploy_region`、`weekly_report_recipient` |
| `slot_name` | 槽位内细分名称 | `bitable-write-path`、`demo-submission`、`production-deploy` |

首版不要求所有记忆都有 stable key。只有命中高价值槽位且 confidence 足够时才附加；其他内容继续使用现有 `normalized_subject` 路径。

## 首批业务槽位

| slot_type | stable key 例子 | 适合原因 | 典型 alias |
|---|---|---|---|
| `rule` | `...:rule:bitable-write-path` | 流程规则经常被改口，旧规则泄漏风险高 | “Bitable 写入规则”“写回飞书表的方式”“benchmark 结果回填规则” |
| `owner` | `...:owner:productization` | 负责人变化必须冲突更新，不应和接收人混淆 | “负责人”“owner”“谁来跟”“由谁处理” |
| `deadline` | `...:deadline:demo-submission` | 截止时间有多轮改口，容易旧值泄漏 | “ddl”“截止”“提交时间”“周五前” |
| `deploy_region` | `...:deploy_region:production-deploy` | 部署区域是当前 benchmark 中典型冲突槽位 | “region”“部署区域”“机房”“生产部署放哪” |
| `weekly_report_recipient` | `...:weekly_report_recipient:productization` | 接收人、负责人、reviewer 是不同槽位，必须拆开 | “周报发给谁”“接收人”“同步对象” |
| `review_policy` | `...:rule:feishu-review-policy` | 自动确认与人工审核边界必须稳定 | “review policy”“审核规则”“哪些要人工确认” |

这些槽位都应该保持项目级限定。只有“项目 + 槽位类型 + 槽位名”同时足够明确时，才生成 stable key；否则保留 candidate 并提示补证据或补上下文。

## Alias 最小落地

首版建议用只读 seed + 本地 ledger 增量表，不直接重构现有 `memories` 表。

### 逻辑表 1：`memory_key_aliases`

```text
alias_id
tenant_id
organization_id
scope_type
scope_id
project_slug
slot_type
slot_name
alias_text
normalized_alias
confidence
source_type
source_id
created_by
created_at
status              # active | candidate | rejected | superseded
```

用途：

- 把自然语言表达映射到 stable key。
- 支持人工确认 alias 是否有效。
- 记录 alias 自身证据，不把 alias 当作 active memory 结论。

### 逻辑表 2：`memory_key_bindings`

```text
binding_id
tenant_id
organization_id
memory_id
stable_key
project_slug
slot_type
slot_name
binding_source      # exact_alias | reviewer_confirmed | benchmark_seed | migration_backfill
confidence
created_at
status              # active | candidate | rejected | superseded
```

用途：

- 把现有 `memory_id` 绑定到 stable key。
- 不要求立刻给 `memories` 增列；实现时可以先通过 adapter 查询绑定表。
- 后续如需 schema migration，再考虑把 `stable_key` 做成可索引字段。

## 最小解析流程

### 1. Candidate 创建前

```text
text + source + current_context.permission
  -> extract_memory()
  -> normalized_subject
  -> alias_resolver.resolve(project, slot, alias)
  -> stable_key? + confidence + explanation
```

如果解析出 stable key，则治理层查 existing 时优先用：

```text
tenant_id + organization_id + scope_type + scope_id + stable_key
```

如果没有 stable key，则保持当前：

```text
tenant_id + organization_id + scope_type + scope_id + type + normalized_subject
```

### 2. Conflict detection

优先级建议：

1. stable key exact match：直接按同业务槽位冲突处理。
2. stable key candidate match：创建 conflict candidate，但标记 `alias_confidence_review_required`。
3. normalized subject match：沿用当前逻辑。
4. 无匹配：创建普通 candidate。

冲突卡片和 review inbox 中应展示：

```text
业务槽位：OpenClaw / production deploy / deploy_region
alias 命中：“线上部署机房” -> deploy_region
旧值：cn-shanghai
新值：ap-shanghai
建议动作：人工确认合并
```

### 3. Confirm / Reject

- confirm conflict candidate 时，active version 仍由现有 governance 状态机处理。
- stable key binding 随 confirm 写入或激活。
- reject candidate 时，相关 candidate alias / binding 也应 rejected 或保持 pending，不得继续影响默认冲突检测。
- undo review 时，binding 状态必须可回滚，避免 alias 残留导致后续误合并。

## 与 Retrieval 的关系

stable key 不替代 retrieval rerank。它提供更稳定的结构化过滤与解释：

- search / prefetch 默认仍只返回 active memory。
- 查询中命中 alias 时，可把 stable key 作为 structured hint，提高同槽位 active memory 的排序。
- `why_ranked` 后续可新增 `stable_key_match`、`alias_match`、`slot_type` 字段，解释为什么当前值排在旧值前。
- superseded 旧值仍只能出现在 `memory.explain_versions`，不能进入默认 search / prefetch 当前答案。

## 与 Benchmark Failure Taxonomy 的关系

当前 benchmark 已把下列失败类型暴露出来：

| failure_type | stable key / alias 的修复方向 |
|---|---|
| `wrong_subject_normalization` | 对高价值槽位增加 stable key exact match，减少自然语言 subject 漂移 |
| `stale_value_leaked` | 同 stable key 下确认新版本后，旧版本稳定 superseded，默认检索用 active-only + stable key shadow filter |
| `keyword_miss` | alias 作为 query expansion，不改变 evidence gate |
| `evidence_missing` | alias 命中不能替代 evidence，active memory 仍必须带 quote/source |
| `permission_scope_error` | alias 表和 binding 表必须带 tenant/org/scope，解析前后都不能跨权限上下文 |

建议后续 benchmark 增加两个派生指标：

```text
Stable Key Match Rate
  = conflict case 中预期 stable key 被正确解析的比例

Alias-induced False Merge Rate
  = alias 解析导致不同槽位被错误合并的比例
```

新增失败类型可由主线程评估后再改代码：

```text
stable_key_missing
alias_false_merge
alias_permission_scope_error
```

## Phased Rollout

### Phase 0：benchmark / design only

范围：

- 保留本文作为设计入口。
- 在 benchmark case 中标注 `expected_stable_key`、`expected_slot_type`、`expected_alias` 的草案字段，但不要求 runner 读取。
- 主线程可选择是否在 `docs/README.md` 导航挂本文；本子任务不改导航，避免和主线程 benchmark 文档冲突。

验收命令：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
git diff --check
```

不做：

- 不改 Python。
- 不改 README。
- 不改数据库 schema。
- 不新增真实 Feishu 数据或真实 ID。

### Phase 1：只读 alias 解析

范围：

- 新增只读 resolver，输入文本、scope、tenant/org，输出 stable key candidate 和 explanation。
- resolver 不写库，不改变 candidate / confirm 行为。
- benchmark 只记录 `observed_stable_key` 与 expected 的差异。

建议验收命令：

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_benchmark tests.test_copilot_governance
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
git diff --check
```

不做：

- 不让 resolver 自动覆盖 active memory。
- 不让 alias 解析绕过 permission。
- 不在 OpenClaw schema 增加 breaking 字段。

### Phase 2：写入治理层 candidate metadata

范围：

- `memory.create_candidate` 输出中加入非 breaking 的 stable key metadata。
- conflict candidate 卡片和 review inbox 展示业务槽位解释。
- confirm 后激活 binding；reject / undo 后同步回滚 binding 状态。

建议验收命令：

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_permissions tests.test_copilot_governance
python3 -m unittest tests.test_copilot_schemas tests.test_copilot_tools
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
git diff --check
```

不做：

- 不自动确认真实 Feishu 冲突候选。
- 不把 alias candidate 当成已验证组织事实。
- 不把一次 sandbox 验证写成稳定长期 live。

### Phase 3：retrieval / benchmark 联动

范围：

- search / prefetch 使用 stable key 作为 structured hint 和旧值 shadow filter。
- benchmark 汇总 stable key 指标和 alias false merge。
- `docs/benchmark-report.md` 只报告实际运行结果，不删除失败样例。

建议验收命令：

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_retrieval tests.test_copilot_benchmark
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_real_feishu_cases.json
git diff --check
```

不做：

- 不改变 active-only 默认召回原则。
- 不向量化全部 raw events。
- 不用 alias 扩权检索。

## 导航建议

为避免和主线程正在更新的 benchmark 文档冲突，本任务不修改 `docs/README.md`。建议主线程后续在“产品规划”或“深研改进事项”附近增加一行：

```text
[productization/stable-memory-key-alias-design.md](productization/stable-memory-key-alias-design.md)：稳定 memory key / alias 层设计，用于降低 subject normalization 和旧值泄漏风险。
```

## 开放问题

1. `project_slug` 首版来自规则 seed、当前 scope 还是显式项目实体？
2. alias candidate 是否需要单独 review queue，还是复用现有 candidate review inbox？
3. stable key 是否最终进入 `memories` 表索引，还是长期保持 binding adapter？
4. `weekly_report_recipient`、`owner`、`reviewer` 三类人员槽位如何避免误合并？
5. benchmark 是否先要求人工标注 expected stable key，再让 resolver 逐步追平？

## 完成定义

首版完成不是“alias 系统上线”，而是：

- 高价值业务槽位、alias 表、binding 表和 rollout gate 已写清。
- 与 governance conflict detection、retrieval 和 benchmark failure taxonomy 的连接点已明确。
- 验收命令和不做事项足够具体，后续 executor 可以小步实现。
- 文档保持 no-overclaim：当前仍只是设计，不代表 productized live 或真实 Feishu 长期运行完成。
