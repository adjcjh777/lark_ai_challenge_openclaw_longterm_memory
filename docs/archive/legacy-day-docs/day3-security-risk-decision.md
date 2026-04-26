# Day 3 Security Risk Decision

日期：2026-04-24

## 背景

Day 3 文档曾把真实飞书运行标识写入公开仓库文档，包括测试群 `chat_id`、Bot mention `open_id`、应用 `App ID`、测试群名称和一次 Demo `memory_id`。

当前仓库文件已经改为环境变量占位符：

- `FEISHU_APP_ID`
- `FEISHU_TEST_CHAT_ID`
- `FEISHU_BOT_OPEN_ID`

队友获取真实值的步骤已写入 `docs/teammate-lark-cli-setup.md`，真实值只应放在本机 `.env.local`。

## 历史扫描结果

使用 `git rev-list --all` + `git grep` 扫描 README 和 docs 后确认：

- 当前文件：未发现已知真实飞书标识。
- Git 历史：Day 3 提交中出现过测试群 `chat_id`、Bot mention `open_id`、测试群名称和 Demo `memory_id`。
- Git 历史：更早的队友配置文档提交中出现过应用 `App ID`。

这些标识不是 App Secret，不能直接登录或调用 API；但它们属于运行环境元数据，公开保留没有必要。

## 决策

当前采取非破坏性修复：

1. 当前公开文档全部改为占位符和环境变量。
2. 队友文档补充真实标识获取步骤。
3. 提交前持续用 `rg` 扫描真实长格式标识。

暂不自动执行 Git 历史重写，因为 history rewrite + force push 会改变远端提交图，可能影响队友已有 clone、分支和未同步工作。

## 什么时候需要重写历史

建议在以下任一条件成立时执行历史重写：

- 仓库将长期保持公开，且希望 GitHub 历史中也不可见这些运行标识。
- 后续发现泄露的不只是 App ID / chat_id / open_id，而是 App Secret、access token、refresh token 或私有文档链接。
- 比赛提交前需要做一次公开仓库 hygiene。

如果只有当前这批标识，风险等级为中低；若 App Secret 或 token 泄露，风险等级立即升为高，必须去飞书开放平台重置凭证。

## 若要彻底清理历史

需要项目负责人明确授权后执行：

```bash
git filter-repo --replace-text replacements.txt
git push --force-with-lease origin main
```

执行前必须：

1. 通知队友暂停 push。
2. 备份当前仓库。
3. 准备 replacement 文件，把真实 `oc_xxx`、`ou_xxx`、`cli_xxx`、真实群名和 Demo `memory_id` 替换为占位符。
4. force push 后通知队友重新 fetch / rebase 或重新 clone。

如果没有安装 `git-filter-repo`，不要临时手写复杂 history rewrite 命令；先安装官方工具或使用 GitHub 推荐流程。
