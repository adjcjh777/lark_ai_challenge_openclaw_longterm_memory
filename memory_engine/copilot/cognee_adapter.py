from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from typing import Any, Protocol

from memory_engine.models import parse_scope

from .schemas import Evidence, MemoryResult


class CogneeAdapterNotConfigured(RuntimeError):
    """Raised when the boundary is called before a Cognee client is injected."""


def load_cognee_client() -> CogneeClient:
    return importlib.import_module("cognee")


class CogneeClient(Protocol):
    def remember(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def recall(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def improve(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def forget(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def add(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def cognify(self, *args: Any, **kwargs: Any) -> Any:
        ...

    def search(self, *args: Any, **kwargs: Any) -> Any:
        ...


@dataclass
class CogneeMemoryAdapter:
    """Narrow Cognee boundary for the Copilot core.

    The project contract is that only this adapter should talk to Cognee
    directly. The first day skeleton keeps the dependency optional so tests and
    legacy benchmark commands still run without installing Cognee.
    """

    client: CogneeClient | None = None
    dataset_prefix: str = "feishu_memory_copilot"

    @property
    def is_configured(self) -> bool:
        return self.client is not None

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
        return self._call("cognify", dataset_name=self.dataset_for_scope(scope), **kwargs)

    def search(self, scope: str, query: str, **kwargs: Any) -> Any:
        raw_results = self._search(query, **kwargs)
        if hasattr(raw_results, "__await__"):
            return self._normalize_async_search_results(raw_results)
        return self._normalize_search_results(raw_results)

    def _call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        if self.client is None:
            raise CogneeAdapterNotConfigured(
                "Cognee client is not configured; inject a local SDK client in the 2026-04-27 spike"
            )
        method = getattr(self.client, method_name)
        return method(*args, **kwargs)

    def _search(self, query: str, **kwargs: Any) -> Any:
        if self.client is None:
            raise CogneeAdapterNotConfigured(
                "Cognee client is not configured; inject a local SDK client in the 2026-04-27 spike"
            )

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
