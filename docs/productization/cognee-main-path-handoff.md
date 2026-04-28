# Cognee 主路径 Handoff

日期：2026-04-28
阶段：后期打磨 P1：让 Cognee 真正进入主路径

## 本轮完成了什么

本轮把 Cognee 从“adapter / live gate 可用”补成了本地可控、可回退、可观测的 recall substrate：

- `memory.confirm` 成功后会把 active memory 的 curated fields 同步给 Cognee。
- 同步文本只包含 `type`、`subject`、`current_value`、`summary` 和 `evidence_quote`，不包含 raw event 全量内容。
- Cognee 同步走 `add -> cognify`，并携带 `memory_id`、`version_id`、`version`、`status`、`source_type`、`source_id`、`quote` 和 `provenance=copilot_ledger`。
- `memory.reject` 成功后会调用 adapter withdrawal，把被拒绝候选从 scoped dataset 撤回。
- Cognee 不可用或同步失败时，响应里返回 `cognee_sync.status=fallback_used` 或 `skipped`，主流程继续以 repository ledger 为事实源。
- 检索层继续要求 Cognee result 匹配本地 ledger；未匹配结果只进入 trace note，不进入正式 answer。

## 关键文件

| 文件 | 说明 |
|---|---|
| `memory_engine/copilot/cognee_adapter.py` | 新增 curated memory document、`sync_curated_memory()`、`sync_memory_withdrawal()`。 |
| `memory_engine/copilot/service.py` | `confirm` / `reject` 后补 `cognee_sync` 状态，失败时 fallback。 |
| `memory_engine/copilot/governance.py` | confirm / reject 响应携带 version、summary、evidence，供 adapter 同步 curated fields。 |
| `memory_engine/copilot/retrieval.py` | 已有 ledger ownership 过滤和 async Cognee search 归一化。 |
| `tests/test_copilot_cognee_adapter.py` | 锁住 dataset、add/cognify、withdrawal 和 curated-only 文本。 |
| `tests/test_copilot_governance.py` | 锁住 confirm sync、reject withdrawal 和 sync failure fallback。 |
| `tests/test_copilot_retrieval.py` | 锁住 Cognee result 必须匹配本地 ledger。 |

## 验证结果

已运行：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_live_embedding_gate.py --json
python3 scripts/check_embedding_provider.py
python3 scripts/spike_cognee_local.py --dry-run
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_cognee_adapter tests.test_copilot_governance tests.test_copilot_retrieval
git diff --check
ollama ps
```

结果：

- OpenClaw version OK：`2026.4.24`。
- Live embedding gate：`ok=true`，provider actual dimensions `1024`，Cognee dry-run pass，gate 内部清理后 `running_after_cleanup=[]`。
- 单独 `check_embedding_provider.py`：`ok=true`，actual dimensions `1024`；该命令会提示需要清理本项目模型。
- 单独 `spike_cognee_local.py --dry-run`：`ok=true`，dataset `feishu_memory_copilot_project_feishu_ai_challenge`。
- `compileall` 通过。
- Cognee adapter / governance / retrieval：32 tests OK。
- `git diff --check` 通过。
- Ollama 清理：单独 provider 检查后看到 `qwen3-embedding:0.6b-fp16` 驻留；已运行 `ollama stop qwen3-embedding:0.6b-fp16`，最终 `ollama ps` 为空。

## 边界

- 本阶段不是生产部署。
- 本阶段不是长期 embedding 服务。
- 本阶段不是 productized live。
- Cognee 是可回退 recall channel，不是绕过 Copilot ledger 的新事实源。
- raw events 不会被全量向量化；只同步确认后的 curated memory。

## 下一步

继续 [launch-polish-todo.md](launch-polish-todo.md) 第 7 项：把 review surface 接成真实可操作界面。

必须保持：

- confirm / reject / view versions 只通过 `CopilotService` / `handle_tool_request()`。
- non-reviewer 操作必须拒绝，candidate 状态不变。
- card / Bitable 不展示未授权 evidence 或 `current_value`。
- Bitable 写回必须幂等、可重试、可读回确认。
