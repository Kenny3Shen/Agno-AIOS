from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable

from agno.knowledge.embedder import Embedder


class FakeEmbedder(Embedder):
    def __init__(self) -> None:
        super().__init__(dimensions=3)

    def get_embedding(self, text: str) -> list[float]:
        return [0.0, 0.0, float(len(text))]

    def get_embedding_and_usage(self, text: str) -> tuple[list[float], None]:
        return (self.get_embedding(text), None)

    async def async_get_embedding(self, text: str) -> list[float]:
        return self.get_embedding(text)

    async def async_get_embedding_and_usage(
        self, text: str
    ) -> tuple[list[float], None]:
        return self.get_embedding_and_usage(text)


class StrictAsyncKnowledge:
    def __init__(
        self,
        *,
        contents: list[Any] | None = None,
        content_by_id: dict[str, Any] | None = None,
        search_results: list[Any] | None = None,
        search_callback: Callable[..., Any] | None = None,
    ) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self._contents = contents or []
        self._content_by_id = content_by_id or {}
        self._search_results = search_results or []
        self._search_callback = search_callback

    def insert(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("sync insert must not be called")

    def search(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("sync search must not be called")

    def load(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("sync load must not be called")

    def get_content(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("sync get_content must not be called")

    def get_content_by_id(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("sync get_content_by_id must not be called")

    def remove_content_by_id(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("sync remove_content_by_id must not be called")

    def remove_all_content(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("sync remove_all_content must not be called")

    async def ainsert(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("ainsert", args, kwargs))

    async def aget_content(self, *args: Any, **kwargs: Any):
        self.calls.append(("aget_content", args, kwargs))
        return self._contents, len(self._contents)

    async def aget_content_by_id(self, content_id: str):
        self.calls.append(("aget_content_by_id", content_id))
        return self._content_by_id.get(content_id)

    async def asearch(self, *args: Any, **kwargs: Any):
        self.calls.append(("asearch", args, kwargs))
        if self._search_callback is not None:
            result = self._search_callback(*args, **kwargs)
            if hasattr(result, "__await__"):
                return await result
            return result
        return self._search_results

    async def apatch_content(self, content: Any):
        self.calls.append(("apatch_content", content))
        existing = self._content_by_id.get(content.id)
        if existing is None:
            return None
        if getattr(content, "name", None) is not None:
            existing.name = content.name
        if getattr(content, "description", None) is not None:
            existing.description = content.description
        existing.metadata = {**getattr(existing, "metadata", {}), **(content.metadata or {})}
        return {"id": content.id, "metadata": existing.metadata}

    def _build_content_hash(self, content: Any) -> str:
        self.calls.append(("_build_content_hash", content))
        return f"hash:{getattr(content, 'id', '')}:{getattr(content, 'name', '')}"

    async def _aload_content(
        self,
        content: Any,
        upsert: bool,
        skip_if_exists: bool,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
    ) -> None:
        self.calls.append(("_aload_content", content, upsert, skip_if_exists, include, exclude))
        self._content_by_id[content.id] = SimpleNamespace(
            id=content.id,
            name=content.name,
            description=content.description,
            path=content.path,
            file_data=content.file_data,
            metadata=content.metadata,
            created_at=0,
        )
