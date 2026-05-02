from __future__ import annotations

import asyncio
import importlib
import os
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Protocol

from memory_engine.models import parse_scope

from .schemas import Evidence, MemoryResult

DEFAULT_COGNEE_EMBEDDING_MAX_BATCH_SIZE = 10


class CogneeAdapterNotConfigured(RuntimeError):
    """Raised when the boundary is called before a Cognee client is injected."""


class CogneeConfigurationError(RuntimeError):
    """Raised when Cognee configuration is invalid or missing."""


def load_cognee_client() -> CogneeClient:
    """Load the Cognee SDK client.

    Returns:
        The cognee module as a client.

    Raises:
        ModuleNotFoundError: If cognee SDK is not installed.
        CogneeConfigurationError: If required environment variables are missing.
    """
    try:
        cognee_module = importlib.import_module("cognee")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError("cognee SDK is not installed. Install it with: pip install cognee") from exc

    # Validate configuration
    _validate_cognee_configuration()

    # Configure Cognee LLM provider
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    if provider == "ollama":
        cognee_module.config.set_llm_provider("ollama")
        # Ollama OpenAI-compatible endpoint needs /v1 suffix
        base_endpoint = os.environ.get("LLM_ENDPOINT", "http://localhost:11434")
        llm_endpoint = base_endpoint.rstrip("/") + "/v1"
        cognee_module.config.set_llm_endpoint(llm_endpoint)
        cognee_module.config.set_llm_model(os.environ.get("LLM_MODEL", "qwen3.5:0.8b"))
        # Ollama doesn't need an API key, but Cognee's OpenAI client requires a non-empty value
        cognee_module.config.set_llm_api_key("ollama")
    elif provider == "custom":
        cognee_module.config.set_llm_provider("custom")
        cognee_module.config.set_llm_endpoint(os.environ.get("LLM_ENDPOINT"))
        cognee_module.config.set_llm_model(os.environ.get("LLM_MODEL"))
        api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if api_key:
            cognee_module.config.set_llm_api_key(api_key)

    _patch_cognee_embedding_batch_limit()

    return cognee_module


def _validate_cognee_configuration() -> None:
    """Validate that required Cognee configuration is present.

    Raises:
        CogneeConfigurationError: If required environment variables are missing.
    """
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    llm_api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")

    # Ollama doesn't require an API key
    if provider != "ollama" and not llm_api_key:
        raise CogneeConfigurationError("Missing LLM API key. Set OPENAI_API_KEY or LLM_API_KEY in .env file.")

    if provider == "custom" and not os.environ.get("LLM_ENDPOINT"):
        raise CogneeConfigurationError("LLM_ENDPOINT is required for Cognee custom provider. Set it in .env file.")

    embedding_model = os.environ.get("EMBEDDING_MODEL")
    if not embedding_model:
        raise CogneeConfigurationError("EMBEDDING_MODEL is required for Cognee embeddings. Set it in .env file.")

    if embedding_model.startswith("ollama/") and not os.environ.get("EMBEDDING_ENDPOINT"):
        raise CogneeConfigurationError(
            "EMBEDDING_ENDPOINT is required for local Ollama embeddings. Set it in .env file."
        )


def _patch_cognee_embedding_batch_limit() -> None:
    """Limit Cognee LiteLLM embedding batches for providers with small caps.

    The installed Cognee SDK forwards the whole batch to LiteLLM and only
    splits on context-window errors. Some OpenAI-compatible embedding providers
    reject batches larger than 10 items, so keep the compatibility shim inside
    the Cognee adapter boundary.
    """

    max_batch_size = _cognee_embedding_max_batch_size()
    if max_batch_size <= 0:
        return
    try:
        module = importlib.import_module(
            "cognee.infrastructure.databases.vector.embeddings.LiteLLMEmbeddingEngine"
        )
        engine_class = getattr(module, "LiteLLMEmbeddingEngine")
    except Exception:
        return

    original = getattr(engine_class, "_feishu_memory_original_embed_text", None)
    if original is None:
        original = engine_class.embed_text
        setattr(engine_class, "_feishu_memory_original_embed_text", original)

    if getattr(engine_class, "_feishu_memory_max_batch_size", None) == max_batch_size:
        return

    async def embed_text_with_batch_limit(self: Any, text: Any) -> Any:
        if not isinstance(text, list) or len(text) <= max_batch_size:
            return await original(self, text)
        vectors: list[Any] = []
        for index in range(0, len(text), max_batch_size):
            chunk = text[index : index + max_batch_size]
            vectors.extend(await original(self, chunk))
        return vectors

    setattr(engine_class, "embed_text", embed_text_with_batch_limit)
    setattr(engine_class, "_feishu_memory_max_batch_size", max_batch_size)


