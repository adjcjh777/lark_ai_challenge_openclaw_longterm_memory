# Feishu Single Listener Handoff

日期：2026-04-28  
状态：已完成测试流程修复；真实 OpenClaw Agent runtime evidence 仍待补。

## 先看这个

1. 今天修的是 OpenClaw 接飞书时暴露出的流程问题：同一个 `Feishu Memory Engine bot` 不能同时被 legacy listener、repo 内 lark-cli listener 和 OpenClaw Feishu websocket 消费。
2. 已新增单监听 preflight；repo 内两个启动入口启动前都会检查冲突，direct `python3 -m memory_engine ... listen` 也会检查。
3. 下一步如果继续 Phase B，先让 OpenClaw Feishu websocket 单独 owns the bot，再把三条真实 Agent runtime flow 写入 `docs/productization/openclaw-runtime-evidence.md`。
4. 判断做对：`python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket` 能说明当前没有 lark-cli listener 冲突；如果只看到泛化 `openclaw-gateway`，repo 内 lark-cli planned listener 会 fail closed，只有 OpenClaw planned owner 可以继续再做 channel / log 验证；`tests.test_feishu_listener_guard` 和 `tests.test_copilot_feishu_live` 通过。
5. 遇到问题记录：冲突进程 pid、kind、command，最后选择哪个监听，以及是否仍保留 `openclaw-gateway` 运行。

## 本阶段做了什么

- 新增 `memory_engine/feishu_listener_guard.py`：识别 repo 内 Copilot listener、legacy listener、直接 `lark-cli event +subscribe`、可识别的 OpenClaw Feishu websocket，并在冲突时 fail fast。
- 新增 `scripts/check_feishu_listener_singleton.py`：手动 preflight 命令，支持 `openclaw-websocket`、`copilot-lark-cli`、`legacy-lark-cli` 三种计划监听。
- 更新 `memory_engine/copilot/feishu_live.py` 和 `memory_engine/feishu_runtime.py`：direct listen 启动前也走单监听检查。
- 更新 `scripts/start_copilot_feishu_live.sh` 和 `scripts/start_feishu_bot.sh`：脚本入口启动前先跑 singleton preflight。
- 新增 `tests/test_feishu_listener_guard.py`：覆盖进程识别、冲突判断、OpenClaw websocket 冲突、generic `openclaw-gateway` 对 repo lark-cli planned listener fail closed、对 OpenClaw planned owner warning 不阻断。
- 新增 `docs/productization/feishu-staging-runbook.md`：把 OpenClaw websocket / Copilot lark-cli sandbox / legacy fallback 三选一写清。
- 同步 `README.md`、`full-copilot-next-execution-doc.md` 和 PRD gap tasks，避免后续验收再同时开启多个监听。

## 怎么继续 Phase B

如果 OpenClaw Feishu websocket owns the bot：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
```

然后只在 OpenClaw Agent 里跑：

1. 历史决策召回：触发 `memory.search`。
2. 候选确认：触发 `memory.create_candidate`，再触发 `memory.confirm` 或 `memory.reject`。
3. 任务前上下文：触发 `memory.prefetch`。

把证据写到 `docs/productization/openclaw-runtime-evidence.md`。不要同时启动 `scripts/start_copilot_feishu_live.sh`、`scripts/start_feishu_bot.sh` 或直接 `lark-cli event +subscribe`。

## 本阶段验证

已运行：

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_feishu_listener_singleton.py --planned-listener openclaw-websocket
python3 -m unittest tests.test_feishu_listener_guard tests.test_copilot_feishu_live
```

结果摘要：

- OpenClaw version OK：`2026.4.24`。
- 当前机器能看到 `openclaw-gateway` 运行；preflight 提示它无法从进程名判断 Feishu websocket 是否启用。repo 内 lark-cli planned listener 会 fail closed；如果 OpenClaw planned owner 继续运行，仍需用 channel 状态和 gateway log 判断是否真的 owns the bot。
- 11 个 listener / Feishu live 相关单测通过。

## 飞书共享看板

已同步并读回确认：

- `2026-04-28 程俊豪：Feishu 单监听 staging 流程修复`：状态 `已完成`，`完成情况-程俊豪=true`，指派给程俊豪。
- `2026-05-10 程俊豪：把 Feishu live sandbox 升级成 staging runbook`：已标记为 `已完成`，备注说明 staging runbook 和启动守卫已由 2026-04-28 任务提前完成；真实 OpenClaw runtime 3 flow evidence 仍由 2026-05-09 任务承接。

## 仍未完成或仍有风险

- 真实 OpenClaw Agent runtime 的 3 条独立验收证据还没写入 `docs/productization/openclaw-runtime-evidence.md`。
- Generic `openclaw-gateway` 进程名无法自动证明 Feishu websocket 是否启用；repo 内 lark-cli planned listener 默认不继续，OpenClaw planned owner 需要按 OpenClaw 配置和现场事实判断。
- 这次没有改产品核心架构，也没有把 legacy handler 改成主入口；旧 Bot 仍只是 fallback。
