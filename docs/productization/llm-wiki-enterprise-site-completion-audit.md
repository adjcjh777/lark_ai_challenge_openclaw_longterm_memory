# LLM Wiki Enterprise Knowledge Site Completion Audit

日期：2026-05-01

状态：本地 / 受控 staging 可验收；不是生产上线完成证明。

## 1. Objective 拆解

用户目标：

```text
做完整版可上线的 llm wiki 企业知识站，将其与知识图谱结合起来去做后台可展示的知识图谱后台，同时优化当前的后台 ui 设计
```

可验收交付物拆解：

| 要求 | 当前判定 | 证据 | 缺口 |
| --- | --- | --- | --- |
| LLM Wiki 企业知识站 | staging 已完成 | `memory_engine/copilot/knowledge_site.py`、`scripts/export_copilot_knowledge_site.py`、`tests/test_copilot_knowledge_site.py`、`README.md` 静态导出说明 | 还没有生产域名、SSO、长期运行证据 |
| 知识图谱结合 | staging 已完成 | `/api/graph`、静态 `data/graph.json`、compiled `memory -> grounded_by -> evidence_source`、图谱节点/边详情面板 | 还没有长期图谱增量质量评估和生产级图谱治理后台 |
| 后台可展示知识图谱 | staging 已完成 | `memory_engine/copilot/admin.py` 的 `Graph` tab、`tests/test_copilot_admin.py`、桌面/移动端 Playwright smoke 截图 | 还不是完整多租户企业后台 |
| 当前后台 UI 优化 | staging 已完成 | Admin Graph 响应式网格、节点/边详情、移动端无横向溢出；静态站 Graph 稳定网格 | 还缺设计系统级组件抽象和完整视觉回归流水线 |
| 可上线 | 部分完成 | `deploy/copilot-admin.service.example`、`deploy/copilot-admin.nginx.example`、`scripts/check_copilot_admin_readiness.py --strict`、admin/viewer token 分级 | 生产 DB、企业 SSO、域名证书、运行监控、长期 productized live 仍未完成 |

## 2. Prompt-to-Artifact Checklist

| 明确要求 / 文件 / 命令 / gate | 证据 | 覆盖说明 |
| --- | --- | --- |
| `index.html` 静态知识站 | `scripts/export_copilot_knowledge_site.py` 输出 `index.html` | 只读展示 active curated memory、Wiki、Graph、搜索和详情 |
| `data/manifest.json` | `memory_engine/copilot/knowledge_site.py` | 保留 `no production deployment` 边界 |
| `data/wiki.json` | `memory_engine/copilot/knowledge_site.py` | 来源为 active curated memory，不包含 raw events |
| `data/graph.json` | `memory_engine/copilot/knowledge_site.py` | 包含 storage graph 和 compiled memory graph |
| `wiki/*.md` | `AdminQueryService.wiki_export_markdown()` | Markdown Wiki 导出，敏感字段脱敏 |
| live admin `/api/wiki` | `memory_engine/copilot/admin.py` | 只读 LLM Wiki 编译视图 |
| live admin `/api/wiki/export` | `memory_engine/copilot/admin.py` | 只接受 admin token；viewer token 返回 `403` |
| live admin `/api/graph` | `memory_engine/copilot/admin.py` | 节点、边、metadata、tenant/org/visibility 字段可查 |
| Graph UI 节点/边详情 | `memory_engine/copilot/admin.py`、`memory_engine/copilot/knowledge_site.py` | 点击节点/边展示 tenant、organization、visibility、observations、metadata |
| read-only API gate | `tests/test_copilot_admin.py` | `POST` 等写请求返回 `405` |
| admin/viewer token gate | `tests/test_copilot_admin.py`、`scripts/check_copilot_admin_readiness.py` | admin 可导出；viewer 只读；token 相同被启动脚本拒绝 |
| staging readiness gate | `python3 scripts/check_copilot_admin_readiness.py --strict` | 覆盖 DB、schema、Wiki、export、Graph、read-only API、access policy |
| OpenClaw 固定版本 | `python3 scripts/check_openclaw_version.py` | 验证 `2026.4.24` 锁定 |
| harness contract | `python3 scripts/check_agent_harness.py` | 验证 AGENTS、执行 contract、Cognee adapter 边界 |
| Python 编译 | `python3 -m compileall memory_engine scripts` | 覆盖 Python 语法和导入编译 |
| 单元测试 | `python3 -m unittest tests.test_copilot_admin tests.test_copilot_knowledge_site tests.test_copilot_knowledge_pages` | 覆盖 admin API、静态站导出、Wiki 页面编译 |
| 空白检查 | `git diff --check` | 避免 trailing whitespace 等提交问题 |
| UI smoke gate | `python3 scripts/check_copilot_admin_ui_smoke.py --json` | 启动 admin、导出静态站，用 Chromium 检查 desktop/mobile Graph 详情、Deerflow attribution 和横向溢出 |
| 本地模型占用检查 | `ollama ps` | 确认没有残留 embedding/model runtime |

