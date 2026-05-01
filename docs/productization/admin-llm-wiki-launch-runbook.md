# LLM Wiki / Graph Admin Launch Runbook

日期：2026-05-01
状态：本地 / staging 只读后台上线 gate；不是 productized live 完成证明。

## 1. 范围

本 runbook 只覆盖本地或受控 staging 的只读 LLM Wiki / 知识图谱后台：

- LLM Wiki：active curated memory 编译视图。
- Graph：`knowledge_graph_*` 表节点/边，以及由 active memory 编译出的 `memory -> grounded_by -> evidence_source` 图谱。
- Ledger / Audit / Tables：只读排障和审计视图。

不覆盖：

- 生产 DB 部署。
- 企业 SSO。
- 完整多租户权限后台。
- productized live 长期运行。

## 2. 启动前检查

```bash
python3 scripts/check_openclaw_version.py
python3 scripts/check_agent_harness.py
python3 -m compileall memory_engine scripts
python3 -m unittest tests.test_copilot_admin tests.test_copilot_knowledge_pages
git diff --check
```

如果要绑定到非本机地址，必须设置后台 token：

```bash
export FEISHU_MEMORY_COPILOT_ADMIN_TOKEN="$(openssl rand -hex 24)"
python3 scripts/check_copilot_admin_readiness.py \
  --db-path data/memory.sqlite \
  --host 0.0.0.0 \
  --admin-token "$FEISHU_MEMORY_COPILOT_ADMIN_TOKEN" \
  --strict \
  --min-wiki-cards 1
```

本机调试可以不设置 token，但 readiness 会给出 warning：

```bash
python3 scripts/check_copilot_admin_readiness.py --db-path data/memory.sqlite
```

## 3. 启动

本机调试：

```bash
python3 scripts/start_copilot_admin.py --db-path data/memory.sqlite --port 8765
```

受控 staging：

```bash
export FEISHU_MEMORY_COPILOT_ADMIN_TOKEN="<redacted-token>"
python3 scripts/start_copilot_admin.py \
  --host 0.0.0.0 \
  --port 8765 \
  --db-path data/memory.sqlite
```

无 token 绑定非 loopback host 会直接失败，这是预期行为。

systemd 受控部署可从模板开始：

```bash
sudo install -d -m 0750 /etc/feishu-memory-copilot
sudo tee /etc/feishu-memory-copilot/admin.env >/dev/null <<'EOF'
MEMORY_DB_PATH=/opt/feishu_ai_challenge/data/memory.sqlite
FEISHU_MEMORY_COPILOT_ADMIN_HOST=0.0.0.0
FEISHU_MEMORY_COPILOT_ADMIN_PORT=8765
FEISHU_MEMORY_COPILOT_ADMIN_TOKEN=<redacted-token>
EOF
sudo cp deploy/copilot-admin.service.example /etc/systemd/system/copilot-admin.service
sudo systemctl daemon-reload
sudo systemctl start copilot-admin
sudo systemctl status copilot-admin --no-pager
```

如果要通过 Nginx 暴露给受控测试用户，从模板开始：

```bash
sudo cp deploy/copilot-admin.nginx.example /etc/nginx/sites-available/copilot-admin
sudo ln -sf /etc/nginx/sites-available/copilot-admin /etc/nginx/sites-enabled/copilot-admin
sudo nginx -t
sudo systemctl reload nginx
```

模板只代理到本机 `127.0.0.1:8765`。正式使用前必须替换域名和证书路径，并确保后台 API token 已启用。

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

核心页面验收：

1. 打开 `/`。
2. 输入 token 后确认 Summary 有 Memory / Active / Audit / Evidence 计数。
3. 进入 `LLM Wiki`，确认 generation policy 为：
   - `active_curated_memory_only`
   - `raw events = excluded`
   - `requires evidence = required`
   - `writes_feishu = no`
4. 在 `LLM Wiki` 点击 `导出 Markdown`，或用 API 验证指定 scope 的静态 Wiki 导出：

```bash
curl -fsS \
  -H "Authorization: Bearer $FEISHU_MEMORY_COPILOT_ADMIN_TOKEN" \
  "http://127.0.0.1:8765/api/wiki/export?scope=project:feishu_ai_challenge" \
  | head
```

导出内容应以 `# 项目记忆卡册：...` 开头，只包含 active curated memory 和 evidence，不包含 raw events。
5. 进入 `Graph`，确认至少能看到 compiled memory 节点；如果已有飞书群/用户/消息图谱，应同时显示 `feishu_chat` / `feishu_user` / `feishu_message`。
6. 进入 `Audit`，确认权限和工具调用审计可读。

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

`index.html` 是只读 Wiki + Graph 静态入口；`manifest.json` 里必须保留 `no production deployment` 边界。该导出包可作为受控内网静态 artifact，但仍不代表生产部署、SSO 或 productized live 已完成。

## 5. 回滚

后台是只读服务，不应修改 SQLite / Feishu / Bitable。回滚动作：

1. 停止 `scripts/start_copilot_admin.py` 进程。
2. 取消暴露端口或反向代理路由。
3. 轮换 `FEISHU_MEMORY_COPILOT_ADMIN_TOKEN`。
4. 保留 `memory_audit_events` 和启动日志用于排障。

## 6. 对外口径

可以说：

- 已完成本地 / staging 只读 LLM Wiki 和知识图谱后台。
- 已有 token gate、只读 API、healthz、readiness gate、Markdown Wiki 导出、静态知识站导出和敏感字段脱敏。
- Wiki 只编译 active curated memory，不向量化或展示全部 raw events。

不能说：

- 已完成生产部署。
- 已完成完整多租户企业后台。
- 已完成企业 SSO。
- 已完成 productized live 长期运行。
