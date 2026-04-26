from __future__ import annotations

import unittest

from memory_engine.copilot.schemas import (
    CandidateSource,
    CopilotError,
    CreateCandidateRequest,
    PrefetchRequest,
    SearchRequest,
    ValidationError,
)


class CopilotSchemaTest(unittest.TestCase):
    def test_search_request_defaults_to_active_status(self) -> None:
        request = SearchRequest.from_payload(
            {
                "query": "production deployment region",
                "scope": "project:feishu_ai_challenge",
            }
        )

        self.assertEqual(3, request.top_k)
        self.assertEqual({"status": "active"}, request.filters)

    def test_search_request_rejects_invalid_scope(self) -> None:
        with self.assertRaises(ValidationError):
            SearchRequest.from_payload({"query": "deployment", "scope": "feishu_ai_challenge"})

    def test_candidate_source_requires_evidence_quote(self) -> None:
        with self.assertRaises(ValidationError):
            CandidateSource.from_payload(
                {
                    "source_type": "feishu_message",
                    "source_id": "msg_1",
                    "actor_id": "user_1",
                    "created_at": "2026-04-26T10:00:00+08:00",
                }
            )

    def test_create_candidate_preserves_source_evidence(self) -> None:
        request = CreateCandidateRequest.from_payload(
            {
                "text": "Production deployment must use --canary.",
                "scope": "project:feishu_ai_challenge",
                "source": {
                    "source_type": "feishu_message",
                    "source_id": "msg_1",
                    "actor_id": "user_1",
                    "created_at": "2026-04-26T10:00:00+08:00",
                    "quote": "Production deployment must use --canary.",
                },
            }
        )

        self.assertFalse(request.auto_confirm)
        self.assertEqual("msg_1", request.source.source_id)
        self.assertEqual("Production deployment must use --canary.", request.source.quote)

    def test_prefetch_requires_current_context(self) -> None:
        with self.assertRaises(ValidationError):
            PrefetchRequest.from_payload(
                {
                    "task": "deployment_checklist",
                    "scope": "project:feishu_ai_challenge",
                }
            )

    def test_error_response_shape_is_stable(self) -> None:
        response = CopilotError("scope_required", "scope is required").to_response()

        self.assertFalse(response["ok"])
        self.assertEqual("scope_required", response["error"]["code"])
        self.assertFalse(response["error"]["retryable"])
        self.assertEqual({}, response["error"]["details"])


if __name__ == "__main__":
    unittest.main()
