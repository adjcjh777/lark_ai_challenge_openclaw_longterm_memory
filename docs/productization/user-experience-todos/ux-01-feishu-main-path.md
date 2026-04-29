# UX-01：飞书主路径从命令集合升级为完整体验

日期：2026-04-29
负责人：程俊豪
状态：已完成
上游总览：[用户体验产品化 TODO 清单](../user-experience-todo.md)
执行顺序：第 1 个

## 本轮要做什么

把当前偏命令式的飞书入口整理成一条普通用户能走完的主路径：

```text
普通话输入
  -> OpenClaw Agent / Feishu live 层判断意图
  -> 调用本项目 fmc_* / memory.* 工具
  -> handle_tool_request()
  -> CopilotService
  -> 返回用户可读结果
  -> 用户确认、拒绝、查看来源、查看版本或进入任务前预取
```

这里的 candidate 指“待确认记忆”。真实飞书来源只能先进入 candidate，不能自动变成 active memory。

## 为什么现在做

当前系统已经有 `/remember`、`/confirm`、`/reject`、`/prefetch`、`/heartbeat` 和自然语言分流基础，但体验还像懂系统的人在操作工具。评委或真实用户不应该先理解 `candidate_id`、`memory_id`、`trace_id`，才能完成一次记忆确认或召回。

本轮重点是让飞书里的第一屏回答用户问题，并把工程字段放到审计详情里。

## 本阶段不用做

- 本阶段不用声明真实 Feishu DM 到本项目 first-class `fmc_*` / `memory.*` 工具链路 live E2E 已完成。
- 本阶段不用做生产部署、全量 Feishu workspace ingestion 或多租户后台。
- 本阶段不用绕过 `handle_tool_request()` / `CopilotService` 直接改 active memory。
- 本阶段不用把 legacy Bot 重新作为主入口。

## 执行任务

| 顺序 | 任务 | 文件位置 | 完成标准 |
|---|---|---|---|
| 1 | 固化飞书主路径脚本 | `docs/demo-runbook.md`、`docs/human-product-guide.md` | 搜索、候选确认、版本解释、任务前 prefetch 各有 1 条普通话输入、预期输出、失败 fallback 和 no-overclaim 边界。 |
| 2 | 让自然语言动作不要求用户输入内部 ID | `memory_engine/copilot/feishu_live.py`、`tests/test_copilot_feishu_live.py` | 用户说“确认这条”“不要记这个”“为什么旧值不用了”时，系统能在当前 chat/thread/reviewer context 下解析到最近候选或记忆；内部仍调用 `memory.confirm` / `memory.reject` / `memory.explain_versions`。 |
| 3 | 调整飞书主答案层级 | `memory_engine/copilot/feishu_live.py`、`memory_engine/feishu_cards.py` | 主答案先给结论、证据和下一步动作；`request_id`、`trace_id`、`permission_decision` 只进入审计详情或卡片底部。 |
| 4 | 锁住服务层调用路径 | `memory_engine/copilot/tools.py`、`memory_engine/copilot/service.py`、`tests/test_copilot_tools.py` | 搜索、候选、确认、拒绝、版本解释、prefetch 都经过 `handle_tool_request()` / `CopilotService`；缺失或畸形 permission 仍 fail closed。 |
| 5 | 更新交付说明 | `docs/productization/user-experience-todo.md`、新 handoff 或 `docs/demo-runbook.md` | 文档写清已完成能力、验证命令、失败情况和仍未完成的 live E2E 边界。 |

## 产品行为要求

### 搜索

用户输入：

```text
上次定的生产部署 region 是哪个？
```

期望主答案：

- 直接回答当前 active 结论。
- 给出 1 条 evidence quote。
- 说明如果旧值被覆盖，应去版本解释里看，不在默认答案里展示旧值。
- 审计详情保留 request / trace / permission metadata。

### 创建候选

用户输入：

```text
记住：生产部署必须加 --canary，region 用 ap-shanghai。
```

期望主答案：

