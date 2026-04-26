"""Feishu Memory Copilot core contracts.

This package is the new OpenClaw-native Copilot surface. It intentionally
starts with schemas and adapter boundaries before wiring retrieval or
governance behavior into the old Day 1 repository implementation.
"""

from .schemas import (
    CandidateSource,
    ConfirmRequest,
    CopilotError,
    CreateCandidateRequest,
    ExplainVersionsRequest,
    PrefetchRequest,
    RejectRequest,
    SearchRequest,
    ValidationError,
)

__all__ = [
    "CandidateSource",
    "ConfirmRequest",
    "CopilotError",
    "CreateCandidateRequest",
    "ExplainVersionsRequest",
    "PrefetchRequest",
    "RejectRequest",
    "SearchRequest",
    "ValidationError",
]
