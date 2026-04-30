# LLM 主导企业记忆治理蓝图

日期：2026-04-30
状态：执行蓝图，写完即按顺序落地
事实源优先级：当前代码 > 本文档 > 旧 handoff / 旧计划

## 1. 问题定义

当前 Feishu Memory Copilot 的“是否记忆”和“如何抽取”主要依赖规则：

- 群聊入口分流：`memory_engine/copilot/feishu_live.py`
- 候选判定与冲突治理：`memory_engine/copilot/governance.py`
- 文本抽取：`memory_engine/extractor.py`
- 信号词与主题规则：`memory_engine/models.py`

这套规则可以跑通 demo，但不符合目标产品形态。主要问题：

1. 对真实企业表达过于僵硬，依赖关键词。
2. subject 抽取粗糙，复合句容易失真。
3. OpenClaw 主链路和 repo 主链路容易漂移，真实测试群里 `/remember` 仍可能落回 OpenClaw 自行写 markdown 的 fallback。
4. 治理层承担了过多“语义判断”职责，导致规则越来越厚。

目标改成：

```text
LLM 负责：
- 这句话是否值得沉淀为企业记忆
- 应该抽成什么结构

规则负责：
- 权限
- candidate-only
- duplicate / conflict
- 状态机
- owner / reviewer / admin
- 审计
```

## 2. 目标架构

### 2.1 总体链路

```text
Feishu / OpenClaw message
  -> lightweight routing / filtering
  -> LLM candidate judge + structured extraction
  -> CopilotGovernance
  -> candidate / duplicate / conflict
  -> confirm / reject / owner-review / audit
```

### 2.2 分层职责

#### L0: 轻量预过滤

保留确定性过滤，不做语义主判断：

- bot 自己的消息
- 空消息
- 纯噪声/纯表情
- 不在 allowlist 的 chat
- 重复 message_id
- 明显系统事件

#### L1: LLM Candidate Judge

新增一个最小模块，输入：

- 当前消息文本
- 少量上下文（chat/thread/topic/source）
- 可选历史 active memory 摘要

输出结构化 JSON：

```json
{
  "should_create_candidate": true,
  "confidence": 0.86,
  "memory_type": "workflow",
  "subject": "生产部署上线窗口",
  "current_value": "上线窗口固定为每周四下午，回滚负责人是程俊豪，截止周五中午。",
  "summary": "上线窗口与负责人规则",
  "reason": "这是未来会重复使用的团队执行规则",
  "risk_flags": [],
  "is_question": false,
  "needs_human_confirmation": true
}
```

#### L2: Governance

`governance.py` 不再主导“像不像记忆”的语义判断，而是负责：

- 校验 LLM 输出结构
- 权限 fail closed
- duplicate / conflict
- candidate-only
- evidence 记录
- 状态机
- 审计

## 3. 实施顺序

### Phase 1：修 OpenClaw 主链路硬路由

目标：真实测试群里的 `/remember` 不再落到 OpenClaw 自行写 markdown fallback，而是**强制**进入 repo 的 `fmc_memory_create_candidate -> CopilotService`。

范围：

- `.openclaw` 的 Feishu runtime / routing
- `/remember` 命令级拦截
- 正确构造 `current_context.permission`

完成标准：

- 真实测试群发 `/remember ...` 时，不再出现 `已记录 ✅` 的 markdown fallback
- 能直接返回 repo 链路的 candidate review interactive card
- 失败时暴露真实 tool error，不伪装成功

### Phase 2：引入 repo 内 LLM Candidate Judge 最小骨架

目标：在 repo 内新增 `llm_candidate_judge.py`，先让被动群聊探测和主动 `/remember` 共用同一套 LLM assessment 输出结构。

范围：

- 新增 judge 模块
- 设计 prompt + JSON schema
- 失败时可 conservative fallback 到旧规则

完成标准：

- judge 可被单测调用
- 输出结构稳定
- 不改权限层

### Phase 3：治理层收缩

目标：让 `governance.py` 从“主判断器”退化为“安全治理器”。

范围：

- `_has_candidate_signal()` 降级
- `extractor.py` 从主线退成 fallback / normalization helper
- `governance.py` 改为消费 assessment

完成标准：

- 新旧链路不重复判断
- duplicate / conflict / risk / state machine 不回归

### Phase 4：评测与真实表达扩样

目标：让 benchmark 评测的核心不再是关键词规则，而是企业记忆判断质量。

范围：

- `benchmarks/copilot_candidate_cases.json`
- `benchmarks/copilot_real_feishu_cases.json`
- 口语正负样本
- 问句负样本
- 多轮改口 conflict

完成标准：

- 新增样本覆盖真实企业表达
- 失败样本保留，不删

## 4. 文件边界

### repo 内

- `memory_engine/copilot/feishu_live.py`
- `memory_engine/copilot/governance.py`
- `memory_engine/extractor.py`
- `memory_engine/models.py`
- `memory_engine/copilot/schemas.py`
- `tests/test_copilot_feishu_live.py`
- `tests/test_copilot_governance.py`
- `tests/test_copilot_tools.py`
- `benchmarks/copilot_candidate_cases.json`
- `benchmarks/copilot_real_feishu_cases.json`

### OpenClaw 本机运行时

- `~/.openclaw/workspace/AGENTS.md`
- `~/.openclaw/plugin-runtime-deps/openclaw-2026.4.24-*/dist/extensions/feishu/*.js`

说明：
第一阶段会触达 `~/.openclaw` 下的本机运行时代码，因为当前真实测试群 bot 主链路仍在这里。

## 5. 非目标

本轮不做：

- 全量 workspace ingestion
- 真实飞书来源自动 active
- 多租户后台
- 把所有治理逻辑交给 LLM 黑盒
- 直接删掉全部旧规则

## 6. 第一阶段执行口径

接下来立刻执行：

1. 修 OpenClaw 测试群 `/remember` 硬路由。
2. 跑真实测试群消息。
3. 只有在真实群里不再出现 `已记录 ✅` fallback 后，才进入 repo 内 LLM judge 实现。

## 7. 验证原则

每次代码改动后都做一次真实测试群验证。

最小验证组合：

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
git diff --check
```

如果改 repo Python 代码，再跑：

```bash
python3 -m unittest tests.test_copilot_feishu_live tests.test_copilot_governance
```

如果改 OpenClaw / Feishu runtime 主链路，再做：

- 真实测试群发一条新的 `@Bot /remember ...`
- 读回群消息
- 读回 gateway / session 日志
