# 项目原型图源码

本目录保存 Feishu Memory Engine 项目的 Mermaid 图源码，避免依赖 Figma 临时链接或免费账号空间限制。

## 图列表

- [项目原型总览](project-overview.mmd)
- [产品交互流程](product-interaction-flow.mmd)
- [系统架构图](system-architecture.mmd)
- [评测闭环图](benchmark-loop.mmd)

## 使用方式

可直接在支持 Mermaid 的 Markdown / GitHub / 飞书文档 / Mermaid Live Editor 中渲染。

如需导出为 SVG 或 PNG，可使用 Mermaid CLI：

```bash
npx @mermaid-js/mermaid-cli -i docs/diagrams/project-overview.mmd -o docs/diagrams/project-overview.svg
```

当前阶段建议优先维护 `.mmd` 源码，导出图片作为白皮书或 PPT 素材时再生成。

