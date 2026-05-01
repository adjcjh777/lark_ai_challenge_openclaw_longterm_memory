# LLM Wiki / Graph Admin Launch Runbook

日期：2026-05-01
状态：本地 / staging 后台上线 gate；不是 productized live 完成证明。

## 1. 范围

本 runbook 只覆盖本地或受控 staging 的 LLM Wiki / 知识图谱后台：

- LLM Wiki：active curated memory 编译视图。
- Graph：`knowledge_graph_*` 表节点/边，以及由 active memory 编译出的 `memory -> grounded_by -> evidence_source` 图谱。
- Tenants：ledger + tenant policy 派生的 tenant / organization readiness、open review、graph/audit 计数、本地/pre-production 租户策略编辑和缺失生产能力清单。
- Ledger / Audit / Tables：只读排障和审计视图。

不覆盖：

- 生产 DB 部署。
- 已接真实企业 IdP 的生产 SSO。
- 完整多租户权限后台。
- 真实企业 IdP / Feishu workspace SSO 生产验收。
- productized live 长期运行。

## 2. 启动前检查

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_admin tests.test_copilot_knowledge_pages
python3 scripts/check_copilot_graph_quality.py --db-path data/memory.sqlite --json
python3 scripts/check_copilot_admin_ui_smoke.py --db-path data/memory.sqlite --scope project:feishu_ai_challenge --output-dir /tmp/copilot-admin-ui-smoke --json
git diff --check
```

Graph quality gate 会复用 Admin Graph backend，检查可见 workspace 中是否有 `memory -> grounded_by -> evidence_source` 编译图谱、边端点完整性、tenant/org 覆盖、孤立节点比例和敏感字符串泄漏。结果同时暴露在 `python3 scripts/check_copilot_graph_quality.py --json`、`/api/graph-quality` 和 Launch 页 Graph Quality 区块。它证明本地/staging 图谱展示质量，不代表生产级图谱治理或长期增量图谱服务。

Audit read-only gate 会复用本地 `memory_audit_events`、`query_audit_events.py` 和 Admin `/api/audit`，检查 tenant/org 过滤、source_context 递归脱敏、CSV 导出、Admin API POST 拒绝和只读计数不变：

```bash
python3 scripts/check_copilot_audit_readonly_gate.py --json
```

这个 gate 只证明本地/staging 审计可读、可过滤、可导出且不泄漏常见 token/secret 字段，不代表生产长期运行、真实企业 IdP、生产 DB 或 SIEM/告警投递完成。

UI smoke 会启动本机 admin、导出静态知识站，并用 Chromium 验证 desktop/mobile 下 Graph tab、Tenants tab、Launch tab、Admin 与静态站的节点/边详情、Relationship Focus evidence path、静态站 Graph quality 摘要、租户 readiness 计数、admin-only tenant policy editor、缺失生产能力清单、静态站 Deerflow attribution、横向溢出和截图像素完整性。需要固定视觉基线时，先运行 `--visual-baseline-dir reports/admin-ui-baseline --update-visual-baseline` 生成 `visual-baseline.json` 和 PNG 基线；后续复用同一个 `--visual-baseline-dir` 会按截图逐张执行采样 pixel diff。脚本会在临时目录安装 Playwright 运行依赖；如果浏览器缓存不存在，先运行 `npx --yes playwright@1.59.1 install chromium`。
GitHub Actions 的 `Admin UI Smoke` job 会运行同一脚本，并额外在 CI 临时目录执行 baseline update / compare，最后上传普通截图、baseline PNG、`visual-baseline.json` 和 compare 截图 artifact。

如果要绑定到非本机地址，必须设置后台 token：

```bash
export FEISHU_MEMORY_COPILOT_ADMIN_TOKEN="$(openssl rand -hex 24)"
export FEISHU_MEMORY_COPILOT_ADMIN_VIEWER_TOKEN="$(openssl rand -hex 24)"
python3 scripts/check_copilot_admin_readiness.py \
  --db-path data/memory.sqlite \
  --host 0.0.0.0 \
  --admin-token "$FEISHU_MEMORY_COPILOT_ADMIN_TOKEN" \
  --viewer-token "$FEISHU_MEMORY_COPILOT_ADMIN_VIEWER_TOKEN" \
  --strict \
  --min-wiki-cards 1
