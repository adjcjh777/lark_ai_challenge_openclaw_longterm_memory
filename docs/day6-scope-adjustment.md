# Day 6 Scope Adjustment

日期：2026-04-25

目标日期：2026-04-29

说明：本轮是提前执行 D6。4 月 29 日主题直播尚未开始，因此所有“直播后范围校准”只记录为待复核项；本轮不基于尚未发生的直播做结论。

## 当前范围结论

初赛必须闭环的内容：

- Memory 定义与架构白皮书：突出“企业记忆 = 当前有效结论 + 版本状态 + 来源证据 + 覆盖关系”。
- 可运行 Demo：继续使用飞书 Bot 的 `/remember`、`/recall`、`/versions`、`/ingest_doc`、`/confirm`、`/reject`。
- 自证 Benchmark Report：继续保持 Day 1 和 Day 5 的可复现 benchmark，D7 再扩容抗干扰数据集。
- 飞书交互表达：D6 初赛范围采用结构化文本卡片，字段必须包含结论、理由、状态、版本、来源、是否被覆盖。
- 安全边界：回复中不展示敏感 token、secret、完整内部链接；文档 token 和消息 ID 只展示截断形态。

推迟到复赛或直播后再决定的内容：

- 真实飞书交互卡片按钮回调的完整闭环。
- H5 命令面板、聊天框加号菜单、消息快捷操作等产品化入口。
- 流式卡片、复杂图表卡片、批量候选确认 UI。
- 企业级 allowlist 管理台和细粒度管理员配置。
- 完整 memory 内容安全扫描拦截链路；D6 只完成设计说明和回复层红线。

## P0 完成情况

- 已将 Bot 回复升级为“卡片化结构化文本”：
  - `记忆确认卡片`
  - `历史决策卡片`
  - `矛盾更新卡片`
  - `待确认记忆卡片`
- 卡片字段包含：结论、理由、状态、版本、来源、是否被覆盖。
- `unknown_command` 回复展示命令白名单，降低非预期命令误处理风险。
- 重复消息仍会返回 duplicate 提示，不重复写入。
- 召回和记忆回复加入敏感信息遮挡：
  - `*_TOKEN`、`*_SECRET`、`*_PASSWORD`、`*_CREDENTIAL`、`*_API_KEY`
  - `feishu_`、`lark_`、`sk_`、`pat_`、`ghp_` 等长 token 形态
  - `internal`、`corp`、`bytedance` 域名下的完整 URL
- 当前生产路径仍默认发送纯文本结构化卡片；这是 D6 的低风险选择。飞书 JSON card 已提供源码样例，后续若启用真实 interactive card，失败时应继续回落到当前纯文本。

## P1 加码完成情况

- 文档 ingestion 回复增加低置信候选提示：`confidence < 0.70` 的候选会标记“需人工确认”。
- 矛盾更新回复展示专门的“旧规则 -> 新规则”字段。
- 新增 `memory_engine/feishu_cards.py`，可生成历史决策卡片和矛盾更新卡片 JSON。
- 已记录命令入口调研结论：后端 Bot 不能实现输入中 slash 候选；初赛保留 `/help` + 结构化卡片，复赛再评估卡片按钮、H5、加号菜单或消息快捷操作。
- 已记录 memory 内容安全扫描设计，参考 Hermes `tools/memory_tool.py` 的 prompt injection、secret/exfil、不可见字符三类风险。

## 命令入口调研结论

当前项目的 Bot 后端能处理“消息发送后”的事件，不能控制用户正在输入时的 slash command palette。总控计划中的判断仍成立：初赛不追求 Codex/Claude Code 式实时输入候选。

可提前落地的替代方案：

- `/help`：作为最低风险命令发现入口，已经可用。
- 卡片按钮：适合候选确认、拒绝、查看版本链；需要接入 interactive card action callback，放到复赛或直播后确认。
- H5 命令面板：适合批量管理 memory、查看证据链；初赛非必须。
- 聊天框加号菜单或消息快捷操作：可能成为产品化入口，但需要在开放平台后台确认可配置项和审核要求。

参考入口：

- 飞书卡片概述：https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/feishu-card-overview
- 飞书客户端 H5 能力：https://open.feishu.cn/document/client-docs/h5/
- 飞书 CLI 消息发送能力：`lark-cli im +messages-send --help` 显示 `--msg-type` 支持 `interactive`，但本项目 D6 不默认启用真实卡片发送。

## Memory 内容安全扫描设计

D6 先做设计和展示层红线，D7 以后再决定是否在写入层强拦截。

第一阶段扫描三类风险：

| 风险 | 例子 | D6 处理 | 后续建议 |
| --- | --- | --- | --- |
| Prompt injection | `ignore previous instructions`、`you are now...` | 文档记录，暂不强拦截 | 写入前阻断或降级为 candidate |
| Secret / exfil | `API_TOKEN=...`、`curl ${SECRET}`、读取 `.env` | 回复层遮挡敏感值 | 写入前扫描，命中则拒绝或要求人工确认 |
| 不可见字符 | U+200B、U+202E 等 | 文档记录，测试后再启用 | 标记为 unsafe candidate |

参考 Hermes 做法：

- `tools/memory_tool.py` 在写入前扫描 prompt injection、exfil、不可见字符。
- 命中风险时返回失败，不让内容进入会被注入 system prompt 的 memory。
- 本项目初赛 memory 不直接注入系统提示词，但仍要防止 Demo 截图泄漏 secret 或内部链接。

