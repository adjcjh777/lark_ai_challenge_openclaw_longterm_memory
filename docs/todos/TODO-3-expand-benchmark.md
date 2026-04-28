# TODO-3：扩大 Benchmark 规模

## 目标

将 Copilot Benchmark 样例总规模从当前 84 条扩充到 200+ 条，覆盖更多真实场景、边界条件和难例，使评测结果更具统计说服力，为复赛指标自证提供更坚实的数据基础。

---

## 当前状态分析

### 总览

| Benchmark 类型 | 文件 | 现有样例数 | 目标样例数 | 需新增 |
|---|---|---:|---:|---:|
| copilot_recall | `copilot_recall_cases.json` | 10 | 40 | +30 |
| copilot_candidate | `copilot_candidate_cases.json` | 34 | 55 | +21 |
| copilot_conflict | `copilot_conflict_cases.json` | 12 | 35 | +23 |
| copilot_layer | `copilot_layer_cases.json` | 15 | 40 | +25 |
| copilot_prefetch | `copilot_prefetch_cases.json` | 6 | 20 | +14 |
| copilot_heartbeat | `copilot_heartbeat_cases.json` | 7 | 20 | +13 |
| **合计** | | **84** | **210** | **+126** |

### 各类 Benchmark 现有覆盖范围

#### 1. Recall（10 条）

| 覆盖场景 | 样例数 | case_id 前缀 |
|---|---:|---|
| active 版本优先（旧值不污染） | 1 | `copilot_recall_deploy_region_001` |
| 负责人信息召回 | 1 | `copilot_recall_benchmark_owner_001` |
| 版本锁安全规则 | 1 | `copilot_recall_openclaw_version_001` |
| raw event 不直接返回 | 1 | `copilot_recall_raw_event_exclusion_001` |
| 当天任务边界 | 1 | `copilot_recall_team_task_001` |
| keyword-only 命中 | 1 | `copilot_recall_keyword_only_demo_path_001` |
| vector-only 语义改写 | 1 | `copilot_recall_vector_only_review_material_001` |
| stale conflict 覆盖 | 1 | `copilot_recall_stale_conflict_bitable_001` |
| 多轮改口截止时间 | 1 | `copilot_recall_multi_turn_deadline_override_002` |
| 未采纳方案过滤 | 1 | `copilot_recall_tentative_tool_not_decision_002` |

**缺口**：缺少多语言混用、长事件链（3+ 轮覆盖）、同义词改写、跨主题干扰、噪声环境下召回、高频 query 稳定性等场景。

#### 2. Candidate（34 条：17 should + 17 skip）

| 覆盖场景 | 样例数 |
|---|---:|
| should - 决策/规则/负责人/截止时间/风险/选型/流程/偏好 | 17 |
| skip - 闲聊/临时状态/未定论/UI 观察/重复消息/模糊反馈 | 17 |

**缺口**：缺少含敏感信息的 candidate 识别、跨 scope candidate、长文本 candidate、多语言 candidate、与已有记忆语义重复的 candidate（去重检测）等场景。

#### 3. Conflict（12 条）

| 覆盖场景 | 样例数 |
|---|---:|
| region/参数/负责人/框架/指标/版本/截止时间/权限/写入链路/Demo 流程覆盖 | 12 |

**缺口**：缺少多级覆盖链（A->B->C 三轮覆盖）、隐式冲突（措辞不同但语义冲突）、同主题多字段部分更新、冲突检测后 reject 场景、跨 scope 冲突等。

#### 4. Layer（15 条：L1=5, L2=5, L3=5）

| 层级 | 覆盖场景 | 样例数 |
|---|---|---:|
| L1 Hot | 部署参数、版本锁、Ollama 清理、README 入口、Copilot-first 开发边界 | 5 |
| L2 Warm | 当天任务、handoff、recall 审查、看板同步、Demo 文案 | 5 |
| L3 Cold | 版本链历史、选型归档、旧文档读取规则、历史评测报告 | 5 |

**缺口**：缺少 L1/L2/L3 边界模糊场景（应归 L2 但常被 L1 抢占）、L2 fallback 到 L1 的降级验证、L3 大量噪声下冷记忆仍可召回、跨天记忆自动降层等。

#### 5. Prefetch（6 条）

| 覆盖场景 | 样例数 |
|---|---:|
| 部署 checklist、截止时间、Demo 讲解词、旧值过滤、Bitable dry-run、Bitable 写入链路 | 6 |

