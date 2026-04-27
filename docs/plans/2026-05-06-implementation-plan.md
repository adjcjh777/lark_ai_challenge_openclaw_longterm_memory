# 2026-05-06 Implementation Plan

阶段：完整产品 Phase 0 / Phase 0.5（提交冻结保护 + 产品化基线 RFC）
主控：`docs/feishu-memory-copilot-implementation-plan.md`
产品化入口：`docs/productization/complete-product-roadmap-prd.md`、`docs/productization/complete-product-roadmap-test-spec.md`

## 执行前先看这个

1. 今天不是临时加功能，而是把“完整产品路线”落到仓库可追踪文档，同时保护初赛提交材料不被破坏。
2. 我接下来从 README 顶部、总控计划、产品化 PRD/Test Spec、Demo/Benchmark/白皮书一致性开始。
3. 今天要交付：Phase 0 提交冻结说明、Phase 0.5 产品化基线说明、no-overclaim（不夸大 live 能力）检查清单。
4. 判断做对：读者打开 GitHub 第一屏能知道下一步是完整产品推进；同时不会误以为已经完成真实飞书 live ingestion。
5. 遇到问题记录：哪些能力只是 schema demo、dry-run、replay、OpenClaw live bridge，哪些才是 future limited Feishu ingestion。

## 当日目标

完成完整产品路线的第一步：**先保护初赛提交闭环，再把产品化基线 RFC 写清楚**。

今天的重点不是写新代码，而是把 PRD 里的完整产品定义落到仓库文档，让后续开发不会继续停留在零散 Demo：

- Phase 0：保护已完成的 README、Demo runbook、Benchmark Report、白皮书和提交材料路径。
- Phase 0.5：把产品化基线契约写清楚，包括 dry-run / replay / OpenClaw live bridge / limited Feishu ingestion / productized live 的区别。
- 把 2026-05-06 和 2026-05-07 从“只做提交收尾”改成“提交保护 + 产品化启动”的连续计划。

## 必读上下文

- `AGENTS.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/productization/complete-product-roadmap-prd.md`
- `docs/productization/complete-product-roadmap-test-spec.md`
- `docs/plans/2026-05-06-implementation-plan.md`
- `docs/plans/2026-05-05-handoff.md`
- `README.md`
- `docs/demo-runbook.md`
- `docs/benchmark-report.md`
- `docs/memory-definition-and-architecture-whitepaper.md`

## 我的主线任务

1. 更新 README 顶部入口，让 GitHub 第一屏显示“完整产品 Phase 0/0.5”当前任务。
2. 更新总控计划，明确 2026-05-06 起采用 `Proof MVP -> Contracted Live Slice -> Controlled Productization` 路线。
3. 把 `.omx/plans/` 中批准的 PRD/Test Spec 复制或同步到 `docs/productization/`，让它们进入仓库可追踪文档。
4. 检查 README、Demo runbook、Benchmark Report、白皮书是否把 dry-run / replay / OpenClaw live bridge 写成真实飞书 live ingestion；如有，改成准确标签。
5. 更新飞书共享看板：创建或更新 `2026-05-06 程俊豪 完整产品 Phase 0/0.5` 任务，状态为进行中或已完成，备注写文档路径和验证命令。

## 今日做到什么程度

今天结束时，后续开发应该能从仓库文档直接继续，而不是只靠聊天记录或 `.omx/` 本地状态：

- `docs/productization/complete-product-roadmap-prd.md` 存在并写清 Phase 0-7。
- `docs/productization/complete-product-roadmap-test-spec.md` 存在并写清测试矩阵、权限反例和 no-overclaim 检查。
- README 顶部第一个主要小节指向完整产品当前任务。
- 总控计划说明 2026-05-06 起进入完整产品路线，但初赛三大交付物仍要保护。
- 05-06/05-07 日期计划不再只写“提交材料收尾”，而是清楚写出 Phase 0/0.5 和 Phase 1 的衔接。
- 没有新增未验证代码能力，没有声称真实飞书 live ingestion 已完成。

## 今日执行清单（按顺序）

