# 2026-05-05 Implementation Plan

阶段：白皮书  
主控：`docs/feishu-memory-copilot-implementation-plan.md`

## 当日目标

创建或重写《Memory 定义与架构白皮书》，让初赛材料能回答 Define it、Build it、Prove it，并把 OpenClaw-native Copilot 主线讲清楚。

## 用户白天主线任务

1. 创建或更新 `docs/memory-definition-and-architecture-whitepaper.md`。
2. 先讲问题背景和记忆定义，再讲为什么这个架构有效。
3. 覆盖 Memory 状态机、证据链、OpenClaw 入口、飞书生态、安全权限、Benchmark 证明。
4. 把 CLI/Bot/Bitable/ingestion 解释为 adapter / fallback / demo surface，不作为主架构。
5. 加入局限和 2026-05-07 之后的复赛路线。

## 需要改/新增的文件

- `docs/memory-definition-and-architecture-whitepaper.md`
- `docs/diagrams/*.mmd`，如需要更新图
- `docs/benchmark-report.md`，如需要引用最新指标
- `docs/demo-runbook.md`，如需要补演示对应关系

## 测试

```bash
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```

文档自查：

- 每个核心判断是否有 Demo 或 Benchmark 证据。
- 是否避免把产品描述成单纯 OpenClaw 插件、Skill 或 npm 包。
- 是否明确不把所有聊天塞进向量库。

## 验收标准

- 白皮书不只是提纲，可以直接作为初赛材料初稿。
- 章节顺序符合：背景/记忆定义 -> 架构设计 -> 当前实现对应关系 -> Benchmark/Demo 证明 -> 风险和后续。
- 权限、安全、证据、版本链、主动提醒都有明确说明。

## 队友晚上补位任务

1. 从非工程评委视角读白皮书，标出看不懂的术语。
2. 润色“为什么不是普通搜索”和“企业价值”段落。
3. 标注需要截图或图表补强的位置。

今晚不用做：

- 不用写论文式长段落。
- 不用新增代码。