def _cognee_embedding_max_batch_size() -> int:
    raw_value = (
        os.environ.get("COGNEE_EMBEDDING_MAX_BATCH_SIZE")
        or os.environ.get("EMBEDDING_MAX_BATCH_SIZE")
        or str(DEFAULT_COGNEE_EMBEDDING_MAX_BATCH_SIZE)
    )
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return DEFAULT_COGNEE_EMBEDDING_MAX_BATCH_SIZE
    return value if value > 0 else DEFAULT_COGNEE_EMBEDDING_MAX_BATCH_SIZE


class CogneeClient(Protocol):
    def remember(self, *args: Any, **kwargs: Any) -> Any: ...

    def recall(self, *args: Any, **kwargs: Any) -> Any: ...

    def improve(self, *args: Any, **kwargs: Any) -> Any: ...

    def forget(self, *args: Any, **kwargs: Any) -> Any: ...

    def add(self, *args: Any, **kwargs: Any) -> Any: ...

    def cognify(self, *args: Any, **kwargs: Any) -> Any: ...

    def search(self, *args: Any, **kwargs: Any) -> Any: ...


@dataclass
class CogneeMemoryAdapter:
    """Narrow Cognee boundary for the Copilot core.

    The project contract is that only this adapter should talk to Cognee
    directly. The first day skeleton keeps the dependency optional so tests and
    legacy benchmark commands still run without installing Cognee.
    """

    client: CogneeClient | None = None
    dataset_prefix: str = "feishu_memory_copilot"
    _auto_load_attempted: bool = field(default=False, repr=False)

    @property
    def is_configured(self) -> bool:
        return self.client is not None

    def ensure_client(self) -> CogneeClient:
        """Ensure a Cognee client is loaded, attempting auto-load if needed.

        Returns:
            The configured Cognee client.

        Raises:
            CogneeAdapterNotConfigured: If client cannot be loaded.
            CogneeConfigurationError: If configuration is invalid.
        """
        if self.client is not None:
            return self.client

        if self._auto_load_attempted:
            raise CogneeAdapterNotConfigured(
                "Cognee client auto-load was attempted but failed. "
                "Check .env configuration and ensure cognee SDK is installed."
            )

        self._auto_load_attempted = True
        try:
            self.client = load_cognee_client()
            return self.client
        except (ModuleNotFoundError, CogneeConfigurationError) as exc:
            raise CogneeAdapterNotConfigured(str(exc)) from exc

    def dataset_for_scope(self, scope: str) -> str:
        parsed = parse_scope(scope)
        scope_key = f"{parsed.scope_type}_{parsed.scope_id}"
        safe_scope = re.sub(r"[^a-zA-Z0-9_]+", "_", scope_key).strip("_").lower()
        return f"{self.dataset_prefix}_{safe_scope}"

    def add_raw_event(self, scope: str, content: str, **metadata: Any) -> Any:
        return self.add(scope, content)

    def cognify_scope(self, scope: str, **kwargs: Any) -> Any:
        return self._call("cognify", datasets=self.dataset_for_scope(scope), **kwargs)

    def remember_candidate_text(self, scope: str, content: str, **metadata: Any) -> Any:
        if self.client is not None and hasattr(self.client, "remember"):
            return self.remember(scope, content, metadata=metadata)
        return self.add_raw_event(scope, content, **metadata)

    def sync_curated_memory(self, scope: str, memory: dict[str, Any]) -> dict[str, Any]:
        """Upsert a Copilot-owned active memory into the scope dataset.

        Cognee is an optional recall channel, so this method sends only curated
        memory fields plus ledger metadata. Raw event payloads stay in SQLite.
        """

        metadata = _curated_memory_metadata(memory)
        document = curated_memory_document(memory, metadata=metadata)
        add_result = self.add(scope, document, metadata=metadata)
        cognify_result = self.cognify_scope(scope)
        return {
            "ok": True,
            "dataset_name": self.dataset_for_scope(scope),
            "memory_id": metadata.get("memory_id"),
            "version": metadata.get("version"),
            "document": document,
            "add_result": add_result,
            "cognify_result": cognify_result,
        }

    def sync_memory_withdrawal(self, scope: str, memory_id: str, **metadata: Any) -> dict[str, Any]:
        result = self.forget(scope, memory_id, metadata=metadata)
        return {
            "ok": True,
            "dataset_name": self.dataset_for_scope(scope),
            "memory_id": memory_id,
            "result": result,
        }

    def delete_scope(self, scope: str, *, dry_run: bool = True) -> dict[str, Any]:
        dataset_name = self.dataset_for_scope(scope)
        if dry_run:
            return {"ok": True, "dry_run": True, "dataset_name": dataset_name, "deleted": False}
        result = self._call("forget", dataset_name=dataset_name)
        return {"ok": True, "dry_run": False, "dataset_name": dataset_name, "deleted": True, "result": result}

    def remember(self, scope: str, content: str, **kwargs: Any) -> Any:
        return self._call("remember", content, dataset_name=self.dataset_for_scope(scope), **kwargs)

    def recall(self, scope: str, query: str, **kwargs: Any) -> Any:
        return self._call("recall", query, dataset_name=self.dataset_for_scope(scope), **kwargs)

    def improve(self, scope: str, **kwargs: Any) -> Any:
        return self._call("improve", dataset_name=self.dataset_for_scope(scope), **kwargs)

    def forget(self, scope: str, memory_id: str, **kwargs: Any) -> Any:
        return self._call("forget", memory_id, dataset_name=self.dataset_for_scope(scope), **kwargs)

    def add(self, scope: str, data: Any, **kwargs: Any) -> Any:
        return self._call("add", data, dataset_name=self.dataset_for_scope(scope), **kwargs)

    def cognify(self, scope: str, **kwargs: Any) -> Any:
        try:
            return self._call("cognify", dataset_name=self.dataset_for_scope(scope), **kwargs)
        except TypeError as exc:
            if _type_error_is_unexpected_keyword(exc, "dataset_name"):
                return self.cognify_scope(scope, **kwargs)
            raise

    def search(self, scope: str, query: str, **kwargs: Any) -> Any:
        raw_results = self._search(query, **kwargs)
        if hasattr(raw_results, "__await__"):
            return self._normalize_async_search_results(raw_results)
        return self._normalize_search_results(raw_results)

    def _call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        self.ensure_client()
        assert self.client is not None  # for type checker
        method = getattr(self.client, method_name)
        try:
            return _resolve_awaitable(method(*args, **kwargs))
        except TypeError as exc:
            if "metadata" in kwargs and _type_error_is_unexpected_keyword(exc, "metadata"):
                retry_kwargs = dict(kwargs)
                retry_kwargs.pop("metadata", None)
                return _resolve_awaitable(method(*args, **retry_kwargs))
            raise

    def _search(self, query: str, **kwargs: Any) -> Any:
        self.ensure_client()

        try:
            from cognee.api.v1.search.search_v2 import SearchType
        except Exception:
            return self._call("search", query, **kwargs)

        query_type = kwargs.pop("query_type", SearchType.CHUNKS)
        try:
            return self.client.search(query_type, query, **kwargs)
        except TypeError:
            return self._call("search", query, **kwargs)

    def _normalize_search_results(self, raw_results: Any) -> list[dict[str, Any]]:
        if raw_results is None:
            return []
        if not isinstance(raw_results, list):
            raw_results = [raw_results]

        normalized: list[dict[str, Any]] = []
        for rank, item in enumerate(raw_results, start=1):
            if not isinstance(item, dict):
                item = {"current_value": str(item)}
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            status = metadata.get("status") or item.get("status") or "active"
            result = MemoryResult(
                memory_id=str(metadata.get("memory_id") or item.get("memory_id") or f"cognee_rank_{rank}"),
                type=str(metadata.get("type") or item.get("type") or "document"),
                subject=str(metadata.get("subject") or item.get("subject") or "Cognee result"),
                current_value=str(item.get("current_value") or item.get("text") or item.get("content") or ""),
                status=str(status),
                layer=str(metadata.get("layer") or item.get("layer") or "L2"),
                version=metadata.get("version") or item.get("version"),
                score=float(item.get("score") or metadata.get("score") or 0),
                rank=rank,
                evidence=[
                    Evidence(
                        source_type=str(metadata.get("source_type") or item.get("source_type") or "cognee"),
                        source_id=metadata.get("source_id") or item.get("source_id"),
                        quote=metadata.get("quote") or item.get("quote") or item.get("text") or item.get("content"),
                    )
                ],
            )
            normalized.append(result.to_dict())
        return normalized

    async def _normalize_async_search_results(self, raw_results: Any) -> list[dict[str, Any]]:
        return self._normalize_search_results(await raw_results)


