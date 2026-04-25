# Day 6 Handoff

日期：2026-04-25

目标日期：2026-04-29

说明：这是提前执行 D6。4 月 29 日主题直播尚未开始，因此直播相关范围校准只记录为待复核项；本轮不臆造直播结论。

## 今日目标

D6 目标是完成主题直播后范围校准与卡片化表达。由于直播未开始，本轮跳过直播内容，优先完成 P0，并继续做 P1 加码。

P0：

- 更新 `docs/day6-scope-adjustment.md`，明确初赛进入范围和复赛延后范围。
- 将 Bot 文本回复升级为“历史决策卡片”的结构化表达。
- 卡片字段包含结论、理由、状态、版本、来源、是否被覆盖。
- 检查安全措辞，避免展示敏感 token、secret、完整内部链接。
- 参考 Hermes Feishu gateway，补 `docs/day6-hermes-feishu-gateway-notes.md`。
- 在现有 handler 中做低风险增强：命令白名单、重复消息提示、文本 fallback。

P1：

- 低置信候选记忆增加人工确认提示。
- 矛盾更新生成“旧规则 -> 新规则”卡片。
- 增加飞书卡片 JSON 源码样例。
- 调研命令入口，确认初赛仍使用 `/help` 作为 slash command palette 替代。
- 增加 memory 内容安全扫描设计说明。

## 已完成代码能力

- 扩展 `memory_engine/feishu_messages.py`：
  - 新增 `SUPPORTED_COMMANDS` 命令白名单。
  - 记忆确认、召回、矛盾更新、待确认记忆统一输出卡片字段。
  - 召回回复输出 `卡片：历史决策卡片`。
  - 矛盾更新回复输出 `卡片：矛盾更新卡片` 和 `旧规则 -> 新规则`。
  - ingestion 候选展示 confidence，低于 `0.70` 时提示人工确认。
  - 对 secret/token/内部 URL 做回复层遮挡。
- 扩展 `memory_engine/repository.py`：
  - supersede 结果返回旧规则内容、旧版本号和旧版本状态，供矛盾更新卡片展示。
- 新增 `memory_engine/feishu_cards.py`：
  - `build_decision_card(...)`
  - `build_update_card(...)`
  - 生成后续可发送为 interactive message 的 JSON card payload。
- 新增 `tests/test_feishu_day6.py`：
  - 验证历史决策卡片字段完整。
  - 验证 secret/token 回复遮挡。
  - 验证矛盾更新卡片展示旧规则到新规则。
  - 验证未知命令展示白名单。
  - 验证 JSON card builder 包含核心字段。

## 已完成文档

- `docs/day6-scope-adjustment.md`
  - 明确初赛范围：白皮书、可运行 Demo、Benchmark、结构化文本卡片、安全表达。
  - 明确复赛延后：真实卡片按钮回调、H5、加号菜单、消息快捷操作、流式卡片、完整安全扫描拦截链路。
  - 记录命令入口调研结论。
  - 记录 memory 内容安全扫描设计。
  - 附历史决策卡片和矛盾更新卡片文本样例。
  - 附飞书卡片 JSON 源码样例。
- `docs/day6-hermes-feishu-gateway-notes.md`
  - 提炼 @mention gating、消息去重、allowlist、每 chat 串行处理、卡片事件 fallback、回复失败 fallback、自发消息过滤、内容安全扫描。
  - 明确 D6 吸收项和拒绝项。
  - 说明后续落地顺序。

## Demo 推荐输入

群聊：

```text
@Feishu Memory Engine bot /remember 生产部署必须加 --canary --region cn-shanghai
@Feishu Memory Engine bot /recall 生产部署参数
@Feishu Memory Engine bot /remember 不对，生产部署 region 改成 ap-shanghai
@Feishu Memory Engine bot /recall 生产部署 region
@Feishu Memory Engine bot /unknown 生产部署
```

单聊机器人时可以省略 `@Feishu Memory Engine bot`。

预期亮点：

- `/recall` 返回历史决策卡片字段。
- 第二次 `/remember` 返回矛盾更新卡片，显示旧规则到新规则。
- `/unknown` 返回命令白名单。
- 如果输入包含 `API_TOKEN=...`，回复中会显示为 `[REDACTED]`。

## 命令入口结论

初赛继续采用：

- `/help` 展示可用命令和 Demo 推荐输入。
- 结构化文本卡片作为截图主承载。
- JSON card builder 作为后续 interactive card 的源码基础。

暂不做：

- 实时 slash 候选 UI。
- 真实卡片按钮回调。
- H5 命令面板。
- 聊天框加号菜单或消息快捷操作。

原因：当前 Bot handler 只能处理已发送消息事件，不能控制用户输入中的候选面板；真实产品入口需要开放平台后台配置和审核确认。

## 验证结果

已通过：

```bash
python3 -m compileall memory_engine scripts
python3 -m unittest discover -s tests
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
python3 -m memory_engine benchmark ingest-doc benchmarks/day5_ingestion_cases.json
```

全量单测：

- `17 tests OK`

Day 1 benchmark：

- `case_count = 10`
- `case_pass_rate = 1.0`
- `conflict_accuracy = 1.0`
- `evidence_coverage = 1.0`
- `stale_leakage_rate = 0.0`

Day 5 ingestion benchmark：

- `case_count = 2`
- `case_pass_rate = 1.0`
- `avg_candidate_count = 5.0`
- `avg_quote_coverage = 1.0`
- `avg_noise_rejection_rate = 1.0`
- `document_evidence_coverage = 1.0`

## 队友今晚任务

1. 从评委视角检查卡片字段：是否一眼看出“这是企业记忆，不是聊天摘要”。
2. 在飞书测试群跑一遍 Demo 推荐输入，并截取 `/recall` 和矛盾更新卡片。
3. 检查 `docs/day6-scope-adjustment.md` 的初赛/复赛边界是否过宽。
4. 如果直播后有新要求，在本 handoff 后追加“直播后复核”小节。

## 未验证项

- 4 月 29 日主题直播尚未发生，直播要求和评分偏好未复核。
- 真实飞书 interactive card 未启用；D6 只提供 JSON 源码样例和结构化文本 fallback。
- 内容安全扫描还未做写入前强拦截；当前只做回复层遮挡和后续设计说明。
- 未在真实飞书群聊重新跑 Day6 全链路；本轮先完成本地 replay/unit/benchmark 验证。
