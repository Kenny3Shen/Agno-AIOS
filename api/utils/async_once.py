"""Process-local async one-shot helpers for schema ensure / bootstrap."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class AsyncOnce:
    """Run an async factory at most once per process (double-checked lock)."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._done = False

    async def run(self, factory: Callable[[], Awaitable[T | None]]) -> T | None:
        if self._done:
            return None
        async with self._lock:
            if self._done:
                return None
            result = await factory()
            self._done = True
            return result
