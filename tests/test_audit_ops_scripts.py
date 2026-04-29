from __future__ import annotations

import sqlite3
import tempfile
import unittest

from memory_engine.db import init_db
from memory_engine.repository import MemoryRepository, now_ms
from scripts.check_audit_alerts import (
    check_consecutive_denies,
    check_ingestion_failure_rate,
)
from scripts.query_audit_events import (
    count_events,
    format_csv,
    query_events,
    summary_by_field,
)


class AuditOpsScriptsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(prefix="audit_ops_", suffix=".sqlite")
        self.conn = sqlite3.connect(self.tmp.name)
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)
        self.repo = MemoryRepository(self.conn)
        self.now = now_ms()

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.close()

    def _record(
        self,
        *,
        event_type: str,
        action: str,
        actor_id: str = "u_ops",
        tenant_id: str = "tenant:demo",
        permission_decision: str = "allow",
        reason_code: str = "scope_access_granted",
    ) -> None:
        with self.conn:
            self.repo.record_audit_event(
                event_type=event_type,
                action=action,
                actor_id=actor_id,
                tenant_id=tenant_id,
                scope="project:feishu_ai_challenge",
                permission_decision=permission_decision,
                reason_code=reason_code,
                request_id=f"req_{event_type}_{reason_code}",
                trace_id=f"trace_{event_type}_{reason_code}",
                created_at=self.now,
            )

    def test_query_events_filters_and_summarizes_ops_fields(self) -> None:
        self._record(event_type="permission_denied", action="memory.search", permission_decision="deny")
        self._record(
            event_type="ingestion_failed",
            action="memory.create_candidate",
            actor_id="u_ingest",
            permission_decision="withhold",
            reason_code="feishu_fetch_failed",
        )

        events = query_events(
            self.conn,
            event_type="ingestion_failed",
            tenant_id="tenant:demo",
            limit=10,
        )
        self.assertEqual(1, len(events))
        self.assertEqual("u_ingest", events[0]["actor_id"])
        self.assertEqual("feishu_fetch_failed", events[0]["reason_code"])
        self.assertEqual(1, count_events(self.conn, permission_decision="deny"))

        summary = summary_by_field(self.conn, group_by="event_type")
        self.assertEqual(
            {"permission_denied": 1, "ingestion_failed": 1},
            {row["group"]: row["count"] for row in summary},
        )
        csv_output = format_csv(events)
        self.assertIn("audit_id,event_type", csv_output)
        self.assertIn("ingestion_failed", csv_output)

    def test_alerts_use_explicit_ingestion_failed_event(self) -> None:
        self._record(event_type="limited_ingestion_candidate", action="memory.create_candidate")
        self._record(
            event_type="ingestion_failed",
            action="memory.create_candidate",
            permission_decision="withhold",
            reason_code="feishu_fetch_failed",
        )

        alert = check_ingestion_failure_rate(self.conn, threshold=0.4, window_minutes=60)

        self.assertIsNotNone(alert)
        assert alert is not None
        self.assertEqual("ingestion_failure_rate", alert["alert_type"])
        self.assertEqual(1, alert["count"])
        self.assertEqual(2, alert["total"])

    def test_consecutive_deny_alert_still_works(self) -> None:
        for index in range(3):
            self._record(
                event_type="permission_denied",
                action="memory.search",
                actor_id=f"u_denied_{index}",
                permission_decision="deny",
                reason_code="tenant_mismatch",
            )

        alert = check_consecutive_denies(self.conn, threshold=3, window_minutes=60)

        self.assertIsNotNone(alert)
        assert alert is not None
        self.assertEqual("consecutive_permission_deny", alert["alert_type"])
        self.assertEqual(3, alert["count"])


if __name__ == "__main__":
    unittest.main()