**缺口**：缺少多记忆组合预取、任务意图不明确时的 fallback、空 context pack 处理、高优先生命周期记忆优先排序、prefetch 与 heartbeat 联动等。

#### 6. Heartbeat（7 条）

| 覆盖场景 | 样例数 |
|---|---:|
| deadline 触发、重要记忆未召回、线程相似性、敏感脱敏、review_due、webhook 脱敏、非 reviewer 权限隔离 | 7 |

**缺口**：缺少 cooldown 去重、多条 reminder 同时触发的排序、噪声记忆不应触发 reminder、heartbeat 与 conflict 联动（记忆被更新后触发复核）、长时间未使用记忆的定期提醒等。

---

## 详细子任务清单

### 子任务 3.1：扩充 Recall 样例（+30 条，目标 40 条）

**负责人**：程俊豪
**预计工作量**：2-3 小时

| # | 新增样例类型 | 数量 | 说明 |
|---|---|---:|---|
| 3.1.1 | 多轮覆盖链（3+ 轮） | 5 | 同一决策被 3 次以上修正，验证最终版本正确召回且旧版本全部 superseded |
| 3.1.2 | 同义词 / 语义改写查询 | 5 | query 不使用事件原文关键词，靠 vector 信号命中。如"部署地区"查询命中"region"记忆 |
| 3.1.3 | 跨主题干扰下的精准召回 | 5 | 事件包含多个主题（部署+周报+框架），query 只问其中一个主题 |
| 3.1.4 | 噪声环境下召回 | 5 | 设置 `noise_count` >= 50，在大量无关闲聊中仍能召回正确记忆 |
| 3.1.5 | 长事件链稳定性 | 5 | 事件序列 5+ 条，包含多次修正和补充，验证最终状态一致 |
| 3.1.6 | 多语言 / 中英混用 | 3 | 事件和 query 混用中英文，验证 tokenizer 和 embedding 兼容性 |
| 3.1.7 | 高频 query 一致性 | 2 | 同一 query 多次执行，验证结果稳定不漂移（通过 benchmark runner 的单 case 多次运行实现） |

**JSON 格式示例**：
```json
{
  "case_id": "copilot_recall_multi_turn_chain_001",
  "type": "copilot_recall",
  "layer_hint": "L2",
  "events": [
    "CI 流水线用 Jenkins。",
    "不对，CI 流水线改成 GitHub Actions。",
    "最终确认：CI 流水线统一用 GitLab CI，GitHub Actions 只保留旧项目。"
  ],
  "query": "CI 流水线现在用什么",
  "expected_active_value": "GitLab CI",
  "forbidden_value": "Jenkins",
  "evidence_keyword": "统一用 GitLab CI",
  "expected_memory_intent": "记录 CI 流水线最终选型，避免旧方案泄漏。",
  "failure_debug_hint": "检查三轮覆盖后 active 是否指向 GitLab CI。",
  "failure_category": "stale_conflict",
  "note": "三轮覆盖链，验证最终版本召回。"
}
```

### 子任务 3.2：扩充 Candidate 样例（+21 条，目标 55 条）

**负责人**：程俊豪
**预计工作量**：1.5-2 小时

| # | 新增样例类型 | 数量 | 说明 |
|---|---|---:|---|
| 3.2.1 | should - 含敏感信息的决策 | 3 | 包含 token/secret 但仍是有效决策，应进入 candidate 并触发 risk_flags |
| 3.2.2 | should - 长文本决策 | 3 | 超过 100 字的复杂决策描述，验证长文本 candidate 识别 |
| 3.2.3 | should - 多语言决策 | 3 | 中英混合的规则描述 |
| 3.2.4 | should - 与已有记忆语义重复但值不同 | 3 | 已有"部署用 canary"，新文本"部署用 blue-green"，应进入 conflict candidate |
| 3.2.5 | skip - 表情 / emoji 为主的消息 | 2 | 纯 emoji 或表情包描述，不应进入 candidate |
| 3.2.6 | skip - 引用他人但未表态 | 3 | "有人说可以用 X"但没有形成决策 |
| 3.2.7 | skip - 技术讨论中的疑问句 | 2 | "这个方案可行吗？"是提问不是决策 |
| 3.2.8 | skip - 与已有记忆完全重复 | 2 | 同一内容再次出现，不应重复创建 candidate |