- 说明已生成待确认记忆，不说“已经记住为最终结论”。
- 给出“确认”“拒绝”“查看来源”的用户动作。
- 不要求用户复制 `candidate_id` 才能完成下一步。

### 确认或拒绝

用户输入：

```text
确认这条
```

或：

```text
这个不要记
```

期望行为：

- 当前用户必须是 reviewer / owner / admin，否则拒绝。
- 系统内部定位当前上下文最近 candidate。
- 成功或失败都写审计。

### 版本解释

用户输入：

```text
为什么之前的 cn-shanghai 不用了？
```

期望行为：

- 调用 `memory.explain_versions`。
- 解释当前版本、旧版本、覆盖原因和证据。
- 默认搜索不泄漏 superseded 旧值。

### 任务前预取

用户输入：

```text
帮我准备今天上线前 checklist。
```

期望行为：

- 调用 `memory.prefetch`。
- 返回 compact context pack，不返回 raw events。
- 明确缺失信息和风险。

## 验收命令

代码实现后运行：

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_feishu_live tests.test_copilot_tools
python3 -m unittest tests.test_feishu_interactive_cards
python3 scripts/check_demo_readiness.py --json
git diff --check
ollama ps
```

如果本轮实际验证 OpenClaw Feishu websocket，再追加：

```bash
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
python3 scripts/check_openclaw_feishu_websocket.py --json --timeout 45
```

## 完成标准

- 普通用户不输入内部 ID，也能完成一次 candidate 确认或拒绝。
- 搜索、候选、版本解释、prefetch 四条主路径都能按脚本复现。
- 飞书主答案不被工程字段淹没。
- 所有状态改变仍经过 `CopilotService`。
- 文档不把测试群 sandbox、demo replay 或本机 staging 写成 production live。

## 失败处理

- 如果自然语言无法可靠定位最近 candidate，先保留命令 fallback，但主答案必须解释下一步怎么做。
- 如果 Feishu / lark-cli 写入失败，只能展示 dry-run payload，不声称真实空间已同步。
- 如果 OpenClaw websocket 状态不一致，把 `channels status`、gateway 日志和 health warning 分开记录，不直接写成 live E2E 完成。

## 顺序执行出口

完成 UX-01 后再进入 [UX-02 记忆卡片信息架构](ux-02-memory-card-information-architecture.md)。UX-02 会把本轮主路径里的返回内容沉淀成稳定卡片模板。

## 完成记录

完成时间：2026-04-29

已完成能力：

- `docs/demo-runbook.md` 和 `docs/human-product-guide.md` 已固化 4 条飞书主路径普通话脚本：搜索、候选确认、版本解释、任务前 prefetch。
- `memory_engine/copilot/feishu_live.py` 已支持“确认这条”“不要记这个”“为什么旧值不用了”在当前 chat / thread / reviewer context 下解析最近 candidate 或 memory。
- 内部状态变更仍调用 `memory.confirm`、`memory.reject`、`memory.explain_versions`，并继续通过 `handle_tool_request()` / `CopilotService`。
- 飞书主答案已调整为先给结论、证据和下一步动作；`request_id`、`trace_id`、`permission_decision` 放入审计详情。

验证命令：

```bash
python3 scripts/check_openclaw_version.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_feishu_live tests.test_copilot_tools
python3 -m unittest tests.test_feishu_interactive_cards
python3 scripts/check_demo_readiness.py --json
git diff --check
ollama ps
```

失败 fallback：

- 如果当前上下文无法可靠定位最近 candidate，回复里保留 `/confirm <candidate_id>` 或 `/reject <candidate_id>` fallback。
- 如果当前上下文无法定位最近 memory，版本解释保留 `/versions <memory_id>` fallback，并建议先搜索具体主题。
- 如果 permission 缺失、畸形或 reviewer 权限不足，继续 fail closed，不展示未授权内容。

仍未完成边界：

- 这不是生产部署。
- 这不是全量 Feishu workspace ingestion。
- 这不代表真实 Feishu DM 已稳定路由到本项目 first-class `fmc_*` / `memory.*` live E2E。
- 这不代表 productized live 长期运行已完成。
