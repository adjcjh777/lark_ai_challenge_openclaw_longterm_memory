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
| LLM Wiki 企业知识站 | staging 已完成 | `memory_engine/copilot/knowledge_site.py`、`scripts/export_copilot_knowledge_site.py`、`tests/test_copilot_knowledge_site.py`、`README.md` 静态导出说明 | 还没有生产域名、真实 IdP SSO 验收、长期运行证据 |
| 知识图谱结合 | staging 已完成 | `/api/graph`、静态 `data/graph.json`、compiled `memory -> grounded_by -> evidence_source`、图谱节点/边详情面板 | 还没有长期图谱增量质量评估和生产级图谱治理后台 |
| 后台可展示知识图谱 | staging 已完成 | `memory_engine/copilot/admin.py` 的 `Graph` tab、`Tenants` tab、`tests/test_copilot_admin.py`、桌面/移动端 Playwright smoke 截图、tenant/org 过滤、admin-only tenant policy editor | 还不是生产级租户管理控制台 |
| 当前后台 UI 优化 | staging 已完成 | Admin Graph 响应式网格、节点/边详情、移动端无横向溢出；静态站 Graph 稳定网格 | 还缺设计系统级组件抽象和完整视觉回归流水线 |
| 可上线 | 部分完成 | `deploy/copilot-admin.service.example`、`deploy/copilot-admin.nginx.example`、`scripts/check_copilot_admin_readiness.py --strict`、admin/viewer token 分级、reverse-proxy SSO header gate | 生产 DB、真实企业 IdP 验收、域名证书、运行监控、长期 productized live 仍未完成 |

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
| live admin `/api/tenants` | `memory_engine/copilot/admin.py` | ledger + tenant policy 派生的 tenant / organization readiness，显示 memory、open review、graph、audit、policy editor 状态和缺失生产能力 |
| live admin `/api/tenant-policies` | `memory_engine/copilot/admin.py`、`tests/test_copilot_admin.py` | GET 可读租户策略；POST 仅 admin 可 upsert 本地/pre-production tenant policy，并写 `tenant_policy_upserted` 审计 |
| tenant/org 过滤 | `memory_engine/copilot/admin.py`、`tests/test_copilot_admin.py` | `/api/wiki`、`/api/graph`、`/api/tenants`、`/api/memories`、`/api/audit` 可按 `tenant_id` / `organization_id` 收敛结果 |
| Graph UI 节点/边详情 | `memory_engine/copilot/admin.py`、`memory_engine/copilot/knowledge_site.py` | 点击节点/边展示 tenant、organization、visibility、observations、metadata |
| restricted write gate | `tests/test_copilot_admin.py` | 非 tenant policy 写请求返回 `405`；tenant policy POST 要求 admin |
| admin/viewer token gate | `tests/test_copilot_admin.py`、`scripts/check_copilot_admin_readiness.py` | admin 可导出和保存 tenant policy；viewer 只读；token 相同被启动脚本拒绝 |
| reverse-proxy SSO header gate | `memory_engine/copilot/admin.py`、`tests/test_copilot_admin.py`、`deploy/copilot-admin.nginx.example` | 本机反向代理注入 `X-Forwarded-Email` 后，admin allowlist 可导出，allowed domain viewer 只能浏览；非生产 IdP 验收 |
| staging readiness gate | `python3 scripts/check_copilot_admin_readiness.py --strict` | 覆盖 DB、schema、Wiki、export、Graph、Tenants readiness、tenant policy editor availability、restricted write API、access policy |
| OpenClaw 固定版本 | `python3 scripts/check_openclaw_version.py` | 验证 `2026.4.24` 锁定 |
| harness contract | `python3 scripts/check_agent_harness.py` | 验证 AGENTS、执行 contract、Cognee adapter 边界 |
| Python 编译 | `python3 -m compileall memory_engine scripts` | 覆盖 Python 语法和导入编译 |
| 单元测试 | `python3 -m unittest tests.test_copilot_admin tests.test_copilot_knowledge_site tests.test_copilot_knowledge_pages` | 覆盖 admin API、静态站导出、Wiki 页面编译 |
| 空白检查 | `git diff --check` | 避免 trailing whitespace 等提交问题 |
| UI smoke gate | `python3 scripts/check_copilot_admin_ui_smoke.py --json` | 启动 admin、导出静态站，用 Chromium 检查 desktop/mobile Graph 详情、Tenants readiness、缺失生产能力清单、Deerflow attribution 和横向溢出 |
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
| `eb78491` | Copilot Admin / static site UI smoke gate script |
| `87bdabc` | Admin UI smoke GitHub Actions CI job |
| `8af104b` | live Admin tenant/org scoped filters |
| `a4d07ad` | reverse-proxy SSO header gate |
| 本轮提交 | admin-only tenant policy editor |

