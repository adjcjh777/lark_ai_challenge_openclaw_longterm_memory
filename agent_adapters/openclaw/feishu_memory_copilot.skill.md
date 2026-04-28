# Feishu Memory Copilot Skill

用途：让 OpenClaw Agent 在飞书项目协作里主动使用团队记忆，而不是只做普通聊天记录搜索。

## 什么时候调用记忆工具

- 用户询问历史决策、负责人、截止时间、部署参数、流程规则或风险结论时，先调用 `fmc_memory_search`。
- 用户说”记住””请记一下””以后都按””统一改成”时，调用 `fmc_memory_create_candidate`，不要绕过候选和证据检查。
- 用户确认候选记忆时，调用 `fmc_memory_confirm`；用户否认时，调用 `fmc_memory_reject`。
- 用户问”为什么现在是这个结论””旧规则是什么””谁改过”时，调用 `fmc_memory_explain_versions`。
- 生成 checklist、周报、计划、会议准备或任务拆解前，调用 `fmc_memory_prefetch`。

## 调用原则

1. `scope` 必须来自当前项目、飞书线程或用户明确指定的范围，例如 `project:feishu_ai_challenge`。
2. 默认只把 `active` memory 当成当前答案。
3. 输出给用户时必须带当前结论、来源证据、状态和版本。
4. `candidate`、`rejected`、`superseded` 不应作为当前结论，除非用户正在看审核队列或版本解释。
5. 包含 secret、token、内部链接或高风险敏感信息时，停止主动提醒，只生成人工复核候选。

## Progressive Disclosure

最常用：

- `fmc_memory_search`
- `fmc_memory_create_candidate`
- `fmc_memory_prefetch`

需要用户确认时再使用：

- `fmc_memory_confirm`
- `fmc_memory_reject`

追溯原因时再使用：

- `fmc_memory_explain_versions`

## 示例

历史决策召回：

```json
{
  "tool": "fmc_memory_search",
  "arguments": {
    "query": "production deploy region",
    "scope": "project:feishu_ai_challenge",
    "top_k": 3
  }
}
```

任务前预取：

```json
{
  "tool": "fmc_memory_prefetch",
  "arguments": {
    "task": "deployment_checklist",
    "scope": "project:feishu_ai_challenge",
    "current_context": {
      "user_intent": "prepare today's deployment checklist",
      "thread_id": "feishu-thread-demo"
    },
    "top_k": 5
  }
}
```