## 3. 当前已推送里程碑

| Commit | 内容 |
| --- | --- |
| `758e545` | 只读 LLM Wiki / Graph Admin 基础入口 |
| `22375be` | admin strict readiness gate |
| `b819d0a` | Nginx reverse proxy template |
| `3e0e217` | Wiki Markdown export |
| `0edb9ec` | static Copilot knowledge site export |
| `0afc42d` | static knowledge graph inspection |
| `e309847` | live admin knowledge graph inspection |
| `59798aa` | admin/viewer token access policy |

## 4. 已验证命令

最近一次 access policy hardening 的验证：

```bash
python3 -m unittest tests.test_copilot_admin tests.test_copilot_knowledge_site tests.test_copilot_knowledge_pages
python3 -m compileall memory_engine scripts
python3 scripts/check_copilot_admin_readiness.py --db-path /tmp/copilot-admin-ui.sqlite --host 0.0.0.0 --admin-token admin-token --viewer-token viewer-token --strict --min-wiki-cards 1 --json
python3 scripts/start_copilot_admin.py --host 0.0.0.0 --port 0 --db-path /tmp/copilot-admin-ui.sqlite --viewer-token same --admin-token same
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
git diff --check
ollama ps
```

UI smoke 验证：

```bash
python3 scripts/check_copilot_admin_ui_smoke.py --output-dir /tmp/copilot-ui-smoke --json
```

覆盖：

```text
admin desktop graph detail and horizontal overflow
admin mobile graph detail and horizontal overflow
static site desktop graph detail and Deerflow attribution
static site mobile graph detail and horizontal overflow
```

额外 HTTP smoke：

```text
viewer token: GET /api/summary -> 200
viewer token: GET /api/wiki/export?scope=... -> 403 admin_export_forbidden
admin token: GET /api/wiki/export?scope=... -> Markdown
```

截图输出示例：

```text
admin-graph-desktop.png
admin-graph-mobile.png
static-site-desktop.png
static-site-mobile.png
```

## 5. 未完成项

以下项目仍然阻止“完整版生产上线完成”结论：

1. 企业 SSO 未接入。当前是 admin/viewer bearer token gate，不是 Feishu workspace SSO 或企业 IdP。
2. 完整多租户企业后台未完成。当前数据结构带 tenant/org 字段，后台展示也显示这些字段，但没有 tenant admin console、租户配置页或租户级策略编辑。
3. 生产 DB 部署未完成。当前 runbook 覆盖本地 / staging SQLite 只读 admin，不覆盖生产数据库运维。
4. 长期 productized live 未完成。当前不能声明真实 Feishu DM 稳定路由到 first-class `memory.*` 工具或长期线上运行。
5. 监控告警未完成。已有 health/readiness，但没有生产级 uptime、延迟、错误率、审计异常告警。
6. UI 视觉回归没有进入 CI。已有可复跑 Playwright smoke 和截图输出，但没有固定基线、自动 diff 和发布阻断。

## 6. 下一步建议

1. 明确目标部署方式：内网静态 artifact、受控 staging admin、还是真实生产服务。
2. 选定企业认证边界：Feishu SSO、oauth2-proxy、Nginx `auth_request`，或其他 IdP。
3. 将 tenant/org 权限策略从只读展示推进到配置化后台。
4. 将 `scripts/check_copilot_admin_ui_smoke.py` 接入 CI，并增加固定截图基线或 DOM layout assertions 作为发布阻断。
5. 建立 productized live 运行证据：启动命令、日志窗口、健康探活、真实受控消息链路、回滚记录。