**JSON 格式示例**：
```json
{
  "case_id": "cand_should_018",
  "type": "copilot_candidate",
  "text": "部署密钥 deploy_token=sk-prod-abc123 只能放 CI/CD 变量，不能写进代码仓库。",
  "expected_candidate": true,
  "expected_reason": "这是密钥管理规则，虽然包含敏感信息但属于高价值决策。"
}
```

### 子任务 3.3：扩充 Conflict 样例（+23 条，目标 35 条）

**负责人**：程俊豪
**预计工作量**：2-3 小时

| # | 新增样例类型 | 数量 | 说明 |
|---|---|---:|---|
| 3.3.1 | 三轮覆盖链 A->B->C | 5 | 旧值被中间值覆盖，中间值又被最终值覆盖，验证只返回最终值 |
| 3.3.2 | 隐式冲突（措辞不同但语义冲突） | 5 | 旧记忆"测试覆盖率达到 80%"，新文本"覆盖率标准改成 90%"，用词不同但同一主题 |
| 3.3.3 | 同主题多字段部分更新 | 3 | 旧记忆包含 region+参数，新文本只更新 region 但不改参数 |
| 3.3.4 | confirm 后 reject 场景 | 3 | 创建 candidate 后 reject 而非 confirm，旧记忆应保持不变 |
| 3.3.5 | 跨主题但用词相似 | 3 | "部署 region"和"服务器 region"是否被归为不同主题 |
| 3.3.6 | 数值型冲突 | 2 | 版本号、端口号、超时时间等数值修正 |
| 3.3.7 | 时间型冲突 | 2 | 截止时间、cron 表达式、频率等时间相关修正 |

**JSON 格式示例**：
```json
{
  "case_id": "conflict_triple_override_013",
  "type": "copilot_conflict",
  "existing_memories": [
    {"content": "规则：日志保留 7 天。"}
  ],
  "text": "刚才说错了，日志保留改成 30 天。但后来又确认了，最终统一改成 14 天。",
  "query": "日志保留天数",
  "expected_active_value": "14 天",
  "forbidden_value": "7 天",
  "expected_action": "confirm",
  "expected_reason": "三轮覆盖后最终值应为 14 天。",
  "failure_debug_hint": "检查最终 active 是否为 14 天，旧值 7 天是否 superseded。"
}
```

### 子任务 3.4：扩充 Layer 样例（+25 条，目标 40 条）

**负责人**：程俊豪
**预计工作量**：2-3 小时

| # | 新增样例类型 | 数量 | 说明 |
|---|---|---:|---|
| 3.4.1 | L1 - 高频操作守则 | 4 | 每日开发中反复使用的规则（git 分支命名、commit 规范、代码审查流程等） |
| 3.4.2 | L1 - 安全红线 | 3 | 禁止操作（禁止 force push、禁止明文密码提交等），应永远在 L1 可查 |
| 3.4.3 | L2 - 当天待办任务 | 4 | 具体到日期的任务分配，适合 L2 近期记忆 |
| 3.4.4 | L2 - 最近决策（本周内） | 3 | 最近几天做出的技术决策，尚未沉淀为长期规则 |
| 3.4.5 | L2 - 边界模糊场景 | 3 | 应归 L2 但可能被 L1 抢占的场景，验证分层准确性 |
| 3.4.6 | L3 - 历史选型记录 | 3 | 早期讨论过但已放弃的方案，应归入 L3 归档 |
| 3.4.7 | L3 - 已完成任务归档 | 3 | 过去已完成的任务记录，只在复盘时需要 |
| 3.4.8 | 跨层 fallback 验证 | 2 | L1 无结果时应 fallback 到 L2，L2 无结果时 fallback 到 L3 |

**JSON 格式示例**：
```json
{
  "case_id": "copilot_layer_l1_git_branch_001",
  "type": "copilot_layer",
  "expected_layer": "L1",
  "events": [
    "新功能分支统一用 feature/xxx 命名，bug 修复用 bugfix/xxx，这是团队每天都要遵守的。"
  ],
  "query": "git 分支怎么命名",
  "expected_active_value": "feature/xxx",
  "evidence_keyword": "每天都要遵守",
  "failure_debug_hint": "检查 L1 是否返回分支命名规则。",
  "layer_reason": "Hot 是每天使用的分支管理规则。"
}
```

