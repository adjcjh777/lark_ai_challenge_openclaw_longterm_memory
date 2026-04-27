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

## 今日做到什么程度

今天结束时进入 scope freeze：只修提交阻塞，不再扩功能。

- `docs/submission-checklist.md` 能逐项判断白皮书、Demo、Benchmark Report 是否达标。
- README、runbook、benchmark report、whitepaper 的架构叙事一致。
- 录屏脚本、截图清单和 fallback 路径准备好。
- 所有验证命令有当前结果；失败项必须写成 checklist blocker 或降级说明。
- 敏感文件、日志、数据库、token 不进入提交。

## 今日执行清单（按顺序）

| 顺序 | 动作 | 文件/位置 | 做到什么程度 | 验收证据 |
|---|---|---|---|---|
| 1 | 创建提交 checklist | `docs/submission-checklist.md` | 覆盖三大交付物、命令、截图、风险、提交链接 | checklist 每项可勾选 |
| 2 | 文档一致性检查 | README/runbook/report/whitepaper | OpenClaw、Cognee、Copilot Core、Feishu 职责描述一致 | 没有互相矛盾表述 |
| 3 | 跑全量 QA | 本地命令 | compileall、unittest、day1、day7、已有 copilot benchmarks | 结果记录到 checklist |
| 4 | 修 P0 阻塞 | 相关文件 | 只修影响 demo/benchmark/提交的 blocker | 每个 blocker 有修复或降级说明 |
| 5 | 准备录屏分镜 | checklist/runbook | 5 分钟视频每 30-60 秒讲什么、展示什么 | 可直接开始录屏 |
| 6 | 准备截图清单 | checklist | README、tool schema、demo output、benchmark summary、whitepaper 图 | 截图文件名和用途明确 |
| 7 | 检查敏感文件 | Git | `.env`、`.omx/`、`.data/`、logs、db、token 不被 staged | `git status --short --ignored` 复核 |
| 8 | 最终范围冻结 | checklist | 后续只修 P0，不接新功能 | checklist 标注 freeze 规则 |

## 今日不做

- 不新增未进入 benchmark 的功能。
- 不大重构核心架构。
- 不为了录屏临时绕过权限、安全或 evidence。
- 不把未验证的 live 能力写成最终能力。

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
- README 足够让评委或未来复现者复现核心流程。
- 敏感文件、数据库、日志、token 不进入提交。
- Demo 失败时有 replay / dry-run / 录屏保底。

## 我的补充任务

先看这个：

1. 今天开始不加新功能，只做提交前检查。
2. 按 checklist 逐项验收。
3. 完成 Benchmark Report 终稿审阅，尤其看指标和失败分类是否容易懂。
4. 录第一版 Demo 视频或至少准备截图证据。
5. 遇到问题记录：checklist 项、失败现象、截图或命令输出。

本阶段不用做：

- 不用再加新功能。
- 不用做大重构。
