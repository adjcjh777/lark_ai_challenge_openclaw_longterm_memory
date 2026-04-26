# 2026-05-07 Implementation Plan

阶段：最终验证、提交缓冲、push  
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

完成初赛提交日最终缓冲：从干净状态跑完整验证，固定 Demo 数据和提交 hash，确保远程仓库包含三大交付物且不包含敏感/临时文件。今天只处理阻塞和材料一致性，不临场扩大功能范围。

## 必读上下文

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/2026-05-07-implementation-plan.md`
- `docs/submission-checklist.md`
- `README.md`
- `docs/demo-runbook.md`
- `docs/benchmark-report.md`
- `docs/memory-definition-and-architecture-whitepaper.md`

## 用户白天主线任务

1. 最后一次检查 `git status --short --ignored`。
2. 从干净状态运行完整验证。
3. 固定 Demo 数据和演示顺序。
4. 记录提交 hash 或 tag。
5. 确认 README、白皮书、Benchmark Report、Demo runbook、submission checklist 一致。
6. 确认 OpenClaw 版本仍是 `2026.4.24`。
7. 确认 `copilot_*` benchmark、examples、dry-run 降级说明没有互相矛盾。
8. 提交并 `git push origin HEAD`。

## 需要改/新增的文件

- `README.md`
- `docs/submission-checklist.md`
- `docs/demo-runbook.md`
- `docs/benchmark-report.md`
- `docs/memory-definition-and-architecture-whitepaper.md`
- 必要时补 `docs/submission-summary.md`

## 最终验收命令

```bash
git status --short --ignored
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m unittest discover tests
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine benchmark run benchmarks/day7_anti_interference.json --markdown-output docs/benchmark-report.md
python3 -m memory_engine benchmark run benchmarks/copilot_recall_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_candidate_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_conflict_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_layer_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_prefetch_cases.json
python3 -m memory_engine benchmark run benchmarks/copilot_heartbeat_cases.json
```

如果某个 `copilot_*` runner 尚未实现，必须在 `docs/submission-checklist.md` 中明确降级说明和已验证的替代路径。

## 验收标准

- 初赛三个交付物齐全：白皮书、Demo、Benchmark Report。
- 远程仓库不包含 `.env`、`.omx/`、数据库文件、缓存文件、真实飞书日志、token。
- main 分支是可提交状态。
- 现场网络或飞书权限失败时，有 replay / dry-run / 录屏保底。
- `README.md`、白皮书、Benchmark Report 对 Cognee、OpenClaw、Copilot Core、Card/Bitable 的职责描述一致。

## 队友晚上补位任务

给队友先看这个：

1. 今天只做最终验证和提交缓冲，不再临时加功能。
2. 用非开发者视角走一遍 README。
3. 做最终材料检查：白皮书、Demo、Benchmark Report 是否互相对得上。
4. 整理复赛待办，不在提交前临时加大改动。
5. 遇到问题发我：文件名、段落或命令输出。

今晚不用做：

- 不临场修非阻塞问题。
- 不新增未验证功能。