def curated_memory_document(memory: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> str:
    evidence = memory.get("evidence") if isinstance(memory.get("evidence"), dict) else {}
    metadata = metadata or _curated_memory_metadata(memory)
    parts = [
        f"memory_id: {metadata.get('memory_id') or ''}",
        f"version_id: {metadata.get('version_id') or ''}",
        f"version: {metadata.get('version') or ''}",
        f"status: {metadata.get('status') or memory.get('status') or ''}",
        f"type: {memory.get('type') or 'unknown'}",
        f"subject: {memory.get('subject') or 'unknown'}",
        f"current_value: {memory.get('current_value') or ''}",
        f"source_type: {metadata.get('source_type') or ''}",
        f"source_id: {metadata.get('source_id') or ''}",
        f"provenance: {metadata.get('provenance') or 'copilot_ledger'}",
    ]
    summary = memory.get("summary") or memory.get("reason")
    if summary:
        parts.append(f"summary: {summary}")
    quote = evidence.get("quote") if isinstance(evidence, dict) else None
    if quote:
        parts.append(f"evidence_quote: {quote}")
    return "\n".join(str(part) for part in parts)


def _type_error_is_unexpected_keyword(exc: TypeError, keyword: str) -> bool:
    message = str(exc)
    return (
        f"unexpected keyword argument '{keyword}'" in message
        or f"got an unexpected keyword argument '{keyword}'" in message
    )


def _resolve_awaitable(value: Any) -> Any:
    if not hasattr(value, "__await__"):
        return value
    if not _event_loop_is_running():
        return asyncio.run(_await_value(value))

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(_await_value(value))
        except BaseException as exc:  # pragma: no cover - re-raised in caller thread
            error["exc"] = exc

    thread = threading.Thread(target=runner, name="copilot-cognee-adapter-await", daemon=True)
    thread.start()
    thread.join()
    if "exc" in error:
        raise error["exc"]
    return result.get("value")


def _event_loop_is_running() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


async def _await_value(awaitable: Any) -> Any:
    return await awaitable


def _curated_memory_metadata(memory: dict[str, Any]) -> dict[str, Any]:
    evidence = memory.get("evidence") if isinstance(memory.get("evidence"), dict) else {}
    return {
        "memory_id": memory.get("memory_id"),
        "version_id": memory.get("version_id"),
        "version": memory.get("version"),
        "status": memory.get("status"),
        "type": memory.get("type"),
        "subject": memory.get("subject"),
        "source_type": evidence.get("source_type") if isinstance(evidence, dict) else None,
        "source_id": evidence.get("source_id") if isinstance(evidence, dict) else None,
        "quote": evidence.get("quote") if isinstance(evidence, dict) else None,
        "provenance": "copilot_ledger",
    }