### 子任务 3.5：扩充 Prefetch 样例（+14 条，目标 20 条）

**负责人**：程俊豪
**预计工作量**：1-2 小时

| # | 新增样例类型 | 数量 | 说明 |
|---|---|---:|---|
| 3.5.1 | 多记忆组合预取 | 3 | 一个任务需要多条记忆（部署=region+参数+检查清单），验证 context pack 组合能力 |
| 3.5.2 | 任务意图模糊时的 fallback | 3 | task 描述含糊（"准备一下"），验证 prefetch 是否仍能返回相关记忆 |
| 3.5.3 | 空记忆库时的 prefetch | 2 | 没有任何记忆时，prefetch 应返回空 context pack 而非报错 |
| 3.5.4 | 高优先记忆排序 | 3 | 多条相关记忆中，安全规则应排在偏好设置之前 |
| 3.5.5 | 旧值过滤扩展 | 3 | 不同主题的旧值过滤（不只是 region），验证通用 superseded 过滤能力 |

**JSON 格式示例**：
```json
{
  "case_id": "prefetch_multi_memory_deploy",
  "type": "copilot_prefetch",
  "task": "执行生产部署",
  "current_context": {
    "intent": "生产部署全流程",
    "thread_topic": "部署"
  },
  "events": [
    {"content": "生产部署必须加 --canary --region ap-shanghai。"},
    {"content": "部署前必须跑 git diff --check 和单元测试。"},
    {"content": "部署后必须检查回滚脚本是否可用。"}
  ],
  "expected_memory_keyword": "--canary",
  "failure_debug_hint": "context pack 应包含部署相关的多条记忆。"
}
```

### 子任务 3.6：扩充 Heartbeat 样例（+13 条，目标 20 条）

**负责人**：程俊豪
**预计工作量**：1-2 小时

| # | 新增样例类型 | 数量 | 说明 |
|---|---|---:|---|
| 3.6.1 | cooldown 去重 | 2 | 同一记忆在 cooldown 期间不应重复触发 reminder |
| 3.6.2 | 多条 reminder 同时触发的排序 | 2 | 多条记忆同时满足触发条件时，应按优先级排序 |
| 3.6.3 | 噪声记忆不触发 | 2 | 低价值记忆（闲聊记录）不应触发 heartbeat reminder |
| 3.6.4 | 记忆更新后触发复核 | 2 | 记忆被 conflict 更新后，应触发 review_due reminder |
| 3.6.5 | 长期未使用记忆定期提醒 | 2 | 超过 14 天未被召回的重要记忆，应生成提醒候选 |
| 3.6.6 | 敏感信息脱敏扩展 | 3 | 不同类型的敏感信息（密码、token、私钥等），验证脱敏覆盖 |

**JSON 格式示例**：
```json
{
  "case_id": "heartbeat_cooldown_dedup",
  "type": "copilot_heartbeat",
  "current_context": {"intent": "检查部署参数"},
  "events": [
    {"content": "生产部署必须加 --canary --region ap-shanghai。"}
  ],
  "mark_recalled_query": "生产部署参数",
  "cooldown_ms": 0,
  "expected_trigger": "important_not_recalled",
  "expected_subject": "生产部署",
  "failure_debug_hint": "已召回的记忆在 cooldown 期间不应重复触发 reminder。"
}
```

---

## 依赖关系

```
子任务 3.1 (Recall) ──┐
子任务 3.2 (Candidate) ──┤
子任务 3.3 (Conflict) ──┼──> 无互相依赖，可并行编写
子任务 3.4 (Layer) ──┤
子任务 3.5 (Prefetch) ──┤
子任务 3.6 (Heartbeat) ──┘

全部完成 ──> 运行全量 benchmark 验证 ──> 更新 benchmark-report.md
```

**前置条件**：
- `memory_engine/benchmark.py` 已支持所有 6 类 benchmark 的 runner（已完成）
- 各 JSON 文件格式与现有样例一致（遵循现有 schema）

**后续依赖**：
- 本任务完成后，`docs/benchmark-report.md` 需要更新为 200+ 条样例的评测结果
- `reports/` 目录下需重新生成 JSON/CSV 评测证据

---

## 风险和注意事项

