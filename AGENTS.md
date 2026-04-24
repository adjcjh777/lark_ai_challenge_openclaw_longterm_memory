# 飞书文档参考
## 开发指南 https://open.feishu.cn/document/client-docs/intro
## 开发教程 https://open.feishu.cn/document/course
## 服务端api https://open.feishu.cn/document/ukTMukTMukTM/ukDNz4SO0MjL5QzM/AI-assistant-code-generation-guide
## 客户端 api https://open.feishu.cn/document/client-docs/h5/
## 飞书 cli https://open.feishu.cn/document/mcp_open_tools/feishu-cli-let-ai-actually-do-your-work-in-feishu
## 飞书 openclaw 官方插件 https://bytedance.larkoffice.com/docx/MFK7dDFLFoVlOGxWCv5cTXKmnMh

# 执行规则
## 本地已经安装了 lark_cli (https://github.com/larksuite/cli), 可以直接使用 `lark-cli` 命令，这是最重要的工具！！！！
## 飞书 openclaw 插件 （https://github.com/larksuite/openclaw-lark），如果需要的话可以直接安装并使用！！！！

## 版本维护与推送规则
### 每完成一个可运行闭环、阶段交付或关键文档更新后，必须执行本地验证、提交并推送到远程仓库。
### 提交前必须检查 `git status --short`，确认 `.env`、`.omx/`、数据库文件、缓存文件和临时报告不会进入提交。
### 代码变更提交前至少运行：
```bash
python3 -m compileall memory_engine scripts
python3 -m memory_engine benchmark run benchmarks/day1_cases.json
```
### 只提交与当前任务相关的文件；不要回退或覆盖他人已有改动。
### commit message 采用“为什么做这次变更”作为首行，并在正文中记录验证情况，例如：
```text
Deliver local Day 1 memory engine loop

Implemented the local remember/recall/conflict/benchmark path so the project has a runnable baseline before Feishu Bot integration.

Tested: python3 -m compileall memory_engine scripts
Tested: python3 -m memory_engine benchmark run benchmarks/day1_cases.json
Not-tested: real Feishu Bot / Bitable integration, planned for Day 2
```
### 提交后推送当前分支到 `origin`：
```bash
git push origin HEAD
```
### 如果推送失败，先读取错误信息并处理可恢复问题；不要使用 destructive git 命令。
