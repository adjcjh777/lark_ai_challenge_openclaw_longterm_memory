"""Feishu Memory Copilot core contracts.

This package is the new OpenClaw-native Copilot surface. It intentionally
starts with schemas and adapter boundaries before wiring retrieval or
governance behavior into the old Day 1 repository implementation.
"""

from .schemas import (
    CandidateMemory,
    CandidateSource,
    ConfirmRequest,
    CopilotError,
    CreateCandidateRequest,
    Evidence,
    ExplainVersionsRequest,
    MemoryResult,
    PrefetchRequest,
    RecallTrace,
    RejectRequest,
    SearchRequest,
    SearchResponse,
    ValidationError,
)

__all__ = [
    "CandidateSource",
    "CandidateMemory",
    "ConfirmRequest",
    "CopilotError",
    "CreateCandidateRequest",
    "Evidence",
    "ExplainVersionsRequest",
    "MemoryResult",
    "PrefetchRequest",
    "RecallTrace",
    "RejectRequest",
    "SearchRequest",
    "SearchResponse",
    "ValidationError",
]
