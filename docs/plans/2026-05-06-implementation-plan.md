# 2026-05-06 Implementation Plan

阶段：提交材料、录屏、QA、scope freeze
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

初赛冻结前 QA 和材料打包：修复会影响 5 分钟 Demo 的阻塞问题，准备提交 checklist、录屏分镜、截图证据和最终验证路径。今天开始范围冻结，只修阻塞，不再新增未验证功能。

## 必读上下文

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/plans/2026-05-06-implementation-plan.md`
- `README.md`
- `docs/demo-runbook.md`
- `docs/benchmark-report.md`
- `docs/memory-definition-and-architecture-whitepaper.md`

## 用户白天主线任务

1. 创建 `docs/submission-checklist.md`。
2. 做全流程 QA：Copilot tools、CLI fallback、Feishu dry-run / replay、benchmark、Bitable 可选同步。
3. 准备录屏分镜和截图清单。
4. 检查 README、Demo runbook、Benchmark Report、白皮书之间是否有矛盾表述。
5. 确认 `agent_adapters/openclaw/` 文档中的命令可复制执行或明确标注为 schema demo / dry-run。
6. 检查 Cognee 本地 SDK path、`.data/cognee/`、repository fallback 的说法是否一致。
7. 检查 stale/superseded 不泄漏、sensitive reminder 不泄漏、evidence coverage 的验证证据是否写入材料。

## 需要改/新增的文件

- `docs/submission-checklist.md`
- `docs/demo-runbook.md`
- `docs/benchmark-report.md`
- `docs/memory-definition-and-architecture-whitepaper.md`
- `README.md`
- 可选：`scripts/verify.sh`

## 测试

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m unittest discover tests
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine benchmark run benchmarks/day7_anti_interference.json --markdown-output docs/benchmark-report.md
```

如果 `copilot_*` runner 已存在，再追加当天已有的全部专项 benchmark；没有实现的必须进入 checklist 的降级说明。

## 验收标准

- submission checklist 能逐项确认初赛三大交付物。
- 任意一天坏掉的功能都不能留到 2026-05-07。
- README 足够让评委或队友复现核心流程。
- 敏感文件、数据库、日志、token 不进入提交。
- Demo 失败时有 replay / dry-run / 录屏保底。

## 队友晚上补位任务

给队友先看这个：

1. 今天开始不加新功能，只做提交前检查。
2. 按 checklist 逐项验收。
3. 完成 Benchmark Report 终稿审阅，尤其看指标和失败分类是否容易懂。
4. 录第一版 Demo 视频或至少准备截图证据。
5. 遇到问题发我：checklist 项、失败现象、截图或命令输出。

今晚不用做：

- 不用再加新功能。
- 不用做大重构。