### 风险

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| 新增样例导致现有通过率下降 | 指标短期波动 | 新增样例先在本地验证，失败样例记录 failure_type 并分析是否为系统缺陷 |
| 样例质量参差不齐 | 评测结果噪声增大 | 每条样例必须有明确的 expected_active_value、evidence_keyword 和 failure_debug_hint |
| JSON 格式不一致 | benchmark runner 解析失败 | 严格遵循现有样例的字段命名和嵌套结构 |
| 样例主题过于集中 | 覆盖范围仍然有限 | 每类样例的主题应尽量分散，覆盖部署、协作、架构、安全、Demo 等多个维度 |
| 200+ 条样例运行时间过长 | 开发迭代变慢 | 单类 benchmark 独立运行，不强制每次跑全量；CI 可只跑增量样例 |

### 注意事项

1. **case_id 命名规范**：遵循 `{type}_{主题}_{序号}` 格式，如 `copilot_recall_multi_turn_chain_001`。序号从现有最大值递增。
2. **forbidden_value 必填**：对于有冲突/覆盖场景的样例，必须设置 forbidden_value 以验证旧值不泄漏。
3. **evidence_keyword 必填**：每条 recall/conflict/layer 样例必须有 evidence_keyword，用于验证证据链完整性。
4. **failure_debug_hint 必填**：每条样例必须有调试提示，便于失败时快速定位。
5. **不删除现有样例**：即使现有样例通过率下降，也不要为了指标删除难例。
6. **主题多样性**：每类 benchmark 新增样例的主题应覆盖：部署规则、协作规范、技术选型、安全约束、Demo 准备、看板管理等。
7. **避免样例间冲突**：不同样例的 events 不应互相矛盾（除非是 conflict 类型的刻意设计）。

---

## 验证命令

### 单类验证（开发过程中）

```bash
# Recall 样例验证
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json --json-output reports/copilot_recall.json --csv-output reports/copilot_recall.csv

# Candidate 样例验证
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json --json-output reports/copilot_candidate.json --csv-output reports/copilot_candidate.csv

# Conflict 样例验证
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json --json-output reports/copilot_conflict.json --csv-output reports/copilot_conflict.csv

# Layer 样例验证
python3 -m memory_engine benchmark run benchmarks/copilot_layer_cases.json --json-output reports/copilot_layer.json --csv-output reports/copilot_layer.csv

# Prefetch 样例验证
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json --json-output reports/copilot_prefetch.json --csv-output reports/copilot_prefetch.csv

# Heartbeat 样例验证
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json --json-output reports/copilot_heartbeat.json --csv-output reports/copilot_heartbeat.csv
```

### 全量验证（完成后）

```bash
# 一键运行全部 benchmark 并生成报告
for f in benchmarks/copilot_*_cases.json; do
  name=$(basename "$f" .json)
  python3 -m memory_engine benchmark run "$f" \
    --json-output "reports/${name}.json" \
    --csv-output "reports/${name}.csv" \
    --markdown-output "docs/benchmark-report.md"
done

# 检查总样例数
echo "=== 样例统计 ==="
for f in benchmarks/copilot_*_cases.json; do
  count=$(python3 -c "import json; print(len(json.load(open('$f'))))")
  echo "$f: $count 条"
done
```

### 样例数验证（快速检查）

```bash
# 确认每类样例数量达到目标
python3 -c "
import json
from pathlib import Path
targets = {
    'copilot_recall_cases': 40,
    'copilot_candidate_cases': 55,
    'copilot_conflict_cases': 35,
    'copilot_layer_cases': 40,
    'copilot_prefetch_cases': 20,
    'copilot_heartbeat_cases': 20,
}
total = 0
for name, target in targets.items():
    path = Path(f'benchmarks/{name}.json')
    count = len(json.loads(path.read_text()))
    total += count
    status = '✅' if count >= target else '❌'
    print(f'{status} {name}: {count}/{target}')
print(f'\n总计: {total}/210')
"
```

---

## 完成标准

- [x] 6 类 benchmark JSON 文件的样例数均达到目标值
- [ ] 全部 200+ 条样例通过 benchmark runner 验证
- [ ] 每条新增样例有完整的 expected_active_value、evidence_keyword、failure_debug_hint
- [ ] 失败样例已记录 failure_type 并分析原因
- [ ] `docs/benchmark-report.md` 已更新为最新评测结果
- [ ] `reports/` 目录下已生成最新的 JSON/CSV 证据文件