```

admin token 可读取 `/api/*`、导出 Wiki Markdown 并保存 `/api/tenant-policies`；viewer token 只能读取 `/api/*`，访问 `/api/wiki/export` 或提交租户策略会返回 `403`。两个 token 必须不同。本机调试可以不设置 token，但 readiness 会给出 warning：

```bash
python3 scripts/check_copilot_admin_readiness.py --db-path data/memory.sqlite
```

readiness gate 会检查 SQLite schema、Wiki generation policy、Markdown export、compiled Graph、Tenants readiness、本地 tenant policy editor 表/API 能力、Launch readiness、知识只读面和 access policy；Tenants / Launch check 不代表已完成生产 DB、真实企业 IdP SSO 或完整企业权限后台。

部署包静态 verifier：

```bash
python3 scripts/check_copilot_admin_env_file.py --expect-example --json
python3 scripts/check_copilot_knowledge_site_export.py --json
python3 scripts/check_copilot_admin_production_evidence.py --json
python3 scripts/check_copilot_admin_deploy_bundle.py --json
python3 scripts/export_copilot_admin_launch_evidence.py --db-path data/memory.sqlite --output-dir /tmp/copilot-admin-launch-evidence --scope project:feishu_ai_challenge --tenant-id tenant:demo --organization-id org:demo --audit-min-events 1 --json
```

`check_copilot_admin_env_file.py --expect-example` 检查仓库里的 env 示例仍是安全占位符；替换本机 runtime 文件后，使用 `python3 scripts/check_copilot_admin_env_file.py --env-file /etc/feishu-memory-copilot/admin.env --expect-runtime --json` 校验 token 已替换、admin/viewer token 不同、端口合法、远程绑定有 token、SSO 配置完整。报告只输出 redacted state，不输出 token 明文。

`check_copilot_knowledge_site_export.py` 使用临时 SQLite 导出一个只读静态 LLM Wiki / Knowledge Graph 站点，并校验 `index.html`、`data/manifest.json`、`data/wiki.json`、`data/graph.json`、`wiki/*.md`、Graph detail UI、read-only boundary 和 secret-like 文本脱敏。它只证明静态 artifact 可生成和可分享，不代表生产域名部署、真实 SSO 或长期 live 已完成。

`check_copilot_admin_production_evidence.py` 默认检查 `deploy/copilot-admin.production-evidence.example.json`，确认生产证据 manifest 结构完整且不含密钥明文；示例文件的预期输出是 `ok=true`、`production_ready=false`。真实上线验收时，复制该 manifest 到受控环境，填入真实 DB / IdP / TLS / monitoring / long-run 证据后运行 `python3 scripts/check_copilot_admin_production_evidence.py --manifest <path> --require-production-ready --json`。

`collect_copilot_production_db_evidence.py` 用于规范真实 PostgreSQL / managed PostgreSQL 证据：它接收迁移时间、PITR 开关、恢复演练时间和非密钥 evidence ref，输出可填入 production evidence manifest 的 `production_db` patch。它不会创建、连接、迁移、备份或恢复生产数据库；真实生产 DB gate 仍必须由托管数据库控制台、迁移日志、PITR 配置和恢复演练日志提供外部证据。

`collect_copilot_external_production_evidence.py` 用于规范真实企业 IdP / SSO、生产域名 TLS 和生产监控投递证据：它接收登录测试、viewer 导出拒绝、证书有效期、HSTS、Prometheus scrape、Grafana dashboard、Alertmanager route 和告警投递测试时间，输出 `enterprise_idp_sso`、`production_domain_tls`、`production_monitoring` manifest patch。它不会执行真实登录、签发证书、配置 Grafana 或发送告警；真实生产 gate 仍必须由外部系统日志、截图或运维记录支撑。

`collect_copilot_admin_long_run_evidence.py` 用于真实运行窗口的证据采集：它会探测正在运行的 Admin 后台 `/healthz`、`/api/health`、`/api/launch-readiness`、`/api/graph-quality` 和 `/metrics`，并输出可填入 production evidence manifest 的 `productized_live_long_run` patch。采集器本身不创建生产 DB、IdP、TLS、监控或生产 readiness。

`check_copilot_admin_deploy_bundle.py` 检查 `deploy/copilot-admin.service.example`、`deploy/copilot-admin.env.example`、`deploy/copilot-admin.nginx.example`、staging Prometheus alert rules、backup gate、readiness gate、SSO header gate、env lint 和 completion audit gate 是否齐备。它的预期结果是 `staging_bundle_ok=true`、`production_blocked=true`；这只说明 staging 部署包模板完整，不代表真实域名/TLS、企业 IdP、生产 DB、生产监控或长期 live 已完成。

`export_copilot_admin_launch_evidence.py` 会把当前本地/staging admin 状态导出为固定 JSON bundle：`summary.json`、`wiki.json`、`graph.json`、`graph-quality.json`、`audit.json`、`audit-readonly-gate.json`、`launch-readiness.json`、`deploy-bundle.json`、`production-evidence.json`、`completion-audit.json` 和 `manifest.json`。manifest 保留 `goal_complete=false`、`production_blocked=true` 和 production blockers；它是交付证据包，不是生产上线证明。

可选企业 SSO header gate：

```bash
# 后端必须绑定 127.0.0.1，由 Nginx / oauth2-proxy / Feishu SSO 网关注入身份 header。
export FEISHU_MEMORY_COPILOT_ADMIN_SSO_ENABLED=1
export FEISHU_MEMORY_COPILOT_ADMIN_SSO_USER_HEADER=X-Forwarded-User
export FEISHU_MEMORY_COPILOT_ADMIN_SSO_EMAIL_HEADER=X-Forwarded-Email
export FEISHU_MEMORY_COPILOT_ADMIN_SSO_ADMIN_USERS=admin@example.com
export FEISHU_MEMORY_COPILOT_ADMIN_SSO_ALLOWED_DOMAINS=example.com
```

SSO 命中的 allowed domain 默认是 viewer，只能浏览 `/api/*`；只有 `FEISHU_MEMORY_COPILOT_ADMIN_SSO_ADMIN_USERS` 命中的用户可以导出 Wiki Markdown。SSO header gate 是反向代理后的 staging / enterprise auth 接入点，不等于已接入真实 Feishu workspace SSO 或企业 IdP 生产验收。

独立 staging verifier：

```bash
python3 scripts/check_copilot_admin_sso_gate.py --json
```

该 verifier 默认用临时 SQLite 和 loopback admin server，不改 `data/memory.sqlite`；它覆盖 no-header `401`、allowed-domain viewer `/api/summary` `200`、viewer `/api/wiki/export` `403`、admin Wiki export `200`、未认证 `/metrics` `401`、viewer `/metrics` `200` 和 `/api/health` SSO policy 读回。它仍只证明 reverse-proxy SSO header gate，不证明真实企业 IdP / Feishu SSO production validation。

## 3. 启动

本机调试：

```bash
python3 scripts/start_copilot_admin.py --db-path data/memory.sqlite --port 8765
```

受控 staging：

```bash
export FEISHU_MEMORY_COPILOT_ADMIN_TOKEN="<redacted-token>"
export FEISHU_MEMORY_COPILOT_ADMIN_VIEWER_TOKEN="<redacted-viewer-token>"
python3 scripts/start_copilot_admin.py \
  --host 0.0.0.0 \
  --port 8765 \
  --db-path data/memory.sqlite
```

无 token 绑定非 loopback host 会直接失败，这是预期行为。

systemd 受控部署可从模板开始：

```bash
sudo install -d -m 0750 /etc/feishu-memory-copilot
sudo install -m 0640 deploy/copilot-admin.env.example /etc/feishu-memory-copilot/admin.env
sudo editor /etc/feishu-memory-copilot/admin.env
python3 scripts/check_copilot_admin_env_file.py --env-file /etc/feishu-memory-copilot/admin.env --expect-runtime --json
sudo cp deploy/copilot-admin.service.example /etc/systemd/system/copilot-admin.service
sudo systemctl daemon-reload
sudo systemctl start copilot-admin
sudo systemctl status copilot-admin --no-pager
```

`deploy/copilot-admin.env.example` 默认把 Python 后端绑定到 `127.0.0.1`，适合放在 Nginx / SSO reverse proxy 后。真实 token、企业 IdP secret、生产 DB credentials 必须只写入本机 `/etc/feishu-memory-copilot/admin.env`，不要提交进仓库。

如果要通过 Nginx 暴露给受控测试用户，从模板开始：

```bash
sudo cp deploy/copilot-admin.nginx.example /etc/nginx/sites-available/copilot-admin
sudo ln -sf /etc/nginx/sites-available/copilot-admin /etc/nginx/sites-enabled/copilot-admin
sudo nginx -t
sudo systemctl reload nginx
```

模板只代理到本机 `127.0.0.1:8765`。正式使用前必须替换域名和证书路径，并确保后台 API token 已启用；评委/队友只读浏览优先发 viewer token，Markdown 导出和租户策略编辑只发 admin token 给维护者。

## 4. 探活和验收

进程 liveness，不返回业务数据：

```bash
curl -fsS http://127.0.0.1:8765/healthz
```

带认证 readiness：

```bash
curl -fsS \
  -H "Authorization: Bearer $FEISHU_MEMORY_COPILOT_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/health
```

上线 gate 摘要：

```bash
curl -fsS \
  -H "Authorization: Bearer $FEISHU_MEMORY_COPILOT_ADMIN_TOKEN" \
  http://127.0.0.1:8765/api/launch-readiness
```

Prometheus text metrics，同样走 admin/viewer token 或 SSO：

```bash
curl -fsS \
  -H "Authorization: Bearer $FEISHU_MEMORY_COPILOT_ADMIN_VIEWER_TOKEN" \
  http://127.0.0.1:8765/metrics
```

生产 DB 证据 patch 生成示例：

```bash
python3 scripts/collect_copilot_production_db_evidence.py \
  --engine managed_postgresql \
  --migration-applied-at 2026-05-01T10:00:00+08:00 \
  --pitr-enabled \
  --backup-restore-drill-at 2026-05-01T11:00:00+08:00 \
  --evidence-ref ops/db-migration-20260501 \
  --evidence-ref ops/pitr-restore-drill-20260501 \
  --json
```

这个命令只生成 `production_manifest_patch.production_db`。不要把它的通过结果写成生产 DB 已部署；必须把真实托管 PostgreSQL / PITR / restore drill 的外部证据一起交给 `check_copilot_admin_production_evidence.py --require-production-ready`。

外部入口证据 patch 生成示例：

```bash
python3 scripts/collect_copilot_external_production_evidence.py \
  --idp-provider feishu_sso \
  --idp-login-tested-at 2026-05-01T10:00:00+08:00 \
  --idp-admin-login-passed \
  --idp-viewer-export-denied \
  --idp-allowed-domain company.internal \
  --idp-evidence-ref ops/idp-smoke-20260501 \
  --tls-url https://memory.company.internal \
  --tls-validated-at 2026-05-01T11:00:00+08:00 \
  --tls-certificate-subject CN=memory.company.internal \
  --tls-certificate-expires-at 2099-01-01T00:00:00+00:00 \
  --tls-hsts-enabled \
  --tls-evidence-ref ops/tls-check-20260501 \
  --prometheus-scrape-proven \
  --grafana-dashboard-url https://grafana.company.internal/d/copilot-admin \
  --alertmanager-route team-memory-copilot \
  --alert-delivery-tested-at 2026-05-01T12:00:00+08:00 \
  --monitoring-evidence-ref ops/alert-delivery-20260501 \
  --json
```

这个命令只生成 `enterprise_idp_sso`、`production_domain_tls` 和 `production_monitoring` patch。不要把它的通过结果写成真实 IdP、TLS 或生产监控已完成；仍需要外部系统证据和 `check_copilot_admin_production_evidence.py --require-production-ready` 统一验收。

本地/staging 长跑采集 smoke：

```bash
python3 scripts/collect_copilot_admin_long_run_evidence.py \
  --base-url http://127.0.0.1:8765 \
  --token "$FEISHU_MEMORY_COPILOT_ADMIN_VIEWER_TOKEN" \
  --sample-count 3 \
  --sample-interval-seconds 0 \
  --min-sample-count 3 \
  --service-unit copilot-admin.service \
  --oncall-owner staging-owner \
  --rollback-drill-at 2026-05-01T00:00:00+08:00 \
  --evidence-ref staging/local-long-run-smoke \
  --json
```

真实 productized live gate 至少要在生产入口运行 24 小时，例如 `--sample-count 25 --sample-interval-seconds 3600 --min-window-hours 24 --min-sample-count 24`，并把输出中的 `production_manifest_patch.productized_live_long_run` 合并到真实 production evidence manifest。短跑 smoke 只证明采集器和接口可用，不代表长期线上运行完成。

### Prometheus Alert Rules

staging alert-rule artifact:

```text
deploy/monitoring/copilot-admin-alerts.yml
```

本地校验：

```bash
python3 scripts/check_prometheus_alert_rules.py --json
```

当前规则覆盖 admin scrape down、Launch staging gate、Wiki cards、Graph nodes、Tenant policy、Audit ledger、production blocked 和 `production_monitoring_alerts` blocker。这个 artifact 可用于 staging 监控试点；它不代表生产 Prometheus/Grafana、Alertmanager 投递、on-call 流程或自动回滚已经验证完成。

核心页面验收：

1. 打开 `/`。
2. 输入 token 后确认 Summary 有 Memory / Active / Audit / Evidence 计数。
3. 在 `tenant_id` / `organization_id` 输入框里填入当前测试租户，确认 `LLM Wiki`、`Graph`、`Tenants`、`Ledger`、`Audit` 都会按租户边界收敛结果；这仍不代表生产多租户后台。
4. 进入 `LLM Wiki`，确认 generation policy 为：
   - `active_curated_memory_only`
   - `raw events = excluded`
   - `requires evidence = required`
   - `writes_feishu = no`
5. 在 `LLM Wiki` 用 admin token 点击 `导出 Markdown`，或用 API 验证指定 scope 的静态 Wiki 导出：

```bash
curl -fsS \
  -H "Authorization: Bearer $FEISHU_MEMORY_COPILOT_ADMIN_TOKEN" \
  "http://127.0.0.1:8765/api/wiki/export?scope=project:feishu_ai_challenge" \
  | head
```

导出内容应以 `# 项目记忆卡册：...` 开头，只包含 active curated memory 和 evidence，不包含 raw events。
6. 使用 viewer token 访问 `/api/wiki/export?scope=...` 应返回 `403`，确认只读浏览 token 不能批量导出知识卡册。
7. 进入 `Graph`，确认至少能看到 compiled memory 节点；如果已有飞书群/用户/消息图谱，应同时显示 `feishu_chat` / `feishu_user` / `feishu_message`。
8. 进入 `Tenants`，确认每个 tenant / organization 显示 memory、open review、graph、audit 计数；用 admin token 保存一条 tenant policy，确认 readiness 从 `available_unconfigured` 变为 `configured`，并读回 `tenant_policy_upserted` 审计。
9. 使用 viewer token 提交 `/api/tenant-policies` 应返回 `403`；admin token 可提交如下最小 payload：

```bash
curl -fsS \
  -H "Authorization: Bearer $FEISHU_MEMORY_COPILOT_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{"tenant_id":"tenant:demo","organization_id":"org:demo","default_visibility_policy":"team","reviewer_roles":["reviewer","owner"],"admin_users":["admin@example.com"],"sso_allowed_domains":["example.com"],"auto_confirm_low_risk":true,"require_review_for_conflicts":true,"notes":"staging tenant policy"}' \
  http://127.0.0.1:8765/api/tenant-policies
```

10. 确认缺失能力只保留真实生产缺口：`enterprise_idp_sso_validation`、`production_db_operations`、`productized_live_long_run`。
11. 进入 `Launch`，确认 staging gates 有真实 evidence，production status 明确是 `blocked`，并列出真实生产 blocker。
12. 进入 `Audit`，确认权限和工具调用审计可读。

静态知识站导出验收：

```bash
python3 scripts/export_copilot_knowledge_site.py \
  --db-path data/memory.sqlite \
  --output-dir reports/copilot-knowledge-site \
  --scope project:feishu_ai_challenge \
  --json
```

导出目录必须包含：

```text
index.html
data/manifest.json
data/wiki.json
data/graph.json
wiki/project_feishu_ai_challenge.md
```

`index.html` 是只读 Wiki + Graph 静态入口，应能搜索卡片/节点，并能点击图谱节点或关系边查看 tenant、organization、visibility、observation 和 metadata 详情；`manifest.json` 里必须保留 `no production deployment` 边界。该导出包可作为受控内网静态 artifact，但仍不代表生产部署、SSO 或 productized live 已完成。

## 5. 回滚

后台知识面是只读服务；唯一写接口是 admin-only tenant policy upsert，不修改 memory active/candidate 状态，也不写 Feishu / Bitable。回滚动作：

1. 停止 `scripts/start_copilot_admin.py` 进程。
2. 取消暴露端口或反向代理路由。
3. 如需撤销本地租户策略，停服后备份 SQLite，再删除或更新 `tenant_admin_policies` 中对应测试行。
4. 轮换 `FEISHU_MEMORY_COPILOT_ADMIN_TOKEN`。
5. 保留 `memory_audit_events` 和启动日志用于排障。

## 6. 对外口径

可以说：

- 已完成本地 / staging LLM Wiki 和知识图谱后台。
- 已有 token gate、知识只读 API、healthz、readiness gate、Markdown Wiki 导出、静态知识站导出和敏感字段脱敏。
- 已有 admin / viewer token 分级：viewer 只读浏览，admin 才能导出 Wiki Markdown 和保存 tenant policy。
- 已有可选 reverse-proxy SSO header gate：admin allowlist 可导出，allowed domain viewer 只能浏览；直接远程绑定仍需 bearer token。
- 已有 tenant / organization 过滤、Tenants readiness 概览和本地/pre-production tenant policy editor，可用于 staging 下检查租户边界展示与上线缺口。
- 已有 Launch readiness 面板和 `/api/launch-readiness`，把 staging gate 与 production blocker 分开展示。
- 已有受认证 `/metrics` Prometheus text endpoint 和 `deploy/monitoring/copilot-admin-alerts.yml` staging alert rules，可供 staging 监控试点抓取和校验；这不是生产告警完成。
- Wiki 只编译 active curated memory，不向量化或展示全部 raw events。

不能说：

- 已完成生产部署。
- 已完成完整多租户企业后台。
- 已接入真实企业 IdP / Feishu workspace SSO 并完成生产验收。
- 已完成 productized live 长期运行。
