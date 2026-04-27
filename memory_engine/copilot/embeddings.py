from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass


CURATED_EMBEDDING_FIELDS = ("type", "subject", "current_value", "summary", "evidence_quote")


@dataclass(frozen=True)
class CuratedMemoryEmbeddingText:
    """Curated memory text allowed to enter the local vector signal."""

    type: str
    subject: str
    current_value: str
    summary: str | None = None
    evidence_quote: str | None = None

    def to_text(self) -> str:
        parts = [
            f"type: {self.type}",
            f"subject: {self.subject}",
            f"current_value: {self.current_value}",
        ]
        if self.summary:
            parts.append(f"summary: {self.summary}")
        if self.evidence_quote:
            parts.append(f"evidence.quote: {self.evidence_quote}")
        return "\n".join(parts)


class DeterministicEmbeddingProvider:
    """Small deterministic fallback for local recall tests.

    This is intentionally not a production embedding model. It gives the MVP a
    stable vector-like signal without introducing a new dependency or embedding
    raw events.
    """

    def __init__(self, *, dimension: int = 64) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        self.dimension = dimension

    def embed_curated_memory(self, text: CuratedMemoryEmbeddingText) -> list[float]:
        return self.embed_text(text.to_text())

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in _tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign * (1.0 + min(len(token), 8) / 8.0)
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [round(value / norm, 8) for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have the same dimension")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return round(sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm), 6)


def _tokens(text: str) -> list[str]:
    lowered = text.lower()
    words = re.findall(r"[a-z0-9_./:-]+", lowered)
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", lowered)
    return words + cjk_chars