## 4. 已验证命令

最近一次 tenant policy editor hardening 的验证：

```bash
python3 -m unittest tests.test_copilot_admin tests.test_copilot_knowledge_site tests.test_copilot_knowledge_pages
python3 -m compileall memory_engine scripts
python3 scripts/check_copilot_admin_readiness.py --db-path /tmp/copilot-admin-ui.sqlite --host 0.0.0.0 --admin-token admin-token --viewer-token viewer-token --strict --min-wiki-cards 1 --json
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
admin desktop tenants readiness and horizontal overflow
admin mobile tenants readiness and horizontal overflow
admin tenant policy editor save and configured readiness
static site desktop graph detail and Deerflow attribution
static site mobile graph detail and horizontal overflow
```

额外 HTTP smoke：

```text
viewer token: GET /api/summary -> 200
viewer token: GET /api/wiki/export?scope=... -> 403 admin_export_forbidden
viewer token: POST /api/tenant-policies -> 403 admin_policy_forbidden
admin token: GET /api/wiki/export?scope=... -> Markdown
admin token: POST /api/tenant-policies -> tenant_policy_upserted audit
```

截图输出示例：

```text
admin-graph-desktop.png
admin-graph-mobile.png
admin-tenants-desktop.png
admin-tenants-mobile.png
static-site-desktop.png
static-site-mobile.png
```

## 5. 未完成项

以下项目仍然阻止“完整版生产上线完成”结论：

1. 真实企业 SSO 未完成生产验收。当前新增的是 reverse-proxy SSO header gate，本机反向代理可注入企业用户 header，但还没有接真实 Feishu workspace SSO 或企业 IdP 并完成生产验收。
2. 完整多租户企业后台未完成。当前已经有本地/pre-production tenant policy editor，可配置默认 visibility、reviewer roles、admin users、SSO allowed domains、低风险 auto-confirm 和冲突人工审核开关；但还没有接真实企业目录、组织架构同步、审批流、细粒度 RBAC 或生产级策略发布。
3. 生产 DB 部署未完成。当前 runbook 覆盖本地 / staging SQLite admin，不覆盖生产数据库运维。
4. 长期 productized live 未完成。当前不能声明真实 Feishu DM 稳定路由到 first-class `memory.*` 工具或长期线上运行。
5. 监控告警未完成。已有 health/readiness，但没有生产级 uptime、延迟、错误率、审计异常告警。
6. UI 视觉回归已有 CI smoke，覆盖 Graph、Tenants、静态站关键 DOM、详情面板、readiness 文案和横向溢出，但没有固定截图基线或自动 pixel diff。

## 6. 下一步建议

1. 明确目标部署方式：内网静态 artifact、受控 staging admin、还是真实生产服务。
2. 选定企业认证边界：Feishu SSO、oauth2-proxy、Nginx `auth_request`，或其他 IdP。
3. 将 tenant policy editor 接入真实企业目录、审批发布流程和权限矩阵执行链路。
4. 给 `scripts/check_copilot_admin_ui_smoke.py` 增加固定截图基线或 pixel diff，继续扩大 dashboard tab 覆盖。
5. 建立 productized live 运行证据：启动命令、日志窗口、健康探活、真实受控消息链路、回滚记录。
