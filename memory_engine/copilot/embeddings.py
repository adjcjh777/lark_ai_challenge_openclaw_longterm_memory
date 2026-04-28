from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

CURATED_EMBEDDING_FIELDS = ("type", "subject", "current_value", "summary", "evidence_quote")

# Lock file path for embedding provider configuration
_EMBEDDING_LOCK_FILE = Path(__file__).resolve().parent / "embedding-provider.lock"


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


class OllamaEmbeddingProvider:
    """Real embedding provider using Ollama via litellm.

    This provider uses the Ollama API to generate real semantic embeddings
    using the qwen3-embedding:0.6b-fp16 model. It includes error handling,
    retry logic, and LRU caching for performance.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        endpoint: str | None = None,
        dimension: int = 1024,
        timeout: float = 30.0,
        max_retries: int = 3,
        cache_size: int = 1024,
    ) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")

        # Load configuration from lock file and environment variables
        config = _load_embedding_config()
        self.model = model or config.get("litellm_model") or "ollama/qwen3-embedding:0.6b-fp16"
        self.endpoint = endpoint or config.get("endpoint") or "http://localhost:11434"
        self.dimension = int(config.get("dimensions", str(dimension)))
        self.timeout = timeout
        self.max_retries = max_retries
        self._initialized = False
        self._litellm_available = False

        # LRU cache for embeddings
        self._cache_size = cache_size
        self._embed_text_cache: dict[str, list[float]] = {}
        self._embed_curated_cache: dict[str, list[float]] = {}

        # Initialize litellm
        self._init_litellm()

    def _init_litellm(self) -> None:
        """Initialize litellm and verify availability."""
        try:
            import litellm
            self._litellm_available = True
            self._initialized = True
            logger.info(
                "OllamaEmbeddingProvider initialized: model=%s, endpoint=%s, dimension=%d",
                self.model,
                self.endpoint,
                self.dimension,
            )
        except ImportError:
            self._litellm_available = False
            self._initialized = False
            logger.warning(
                "litellm not available, OllamaEmbeddingProvider cannot be used. "
                "Install litellm: pip install litellm"
            )

    def is_available(self) -> bool:
        """Check if the provider is available and configured."""
        return self._initialized and self._litellm_available

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a text string with caching and retry logic."""
        if not self.is_available():
            raise RuntimeError("OllamaEmbeddingProvider is not available")

        # Check cache
        cache_key = f"text:{text}"
        if cache_key in self._embed_text_cache:
            return self._embed_text_cache[cache_key]

        # Generate embedding with retry
        vector = self._embed_with_retry(text)

        # Cache the result (simple LRU - remove oldest if full)
        if len(self._embed_text_cache) >= self._cache_size:
            # Remove first item (FIFO approximation of LRU)
            oldest_key = next(iter(self._embed_text_cache))
            del self._embed_text_cache[oldest_key]
        self._embed_text_cache[cache_key] = vector

        return vector

    def embed_curated_memory(self, text: CuratedMemoryEmbeddingText) -> list[float]:
        """Generate embedding for a curated memory with caching and retry logic."""
        if not self.is_available():
            raise RuntimeError("OllamaEmbeddingProvider is not available")

        # Check cache
        cache_key = f"curated:{text.to_text()}"
        if cache_key in self._embed_curated_cache:
            return self._embed_curated_cache[cache_key]

        # Generate embedding with retry
        vector = self._embed_with_retry(text.to_text())

        # Cache the result
        if len(self._embed_curated_cache) >= self._cache_size:
            oldest_key = next(iter(self._embed_curated_cache))
            del self._embed_curated_cache[oldest_key]
        self._embed_curated_cache[cache_key] = vector

        return vector

    def _embed_with_retry(self, text: str) -> list[float]:
        """Embed text with retry logic for network errors."""
        import litellm

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                # Check if we're in an asyncio event loop
                try:
                    loop = asyncio.get_running_loop()
                    # If we're in an event loop, use thread pool to avoid blocking
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            litellm.embedding,
                            model=self.model,
                            input=[text],
                            api_base=self.endpoint,
                        )
                        response = future.result(timeout=self.timeout)
                except RuntimeError:
                    # No running event loop, use synchronous call
                    response = litellm.embedding(
                        model=self.model,
                        input=[text],
                        api_base=self.endpoint,
                    )

                embedding = response.data[0]["embedding"]
                vector = list(embedding)

                # Validate dimension
                if len(vector) != self.dimension:
                    raise ValueError(
                        f"Expected embedding dimension {self.dimension}, "
                        f"got {len(vector)}"
                    )

                return vector

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Embedding attempt %d/%d failed: %s",
                    attempt + 1,
                    self.max_retries,
                    str(exc),
                )
                if attempt < self.max_retries - 1:
                    # Exponential backoff
                    time.sleep(0.5 * (2 ** attempt))

        raise RuntimeError(
            f"Failed to generate embedding after {self.max_retries} attempts: "
            f"{last_error}"
        )

    def batch_embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts in a single API call."""
        if not self.is_available():
            raise RuntimeError("OllamaEmbeddingProvider is not available")

        import litellm

        try:
            response = litellm.embedding(
                model=self.model,
                input=texts,
                api_base=self.endpoint,
            )
            embeddings = [list(item["embedding"]) for item in response.data]

            # Validate dimensions
            for i, vector in enumerate(embeddings):
                if len(vector) != self.dimension:
                    raise ValueError(
                        f"Expected embedding dimension {self.dimension} at index {i}, "
                        f"got {len(vector)}"
                    )

            return embeddings

        except Exception as exc:
            logger.error("Batch embedding failed: %s", str(exc))
            raise

    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        self._embed_text_cache.clear()
        self._embed_curated_cache.clear()
        logger.info("Embedding cache cleared")


def _load_embedding_config() -> dict[str, str]:
    """Load embedding configuration from lock file and environment variables."""
    config: dict[str, str] = {}

    # Load from lock file
    if _EMBEDDING_LOCK_FILE.exists():
        try:
            for line in _EMBEDDING_LOCK_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip().strip('"').strip("'")
        except Exception as exc:
            logger.warning("Failed to read embedding lock file: %s", exc)

    # Environment variables override lock file
    env_mapping = {
        "EMBEDDING_MODEL": "litellm_model",
        "EMBEDDING_ENDPOINT": "endpoint",
        "EMBEDDING_DIMENSIONS": "dimensions",
    }
    for env_key, config_key in env_mapping.items():
        value = os.environ.get(env_key)
        if value:
            config[config_key] = value

    return config


def create_embedding_provider(
    *,
    provider: str | None = None,
    fallback: bool = True,
) -> OllamaEmbeddingProvider | DeterministicEmbeddingProvider:
    """Factory function to create the appropriate embedding provider.

    Tries to create an OllamaEmbeddingProvider first. If it fails and
    fallback is True, returns a DeterministicEmbeddingProvider.
    """
    provider_name = provider or os.environ.get("EMBEDDING_PROVIDER", "ollama")

    if provider_name == "ollama":
        try:
            ollama_provider = OllamaEmbeddingProvider()
            if ollama_provider.is_available():
                logger.info("Using OllamaEmbeddingProvider")
                return ollama_provider
            else:
                logger.warning("OllamaEmbeddingProvider not available, trying fallback")
        except Exception as exc:
            logger.warning("Failed to create OllamaEmbeddingProvider: %s", exc)

    if fallback:
        logger.info("Using DeterministicEmbeddingProvider as fallback")
        return DeterministicEmbeddingProvider()

    raise RuntimeError(f"Embedding provider '{provider_name}' is not available")


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
