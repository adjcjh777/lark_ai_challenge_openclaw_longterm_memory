from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from memory_engine.cli import build_parser
from memory_engine.copilot.admin import AdminQueryService, AdminSsoConfig, create_admin_server, start_embedded_admin
from memory_engine.db import init_db
from memory_engine.repository import MemoryRepository, now_ms
from scripts.check_copilot_admin_readiness import run_admin_readiness


class CopilotAdminTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(prefix="copilot_admin_", suffix=".sqlite")
        self.conn = sqlite3.connect(self.tmp.name)
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        self.repo = MemoryRepository(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.close()

    def _seed_rows(self) -> None:
        active = self.repo.remember("project:admin_demo", "决定：后台服务默认只绑定 127.0.0.1。")
        candidate = self.repo.add_candidate(
            "project:admin_demo",
            "规则：候选记忆必须先 review 再 active。",
            source_type="lark_doc",
            source_id="doc_admin",
            document_token="doc_admin",
            document_title="Admin Runbook",
            quote="候选记忆必须先 review 再 active。",
            created_by="test",
        )
        with self.conn:
            event_time = now_ms()
            self.repo.record_raw_event(
                "project:admin_demo",
                "机器人收到一条新的飞书测试消息，app_secret=demo-secret。",
                source_type="feishu_message",
                source_id="msg_admin",
                sender_id="ou_admin",
                raw_json={"chat_id": "chat_admin"},
                event_time=event_time,
            )
            self.conn.execute(
                """
                INSERT INTO knowledge_graph_nodes (
                  id, tenant_id, organization_id, node_type, node_key, label,
                  visibility_policy, status, metadata_json, first_seen_at,
                  last_seen_at, observation_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "kgn_admin_chat",
                    "tenant:demo",
                    "org:demo",
                    "feishu_chat",
                    "chat_admin",
                    "Feishu chat chat_admin",
                    "team",
                    "active",
                    "{}",
                    event_time,
                    event_time,
                    1,
                ),
            )
            self.conn.execute(
                """
                INSERT INTO knowledge_graph_nodes (
                  id, tenant_id, organization_id, node_type, node_key, label,
                  visibility_policy, status, metadata_json, first_seen_at,
                  last_seen_at, observation_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "kgn_admin_user",
                    "tenant:demo",
                    "org:demo",
                    "feishu_user",
                    "ou_admin",
                    "Admin Reviewer",
                    "team",
                    "active",
                    "{}",
                    event_time,
                    event_time,
                    2,
                ),
            )
            self.conn.execute(
                """
                INSERT INTO knowledge_graph_edges (
                  id, tenant_id, organization_id, source_node_id, target_node_id,
                  edge_type, metadata_json, first_seen_at, last_seen_at, observation_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "kge_admin_member",
                    "tenant:demo",
                    "org:demo",
                    "kgn_admin_user",
                    "kgn_admin_chat",
                    "member_of",
                    "{}",
                    event_time,
                    event_time,
                    2,
                ),
            )
            self.repo.record_audit_event(
                event_type="candidate_created",
                action="memory.create_candidate",
                target_type="candidate",
                target_id=candidate["memory_id"],
                candidate_id=candidate["memory_id"],
                actor_id="u_admin",
                scope="project:admin_demo",
                permission_decision="allow",
                request_id="req_admin",
                trace_id="trace_admin",
                created_at=now_ms(),
            )
            other = self.repo.remember(
                "project:other_admin",
                "决定：其他租户的后台域名只在独立环境展示。",
                source_type="lark_doc",
                source_id="doc_other_admin",
                created_by="other",
            )
            self.conn.execute(
                "UPDATE memories SET tenant_id = ?, organization_id = ? WHERE id = ?",
                ("tenant:other", "org:other", other["memory_id"]),
            )
            self.conn.execute(
                "UPDATE memory_versions SET tenant_id = ?, organization_id = ? WHERE memory_id = ?",
                ("tenant:other", "org:other", other["memory_id"]),
            )
            self.conn.execute(
                "UPDATE memory_evidence SET tenant_id = ?, organization_id = ? WHERE memory_id = ?",
                ("tenant:other", "org:other", other["memory_id"]),
            )
            self.conn.execute(
                "UPDATE raw_events SET tenant_id = ?, organization_id = ? WHERE source_id = ?",
                ("tenant:other", "org:other", "doc_other_admin"),
            )
        self.active_id = active["memory_id"]
        self.candidate_id = candidate["memory_id"]

    def test_query_service_summarizes_and_filters_memory_rows(self) -> None:
        self._seed_rows()

        service = AdminQueryService(self.conn)
        summary = service.summary()
        self.assertEqual(3, summary["memory_total"])
        self.assertEqual({"active": 2, "candidate": 1}, summary["memory_by_status"])
        self.assertEqual(1, summary["audit_total"])

        live = service.live_overview()
        self.assertIn("msg_admin", {item["source_id"] for item in live["recent_raw_events"]})
        raw_contents = "\n".join(item["content"] for item in live["recent_raw_events"])
        self.assertIn("[REDACTED]", raw_contents)
        self.assertNotIn("demo-secret", raw_contents)
        self.assertEqual(2, live["knowledge_graph"]["node_total"])
        self.assertEqual(1, live["knowledge_graph"]["edge_total"])
        self.assertIn("wiki", live)
        self.assertFalse(live["wiki"]["generation_policy"]["raw_events_included"])

        candidates = service.list_memories(status="candidate", query="review", limit=10)
        self.assertEqual(1, candidates["total"])
        self.assertEqual(self.candidate_id, candidates["items"][0]["id"])
        self.assertEqual("Admin Runbook", candidates["items"][0]["evidence"][0]["document_title"])

        detail = service.memory_detail(self.active_id)
        self.assertEqual(self.active_id, detail["memory"]["id"])
        self.assertEqual(1, len(detail["versions"]))
        self.assertEqual(1, len(detail["evidence"]))

        wiki = service.wiki_overview(scope="project:admin_demo")
        self.assertEqual(1, wiki["card_count"])
        self.assertEqual(self.active_id, wiki["cards"][0]["id"])
        self.assertIn("后台服务", wiki["cards"][0]["evidence"]["quote"])
        tenant_wiki = service.wiki_overview(
            scope="project:admin_demo",
            tenant_id="tenant:demo",
            organization_id="org:demo",
        )
        self.assertEqual(1, tenant_wiki["card_count"])
        other_tenant_wiki = service.wiki_overview(scope="project:admin_demo", tenant_id="tenant:none")
        self.assertEqual(0, other_tenant_wiki["card_count"])
        wiki_export = service.wiki_export_markdown(scope="project:admin_demo")
        self.assertIn("# 项目记忆卡册：project:admin_demo", wiki_export)
        self.assertIn("后台服务默认只绑定", wiki_export)
        self.assertIn("不包含 raw events", wiki_export)

        graph = service.graph_workspace(query="Reviewer")
        self.assertEqual(1, len(graph["nodes"]))
        self.assertEqual("feishu_user", graph["nodes"][0]["node_type"])
        self.assertEqual(1, len(graph["edges"]))

        compiled_graph = service.graph_workspace()
        self.assertGreaterEqual(compiled_graph["workspace_node_count"], 4)
        self.assertIn("memory", {node["node_type"] for node in compiled_graph["nodes"]})
        self.assertIn("grounded_by", {edge["edge_type"] for edge in compiled_graph["edges"]})
        tenant_graph = service.graph_workspace(tenant_id="tenant:demo", organization_id="org:demo", status="active")
        self.assertGreaterEqual(tenant_graph["workspace_node_count"], 4)
        self.assertEqual({"tenant:demo"}, {node["tenant_id"] for node in tenant_graph["nodes"]})
        other_tenant_graph = service.graph_workspace(tenant_id="tenant:none")
        self.assertEqual(0, other_tenant_graph["workspace_node_count"])
        self.assertEqual(0, other_tenant_graph["workspace_edge_count"])

        tenant_memories = service.list_memories(tenant_id="tenant:demo", organization_id="org:demo")
        self.assertEqual(2, tenant_memories["total"])
        other_tenant_memories = service.list_memories(tenant_id="tenant:none")
        self.assertEqual(0, other_tenant_memories["total"])

        tenant_audit = service.list_audit(tenant_id="tenant:demo", organization_id="org:demo")
        self.assertEqual(1, tenant_audit["total"])
        other_org_audit = service.list_audit(organization_id="org:other")
        self.assertEqual(0, other_org_audit["total"])

        tenants = service.tenant_overview()
        self.assertEqual(2, tenants["tenant_count"])
        self.assertNotIn("tenant_config_editor", tenants["missing_capabilities"])
        self.assertNotIn("role_policy_editor", tenants["missing_capabilities"])
        self.assertIn("enterprise_idp_sso_validation", tenants["missing_capabilities"])
        self.assertTrue(tenants["tenant_policy_editor_available"])
        demo_tenant = next(item for item in tenants["items"] if item["tenant_id"] == "tenant:demo")
        self.assertEqual("org:demo", demo_tenant["organization_id"])
        self.assertEqual(2, demo_tenant["memory_total"])
        self.assertEqual(1, demo_tenant["open_review_count"])
        self.assertEqual("available_unconfigured", demo_tenant["readiness"]["policy_editor"])
        self.assertEqual("header_gate_available_not_idp_validated", demo_tenant["readiness"]["sso"])
        filtered_tenants = service.tenant_overview(tenant_id="tenant:other", organization_id="org:other")
        self.assertEqual(1, filtered_tenants["tenant_count"])
        self.assertEqual("tenant:other", filtered_tenants["items"][0]["tenant_id"])

        upserted = service.upsert_tenant_policy(
            {
                "tenant_id": "tenant:demo",
                "organization_id": "org:demo",
                "status": "active",
                "default_visibility_policy": "team",
                "auto_confirm_low_risk": True,
                "require_review_for_conflicts": True,
                "reviewer_roles": ["reviewer", "owner"],
                "admin_users": ["Admin@Example.com"],
                "sso_allowed_domains": ["Example.com"],
                "notes": "staging tenant policy",
            },
            actor_id="copilot_admin_test",
        )
        self.assertTrue(upserted["created"])
        policies = service.tenant_policies(tenant_id="tenant:demo", organization_id="org:demo")
        self.assertEqual(1, policies["total"])
        self.assertEqual(["admin@example.com"], policies["items"][0]["admin_users"])
        updated_tenants = service.tenant_overview(tenant_id="tenant:demo", organization_id="org:demo")
        self.assertEqual("configured", updated_tenants["items"][0]["readiness"]["policy_editor"])
        self.assertEqual(
            "tenant_policy_upserted", service.list_audit(event_type="tenant_policy_upserted")["items"][0]["event_type"]
        )
        launch = service.launch_readiness()
        self.assertEqual("pass", launch["staging_status"])
        self.assertEqual("blocked", launch["production_status"])
        self.assertIn("enterprise_idp_sso_validation", {item["id"] for item in launch["production_blockers"]})
        self.assertIn("tenant_policy_editor", {item["id"] for item in launch["checks"]})

    def test_http_admin_is_read_only_and_serves_json_api(self) -> None:
        self._seed_rows()
        server = create_admin_server("127.0.0.1", 0, self.tmp.name)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"
            with urlopen(f"{base_url}/api/summary", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(3, payload["data"]["memory_total"])

            with urlopen(f"{base_url}/healthz", timeout=5) as response:
                healthz = json.loads(response.read().decode("utf-8"))
            self.assertTrue(healthz["ok"])

            with urlopen(f"{base_url}/metrics", timeout=5) as response:
                metrics = response.read().decode("utf-8")
                metrics_type = response.getheader("Content-Type")
            self.assertTrue(metrics_type.startswith("text/plain"))
            self.assertIn("copilot_admin_memory_total 3", metrics)
            self.assertIn("copilot_admin_launch_production_blocked 1", metrics)

            with urlopen(f"{base_url}/api/health", timeout=5) as response:
                health = json.loads(response.read().decode("utf-8"))
            self.assertTrue(health["ok"])
            self.assertFalse(health["data"]["read_only"])
            self.assertTrue(health["data"]["read_only_knowledge_surfaces"])
            self.assertTrue(health["data"]["tenant_policy_write_api"])
            self.assertTrue(health["data"]["wiki_ready"])

            with urlopen(f"{base_url}/api/live", timeout=5) as response:
                live_payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(live_payload["ok"])
            self.assertIn("msg_admin", {item["source_id"] for item in live_payload["data"]["recent_raw_events"]})

            with urlopen(f"{base_url}/api/launch-readiness", timeout=5) as response:
                launch_payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(launch_payload["ok"])
            self.assertEqual("blocked", launch_payload["data"]["production_status"])
            self.assertIn("llm_wiki", {item["id"] for item in launch_payload["data"]["checks"]})
            self.assertIn(
                "enterprise_idp_sso_validation",
                {item["id"] for item in launch_payload["data"]["production_blockers"]},
            )

            with urlopen(f"{base_url}/api/wiki?scope=project%3Aadmin_demo", timeout=5) as response:
                wiki_payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(wiki_payload["ok"])
            self.assertEqual(1, wiki_payload["data"]["card_count"])
            self.assertFalse(wiki_payload["data"]["generation_policy"]["writes_feishu"])

            with urlopen(f"{base_url}/api/wiki?tenant_id=tenant%3Anone", timeout=5) as response:
                other_tenant_wiki = json.loads(response.read().decode("utf-8"))
            self.assertTrue(other_tenant_wiki["ok"])
            self.assertEqual(0, other_tenant_wiki["data"]["card_count"])

            with urlopen(f"{base_url}/api/wiki/export?scope=project%3Aadmin_demo", timeout=5) as response:
                wiki_export = response.read().decode("utf-8")
                content_type = response.getheader("Content-Type")
            self.assertTrue(content_type.startswith("text/markdown"))
            self.assertIn("# 项目记忆卡册：project:admin_demo", wiki_export)
            self.assertIn("后台服务默认只绑定", wiki_export)

            with urlopen(f"{base_url}/api/graph?q=Reviewer", timeout=5) as response:
                graph_payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(graph_payload["ok"])
            self.assertEqual(1, len(graph_payload["data"]["nodes"]))

            with urlopen(f"{base_url}/api/graph?tenant_id=tenant%3Anone", timeout=5) as response:
                other_tenant_graph = json.loads(response.read().decode("utf-8"))
            self.assertTrue(other_tenant_graph["ok"])
            self.assertEqual(0, other_tenant_graph["data"]["workspace_node_count"])

            with urlopen(f"{base_url}/api/memories?organization_id=org%3Anone", timeout=5) as response:
                other_org_memories = json.loads(response.read().decode("utf-8"))
            self.assertTrue(other_org_memories["ok"])
            self.assertEqual(0, other_org_memories["data"]["total"])

            with urlopen(f"{base_url}/api/tenants?tenant_id=tenant%3Aother", timeout=5) as response:
                tenants_payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(tenants_payload["ok"])
            self.assertEqual(1, tenants_payload["data"]["tenant_count"])
            self.assertEqual("tenant:other", tenants_payload["data"]["items"][0]["tenant_id"])
            self.assertNotIn("tenant_config_editor", tenants_payload["data"]["missing_capabilities"])
            self.assertIn("enterprise_idp_sso_validation", tenants_payload["data"]["missing_capabilities"])

            with urlopen(f"{base_url}/api/tenant-policies?tenant_id=tenant%3Aother", timeout=5) as response:
                policies_payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(policies_payload["ok"])
            self.assertTrue(policies_payload["data"]["available"])

            with urlopen(base_url, timeout=5) as response:
                html = response.read().decode("utf-8")
            self.assertLess(html.index("<th>Updated</th>"), html.index("<th>Status</th>"))
            self.assertIn('data-view="home"', html)
            self.assertIn('data-view="wiki"', html)
            self.assertIn('data-view="graph"', html)
            self.assertIn('data-view="tenants"', html)
            self.assertIn('data-view="launch"', html)
            self.assertIn('id="organization"', html)
            self.assertIn('id="graph-detail"', html)
            self.assertIn("data-node-id", html)
            self.assertIn("data-edge-id", html)
            self.assertIn("Related edges", html)

            request = Request(f"{base_url}/api/memories", method="POST")
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=5)
            self.assertEqual(405, raised.exception.code)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_http_admin_api_requires_bearer_token_when_configured(self) -> None:
        self._seed_rows()
        server = create_admin_server(
            "127.0.0.1",
            0,
            self.tmp.name,
            auth_token="test-token",
            viewer_token="viewer-token",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base_url, timeout=5) as response:
                html = response.read().decode("utf-8")
            self.assertIn("Feishu Memory Copilot Admin", html)

            with self.assertRaises(HTTPError) as raised:
                urlopen(f"{base_url}/api/summary", timeout=5)
            self.assertEqual(401, raised.exception.code)

            with self.assertRaises(HTTPError) as raised:
                urlopen(f"{base_url}/api/wiki/export?scope=project%3Aadmin_demo", timeout=5)
            self.assertEqual(401, raised.exception.code)

            with self.assertRaises(HTTPError) as raised:
                urlopen(f"{base_url}/metrics", timeout=5)
            self.assertEqual(401, raised.exception.code)

            with urlopen(f"{base_url}/healthz", timeout=5) as response:
                healthz = json.loads(response.read().decode("utf-8"))
            self.assertTrue(healthz["ok"])

            request = Request(f"{base_url}/api/summary", headers={"Authorization": "Bearer test-token"})
            with urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(3, payload["data"]["memory_total"])

            request = Request(f"{base_url}/api/summary", headers={"Authorization": "Bearer viewer-token"})
            with urlopen(request, timeout=5) as response:
                viewer_payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(viewer_payload["ok"])
            self.assertEqual(3, viewer_payload["data"]["memory_total"])

            request = Request(f"{base_url}/metrics", headers={"Authorization": "Bearer viewer-token"})
            with urlopen(request, timeout=5) as response:
                metrics = response.read().decode("utf-8")
            self.assertIn("copilot_admin_tenant_count", metrics)
            self.assertIn('copilot_admin_launch_production_blocker{blocker="production_monitoring_alerts"} 1', metrics)

            policy_body = json.dumps(
                {
                    "tenant_id": "tenant:demo",
                    "organization_id": "org:demo",
                    "status": "active",
                    "default_visibility_policy": "team",
                    "reviewer_roles": ["reviewer", "owner"],
                    "admin_users": ["admin@example.com"],
                    "sso_allowed_domains": ["example.com"],
                    "auto_confirm_low_risk": True,
                    "require_review_for_conflicts": True,
                    "notes": "token protected policy",
                }
            ).encode("utf-8")
            request = Request(
                f"{base_url}/api/tenant-policies",
                data=policy_body,
                headers={"Authorization": "Bearer viewer-token", "Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=5)
            self.assertEqual(403, raised.exception.code)

            request = Request(
                f"{base_url}/api/tenant-policies",
                data=policy_body,
                headers={"Authorization": "Bearer test-token", "Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=5) as response:
                policy_payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(policy_payload["ok"])
            self.assertTrue(policy_payload["data"]["created"])
            self.assertEqual(["owner", "reviewer"], sorted(policy_payload["data"]["policy"]["reviewer_roles"]))

            request = Request(
                f"{base_url}/api/wiki/export?scope=project%3Aadmin_demo",
                headers={"Authorization": "Bearer viewer-token"},
            )
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=5)
            self.assertEqual(403, raised.exception.code)

            request = Request(
                f"{base_url}/api/wiki/export?scope=project%3Aadmin_demo",
                headers={"Authorization": "Bearer test-token"},
            )
            with urlopen(request, timeout=5) as response:
                wiki_export = response.read().decode("utf-8")
            self.assertIn("# 项目记忆卡册：project:admin_demo", wiki_export)

            request = Request(f"{base_url}/api/health", headers={"Authorization": "Bearer test-token"})
            with urlopen(request, timeout=5) as response:
                health = json.loads(response.read().decode("utf-8"))
            self.assertEqual("enabled", health["data"]["auth"])
            self.assertTrue(health["data"]["access_policy"]["admin_token_configured"])
            self.assertTrue(health["data"]["access_policy"]["viewer_token_configured"])
            self.assertFalse(health["data"]["access_policy"]["viewer_token_can_export"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_http_admin_api_accepts_sso_headers_from_loopback_proxy(self) -> None:
        self._seed_rows()
        sso_config = AdminSsoConfig(
            enabled=True,
            admin_users=frozenset({"admin@example.com"}),
            allowed_domains=frozenset({"example.com"}),
        )
        server = create_admin_server("127.0.0.1", 0, self.tmp.name, sso_config=sso_config)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"
            with self.assertRaises(HTTPError) as raised:
                urlopen(f"{base_url}/api/summary", timeout=5)
            self.assertEqual(401, raised.exception.code)

            request = Request(f"{base_url}/api/summary", headers={"X-Forwarded-Email": "reader@example.com"})
            with urlopen(request, timeout=5) as response:
                viewer_payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(viewer_payload["ok"])
            self.assertEqual(3, viewer_payload["data"]["memory_total"])

            request = Request(
                f"{base_url}/api/wiki/export?scope=project%3Aadmin_demo",
                headers={"X-Forwarded-Email": "reader@example.com"},
            )
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=5)
            self.assertEqual(403, raised.exception.code)

            request = Request(
                f"{base_url}/api/wiki/export?scope=project%3Aadmin_demo",
                headers={"X-Forwarded-Email": "admin@example.com"},
            )
            with urlopen(request, timeout=5) as response:
                wiki_export = response.read().decode("utf-8")
            self.assertIn("# 项目记忆卡册：project:admin_demo", wiki_export)

            request = Request(f"{base_url}/api/health", headers={"X-Forwarded-Email": "admin@example.com"})
            with urlopen(request, timeout=5) as response:
                health = json.loads(response.read().decode("utf-8"))
            self.assertEqual("enabled", health["data"]["auth"])
            self.assertTrue(health["data"]["access_policy"]["sso_enabled"])
            self.assertTrue(health["data"]["access_policy"]["sso_admin_users_configured"])
            self.assertTrue(health["data"]["access_policy"]["sso_allowed_domains_configured"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_embedded_admin_starts_with_runtime_and_can_shutdown(self) -> None:
        self._seed_rows()

        runtime = start_embedded_admin(host="127.0.0.1", port=0, db_path=self.tmp.name, enabled=True)
        try:
            self.assertTrue(runtime.enabled)
            self.assertIsNotNone(runtime.url)
            assert runtime.url is not None
            with urlopen(f"{runtime.url}/api/summary", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(3, payload["data"]["memory_total"])
        finally:
            runtime.stop()

    def test_copilot_feishu_listen_defaults_to_embedded_admin(self) -> None:
        parser = build_parser()

        args = parser.parse_args(["copilot-feishu", "listen"])

        self.assertTrue(args.admin)
        self.assertEqual("127.0.0.1", args.admin_host)
        self.assertEqual(8765, args.admin_port)

        disabled = parser.parse_args(["copilot-feishu", "listen", "--no-admin"])
        self.assertFalse(disabled.admin)

    def test_admin_start_script_rejects_remote_bind_without_token(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/start_copilot_admin.py",
                "--host",
                "0.0.0.0",
                "--port",
                "0",
                "--db-path",
                self.tmp.name,
            ],
            cwd=".",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(2, result.returncode)
        self.assertIn("non-loopback host without an access token", result.stderr)

    def test_admin_readiness_strict_mode_requires_auth_wiki_and_graph(self) -> None:
        self._seed_rows()

        strict_ok = run_admin_readiness(
            db_path=Path(self.tmp.name),
            host="0.0.0.0",
            admin_token="test-token",
            strict=True,
        )
        self.assertTrue(strict_ok["ok"])
        self.assertEqual("pass", strict_ok["checks"]["wiki"]["status"])
        self.assertEqual("pass", strict_ok["checks"]["graph"]["status"])
        self.assertEqual("pass", strict_ok["checks"]["tenants"]["status"])
        self.assertEqual(2, strict_ok["checks"]["tenants"]["tenant_count"])
        self.assertTrue(strict_ok["checks"]["tenants"]["tenant_policy_editor_available"])
        self.assertNotIn("tenant_config_editor", strict_ok["checks"]["tenants"]["missing_capabilities"])
        self.assertIn("enterprise_idp_sso_validation", strict_ok["checks"]["tenants"]["missing_capabilities"])
        self.assertEqual("pass", strict_ok["checks"]["access_policy"]["status"])

        missing_auth = run_admin_readiness(
            db_path=Path(self.tmp.name),
            host="127.0.0.1",
            admin_token=None,
            strict=True,
        )
        self.assertFalse(missing_auth["ok"])
        self.assertEqual("fail", missing_auth["checks"]["remote_bind_auth"]["status"])

        viewer_only = run_admin_readiness(
            db_path=Path(self.tmp.name),
            host="0.0.0.0",
            admin_token=None,
            viewer_token="viewer-token",
            strict=True,
        )
        self.assertFalse(viewer_only["ok"])
        self.assertEqual("pass", viewer_only["checks"]["remote_bind_auth"]["status"])
        self.assertEqual("fail", viewer_only["checks"]["access_policy"]["status"])

        sso_ok = run_admin_readiness(
            db_path=Path(self.tmp.name),
            host="127.0.0.1",
            admin_token=None,
            sso_config=AdminSsoConfig(
                enabled=True,
                admin_users=frozenset({"admin@example.com"}),
                allowed_domains=frozenset({"example.com"}),
            ),
            strict=True,
        )
        self.assertTrue(sso_ok["ok"])
        self.assertEqual("pass", sso_ok["checks"]["remote_bind_auth"]["status"])
        self.assertEqual("pass", sso_ok["checks"]["access_policy"]["status"])
        self.assertTrue(sso_ok["checks"]["access_policy"]["sso_enabled"])

        remote_sso_only = run_admin_readiness(
            db_path=Path(self.tmp.name),
            host="0.0.0.0",
            admin_token=None,
            sso_config=AdminSsoConfig(
                enabled=True,
                admin_users=frozenset({"admin@example.com"}),
                allowed_domains=frozenset({"example.com"}),
            ),
            strict=True,
        )
        self.assertFalse(remote_sso_only["ok"])
        self.assertEqual("fail", remote_sso_only["checks"]["remote_bind_auth"]["status"])

        too_few_cards = run_admin_readiness(
            db_path=Path(self.tmp.name),
            host="127.0.0.1",
            admin_token="test-token",
            min_wiki_cards=3,
        )
        self.assertFalse(too_few_cards["ok"])
        self.assertEqual("fail", too_few_cards["checks"]["wiki"]["status"])


if __name__ == "__main__":
    unittest.main()
