from __future__ import annotations

import unittest

from memory_engine.copilot.schemas import (
    CandidateSource,
    CopilotError,
    CreateCandidateRequest,
    PrefetchRequest,
    ExplainVersionsRequest,
    ConfirmRequest,
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

    def test_search_request_rejects_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            SearchRequest.from_payload(
                {
                    "query": "production deployment region",
                    "scope": "project:feishu_ai_challenge",
                    "unexpected": "value",
                }
            )

    def test_search_request_rejects_invalid_filters(self) -> None:
        invalid_payloads = [
            {"query": "deployment", "scope": "project:feishu_ai_challenge", "filters": {"layer": "L9"}},
            {"query": "deployment", "scope": "project:feishu_ai_challenge", "filters": {"status": "unknown"}},
            {"query": "deployment", "scope": "project:feishu_ai_challenge", "filters": {"type": "chat"}},
            {"query": "deployment", "scope": "project:feishu_ai_challenge", "filters": {"extra": "value"}},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                SearchRequest.from_payload(payload)

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

    def test_create_candidate_rejects_non_boolean_auto_confirm(self) -> None:
        for value in ("false", "0", 1):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                CreateCandidateRequest.from_payload(
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
                        "auto_confirm": value,
                    }
                )

    def test_explain_versions_rejects_non_boolean_include_archived(self) -> None:
        for value in ("false", "0", 1):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                ExplainVersionsRequest.from_payload(
                    {
                        "memory_id": "mem_1",
                        "scope": "project:feishu_ai_challenge",
                        "include_archived": value,
                    }
                )

    def test_confirm_request_rejects_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            ConfirmRequest.from_payload(
                {
                    "candidate_id": "mem_1",
                    "scope": "project:feishu_ai_challenge",
                    "actor_id": "user_1",
                    "unexpected": "value",
                }
            )

    def test_prefetch_requires_current_context(self) -> None:
        with self.assertRaises(ValidationError):
            PrefetchRequest.from_payload(
                {
                    "task": "deployment_checklist",
                    "scope": "project:feishu_ai_challenge",
                }
            )

    def test_prefetch_rejects_empty_current_context(self) -> None:
        with self.assertRaises(ValidationError):
            PrefetchRequest.from_payload(
                {
                    "task": "deployment_checklist",
                    "scope": "project:feishu_ai_challenge",
                    "current_context": {},
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
