from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from memory_engine.copilot.admin import AdminQueryService, create_admin_server
from memory_engine.db import init_db
from memory_engine.repository import MemoryRepository, now_ms


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
        self.active_id = active["memory_id"]
        self.candidate_id = candidate["memory_id"]

    def test_query_service_summarizes_and_filters_memory_rows(self) -> None:
        self._seed_rows()

        service = AdminQueryService(self.conn)
        summary = service.summary()
        self.assertEqual(2, summary["memory_total"])
        self.assertEqual({"active": 1, "candidate": 1}, summary["memory_by_status"])
        self.assertEqual(1, summary["audit_total"])

        candidates = service.list_memories(status="candidate", query="review", limit=10)
        self.assertEqual(1, candidates["total"])
        self.assertEqual(self.candidate_id, candidates["items"][0]["id"])
        self.assertEqual("Admin Runbook", candidates["items"][0]["evidence"][0]["document_title"])

        detail = service.memory_detail(self.active_id)
        self.assertEqual(self.active_id, detail["memory"]["id"])
        self.assertEqual(1, len(detail["versions"]))
        self.assertEqual(1, len(detail["evidence"]))

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
            self.assertEqual(2, payload["data"]["memory_total"])

            request = Request(f"{base_url}/api/memories", method="POST")
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=5)
            self.assertEqual(405, raised.exception.code)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