| 顺序 | 动作 | 文件/位置 | 做到什么程度 | 验收证据 |
|---|---|---|---|---|
| 1 | 校验当前环境 | OpenClaw / Git | 确认版本锁和工作树状态 | `python3 scripts/check_openclaw_version.py` 通过，记录 `git status --short` |
| 2 | 固化产品化计划 | `docs/productization/` | PRD/Test Spec 从 `.omx/plans/` 进入可追踪文档 | 两个 Markdown 文件存在，可点击 |
| 3 | 更新 README 顶部 | `README.md` | 第一屏显示完整产品 Phase 0/0.5 任务和直接链接 | 打开 README 不用翻目录 |
| 4 | 更新总控计划 | `docs/feishu-memory-copilot-implementation-plan.md` | 1.x 和 05-06/05-07 排期说明完整产品路线 | 明确 Contract Freeze Gate 前不接真实 ingestion |
| 5 | 更新日期计划 | `docs/plans/2026-05-06-implementation-plan.md`、`docs/plans/2026-05-07-implementation-plan.md` | 今天和明天任务能直接执行 | 每天有“执行前先看这个”和完成标准 |
| 6 | 做 no-overclaim 检查 | README/runbook/report/whitepaper | schema demo、dry-run、replay、OpenClaw live bridge、limited ingestion 标签一致 | 无“已完成真实飞书 live ingestion”误导 |
| 7 | 同步飞书共享看板 | lark-cli | 05-06 程俊豪任务和补充任务更新 | `lark-cli base +record-list` 读回确认，失败则写清错误 |
| 8 | 验证文档改动 | 本地命令 | 文档-only 至少通过版本锁和 diff 检查 | `python3 scripts/check_openclaw_version.py`、`git diff --check` 通过 |

## 我的补充任务

1. 检查 `docs/demo-runbook.md` 中每个演示步骤是否标注了 replay / dry-run / OpenClaw schema demo。
2. 检查 `agent_adapters/openclaw/examples/` 是否还让人误解为真实 runtime 已稳定接通。
3. 检查 `docs/benchmark-report.md` 是否把 benchmark 结果写成产品上线证明；如果有，改成“评测证明”。
4. 检查 `docs/memory-definition-and-architecture-whitepaper.md` 是否明确多租户权限目前是下一阶段硬门槛，而不是已完整生产化。
5. 在看板备注里写清：今天不接真实飞书 ingestion，不改 OpenClaw 版本，不写新功能代码。

## 今日不做

- 不实现 Phase 1 的 storage migration 或权限代码。
- 不接真实飞书消息、文档或 Bitable ingestion。
- 不启动 `$team` 并行实现。
- 不升级 OpenClaw，不重选 Cognee。
- 不把 OpenClaw seed/local bridge 写成 Feishu live ingestion。

## 需要改/新增的文件

- `README.md`
- `docs/feishu-memory-copilot-implementation-plan.md`
- `docs/productization/complete-product-roadmap-prd.md`
- `docs/productization/complete-product-roadmap-test-spec.md`
- `docs/plans/2026-05-06-implementation-plan.md`
- `docs/plans/2026-05-07-implementation-plan.md`
- 如 no-overclaim 检查发现问题，再小改：`docs/demo-runbook.md`、`docs/benchmark-report.md`、`docs/memory-definition-and-architecture-whitepaper.md`

## 验证

文档-only 改动至少运行：

```bash
python3 scripts/check_openclaw_version.py
git diff --check
```

如果同步看板，必须读回确认：

```bash
lark-cli base +record-list ...
```

本阶段不运行 embedding / Cognee / Ollama；如果临时运行相关验证，结束前必须执行 `ollama ps` 并停止本项目模型。

## 验收标准

- README 顶部能直接点击进入产品化 PRD/Test Spec 和日期计划。
- 总控计划和 05-06/05-07 日期计划都清楚说明完整产品路线。
- Phase 0/0.5 可执行：先保护提交，再写产品化基线，不开始代码实现。
- 文档没有把 dry-run、replay、schema demo、OpenClaw local bridge 夸大为真实飞书 live ingestion。
- 飞书共享看板与 README/日期计划一致；如果同步失败，最终回复和 handoff 必须写明失败命令和错误。
