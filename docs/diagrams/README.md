# 项目原型图源码

本目录保存 Feishu Memory Engine 项目的 Mermaid 图源码，避免依赖 Figma 临时链接或免费账号空间限制。

评委现场优先从 [../judge-10-minute-experience.md](../judge-10-minute-experience.md) 进入；本目录只提供架构、交互和 benchmark loop 的可渲染源码，不代表 production live 已完成。

## 图列表

- [项目原型总览](project-overview.mmd)
- [产品交互流程](product-interaction-flow.mmd)
- [系统架构图](system-architecture.mmd)
- [评测闭环图](benchmark-loop.mmd)

## UX-07 现场使用顺序

| 顺序 | 图 | 用途 |
|---|---|---|
| 1 | [系统架构图](system-architecture.mmd) | 讲 OpenClaw Agent、memory tools、Copilot Core、governance / retrieval / audit 的关系 |
| 2 | [产品交互流程](product-interaction-flow.mmd) | 讲用户如何完成搜索、候选确认、版本解释和任务前 prefetch |
| 3 | [评测闭环图](benchmark-loop.mmd) | 讲样本、runner、指标、失败分类和修复闭环 |

## 使用方式

可直接在支持 Mermaid 的 Markdown / GitHub / 飞书文档 / Mermaid Live Editor 中渲染。

如需导出为 SVG 或 PNG，可使用 Mermaid CLI：

```bash
npx @mermaid-js/mermaid-cli -i docs/diagrams/project-overview.mmd -o docs/diagrams/project-overview.svg
```

当前阶段建议优先维护 `.mmd` 源码，导出图片作为白皮书或 PPT 素材时再生成。