## 卡片字段标准

历史决策卡片：

```text
历史决策卡片：当前有效结论是 生产部署必须加 --canary --region ap-shanghai

类型：记忆召回
卡片：历史决策卡片
结论：生产部署必须加 --canary --region ap-shanghai
理由：按主题匹配 active 记忆，并返回最新有效版本
主题：生产部署
状态：active
版本：v2
来源：当前飞书消息 / om_d...date
是否被覆盖：否（当前 active 版本）
记忆类型：workflow
当前有效规则：生产部署必须加 --canary --region ap-shanghai
memory_id：mem_demo_day6
证据：不对，生产部署 region 改成 ap-shanghai
```

矛盾更新卡片：

```text
矛盾更新卡片：旧规则已被新规则覆盖。

类型：记忆更新
卡片：矛盾更新卡片
结论：不对，生产部署 region 改成 ap-shanghai
理由：来自当前指令和证据链
主题：生产部署
状态：active
版本：v2
来源：当前飞书消息
是否被覆盖：否（这是当前有效版本）
旧规则 -> 新规则：生产部署必须加 --canary --region cn-shanghai -> 不对，生产部署 region 改成 ap-shanghai
旧版本状态：superseded
记忆类型：workflow
处理结果：旧版本已标记为 superseded，新版本已生效。
memory_id：mem_demo_day6
```

## 飞书卡片 JSON 源码样例

历史决策卡片：

```json
{
  "config": {
    "wide_screen_mode": true
  },
  "header": {
    "template": "blue",
    "title": {
      "tag": "plain_text",
      "content": "历史决策卡片"
    }
  },
  "elements": [
    {
      "tag": "div",
      "fields": [
        {
          "is_short": false,
          "text": {
            "tag": "lark_md",
            "content": "**结论**\n生产部署必须加 --canary --region ap-shanghai"
          }
        },
        {
          "is_short": false,
          "text": {
            "tag": "lark_md",
            "content": "**理由**\n按主题召回 active 版本，并返回最新证据"
          }
        },
        {
          "is_short": true,
          "text": {
            "tag": "lark_md",
            "content": "**状态**\nactive"
          }
        },
        {
          "is_short": true,
          "text": {
            "tag": "lark_md",
            "content": "**版本**\nv2"
          }
        },
        {
          "is_short": true,
          "text": {
            "tag": "lark_md",
            "content": "**来源**\n当前飞书消息 / om_d...date"
          }
        },
        {
          "is_short": true,
          "text": {
            "tag": "lark_md",
            "content": "**是否被覆盖**\n否（当前 active 版本）"
          }
        },
        {
          "is_short": true,
          "text": {
            "tag": "lark_md",
            "content": "**memory_id**\nmem_demo_day6"
          }
        }
      ]
    },
    {
      "tag": "hr"
    },
    {
      "tag": "div",
      "text": {
        "tag": "lark_md",
        "content": "这是一条企业记忆卡片：它展示当前有效结论、版本状态和证据来源，而不是普通聊天摘要。"
      }
    }
  ]
}
```

矛盾更新卡片：

```json
{
  "config": {
    "wide_screen_mode": true
  },
  "header": {
    "template": "orange",
    "title": {
      "tag": "plain_text",
      "content": "矛盾更新卡片"
    }
  },
  "elements": [
    {
      "tag": "div",
      "fields": [
        {
          "is_short": false,
          "text": {
            "tag": "lark_md",
            "content": "**结论**\n生产部署必须加 --canary --region ap-shanghai"
          }
        },
        {
          "is_short": false,
          "text": {
            "tag": "lark_md",
            "content": "**理由**\n用户使用“不对/改成”明确覆盖旧规则"
          }
        },
        {
          "is_short": true,
          "text": {
            "tag": "lark_md",
            "content": "**状态**\nactive"
          }
        },
        {
          "is_short": true,
          "text": {
            "tag": "lark_md",
            "content": "**版本**\nv2"
          }
        },
        {
          "is_short": true,
          "text": {
            "tag": "lark_md",
            "content": "**来源**\n当前飞书消息 / om_d...date"
          }
        },
        {
          "is_short": true,
          "text": {
            "tag": "lark_md",
            "content": "**是否被覆盖**\n否（旧规则已 superseded）"
          }
        },
        {
          "is_short": true,
          "text": {
            "tag": "lark_md",
            "content": "**memory_id**\nmem_demo_day6"
          }
        }
      ]
    },
    {
      "tag": "div",
      "text": {
        "tag": "lark_md",
        "content": "**旧规则 -> 新规则**\n生产部署必须加 --canary --region cn-shanghai -> 生产部署必须加 --canary --region ap-shanghai"
      }
    },
    {
      "tag": "hr"
    },
    {
      "tag": "div",
      "text": {
        "tag": "lark_md",
        "content": "这是一条企业记忆卡片：它展示当前有效结论、版本状态和证据来源，而不是普通聊天摘要。"
      }
    }
  ]
}
```

## 直播后待复核

4 月 29 日直播结束后需要补一轮小修：

- 是否有新的初赛硬性要求。
- 评分是否更偏 Demo、白皮书、Benchmark 或飞书生态集成。
- 卡片标题和字段名是否需要改成更贴近评委语言。
- 是否值得把真实 interactive card 作为初赛展示项，而不是只保留 JSON 样例。
