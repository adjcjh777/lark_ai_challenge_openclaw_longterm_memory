# Day 4 Bitable Demo 讲解词

日期：2026-04-27  
场景：评委打开 Bitable 看板时的 3 分钟讲解

## 0. 开场

这张多维表格不是聊天记录备份，而是 Memory Engine 从协作信息里抽象出来的“可复用企业记忆台账”。  
评委可以从三张表快速看到：当前有效记忆、历史版本链、以及系统自证的 Benchmark 指标。

## 1. Memory Ledger

先看 `Memory Ledger`。这一张表一行对应一条当前记忆，核心字段是：

- `type`：这条记忆是什么类型，例如 decision、workflow、preference、deadline、risk。
- `subject`：记忆主题，例如生产部署、白皮书截止、Token 泄露风险。
- `current_value`：当前有效结论。
- `status`：当前是否 active。
- `version`：当前是第几个版本。
- `source`：这条记忆来自哪里。

讲解口径：

```text
这里展示的是系统当前相信的事实或规则。比如“生产部署”这条，不是把群聊原文全部存下来，而是沉淀成 workflow 类型的当前规则。评委看这个视图，可以直接判断系统是否真的把协作信息变成了可操作记忆。
```

推荐先切到这些视图：

- `Active Ledger`：只看当前有效记忆。
- `By Type`：按类型分组，展示 decision、workflow、preference、deadline、risk 的覆盖。
- `Recently Updated`：按更新时间倒序，展示刚刚同步的记忆。

## 2. Memory Versions

再看 `Memory Versions`。这一张表展示同一条记忆的版本链。

讲解口径：

```text
企业记忆和普通搜索最大的区别是会处理变更。旧规则不会被删除，而是变成 superseded；新规则成为 active。这样系统既不会召回过期规则，也保留了审计链路。
```

可以重点展示：

- `生产部署`：从 `cn-shanghai` 改成 `ap-shanghai`。
- `架构分层`：从 SQLite 单层存储改成 SQLite + Bitable 双层结构。
- `白皮书截止`：从 2026-05-02 提前到 2026-05-01。

推荐视图：

- `Version Chain`：按 `memory_id` 分组，按 `version` 升序。
- `By Version Status`：按 active / superseded 分组。

## 3. Benchmark Results

最后看 `Benchmark Results`。

讲解口径：

```text
这张表说明我们不是只做了一次人工演示，而是把抗干扰、冲突更新、旧值泄露和证据覆盖变成了可重复评测指标。当前 Day1 cases 的通过率是 1.0，旧值泄露率是 0.0。
```

重点字段：

- `case_count`
- `case_pass_rate`
- `conflict_accuracy`
- `stale_leakage_rate`
- `evidence_coverage`
- `avg_latency_ms`

## 4. 评委可能追问

### 为什么不是普通搜索？

普通搜索会返回相似内容；Memory Engine 返回当前有效结论。  
这里的 `status`、`version`、`supersedes_version_id` 证明系统知道旧规则已经被新规则覆盖。

### 为什么要放 Bitable？

Bitable 是评委和业务人员能直接看的审计台账。  
SQLite 保证本地 Demo 和 Benchmark 稳定，Bitable 负责可视化、审核和协作展示。

### 如果 Bitable 权限不可用怎么办？

核心能力不依赖 Bitable。  
`remember`、`recall`、`benchmark` 都在本地 SQLite 闭环；Bitable 同步默认 dry-run，只有显式 `--write` 才写入。

### 重复同步怎么办？

当前 Day4 为 append-only，同步目的是初赛展示。  
如果进入生产化，会增加基于 `memory_id`、`version_id`、`run_id` 的 upsert 或 record_id 映射。

## 5. 结束语

```text
这一页的价值是把“AI 记住了什么、为什么现在相信这个版本、系统是否经得起评测”同时展示出来。它不是一个日志表，而是企业记忆从产生、更新到自证的可视化台账。
```
