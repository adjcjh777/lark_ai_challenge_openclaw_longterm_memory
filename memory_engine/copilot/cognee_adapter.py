from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from memory_engine.models import parse_scope


class CogneeAdapterNotConfigured(RuntimeError):
    """Raised when the boundary is called before a Cognee client is injected."""


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

    def dataset_for_scope(self, scope: str) -> str:
        parsed = parse_scope(scope)
        scope_key = f"{parsed.scope_type}_{parsed.scope_id}"
        safe_scope = re.sub(r"[^a-zA-Z0-9_]+", "_", scope_key).strip("_").lower()
        return f"{self.dataset_prefix}_{safe_scope}"

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
        return self._call("search", query, dataset_name=self.dataset_for_scope(scope), **kwargs)

    def _call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        if self.client is None:
            raise CogneeAdapterNotConfigured(
                "Cognee client is not configured; inject a local SDK client in the 2026-04-27 spike"
            )
        method = getattr(self.client, method_name)
        return method(*args, **kwargs)
