"""Process-local TTL caches for short-lived hot-path reads."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable
import time
from typing import Generic, TypeVar, cast

T = TypeVar("T")
K = TypeVar("K", bound=Hashable)
_MISSING = object()


class TtlCache(Generic[T]):
    """Hold one value for ``ttl_sec`` seconds; miss returns ``None``."""

    def __init__(self, ttl_sec: float = 5.0) -> None:
        self._ttl_sec = max(0.0, float(ttl_sec))
        self._value: T | None = None
        self._at: float = 0.0
        self._present = False

    def get(self) -> T | None:
        if not self._present:
            return None
        if self._ttl_sec > 0 and (time.time() - self._at) >= self._ttl_sec:
            return None
        return self._value

    def set(self, value: T) -> T:
        self._value = value
        self._at = time.time()
        self._present = True
        return value

    def clear(self) -> None:
        self._value = None
        self._at = 0.0
        self._present = False


class AsyncTtlCache(Generic[K, T]):
    """Bounded keyed TTL cache that coalesces concurrent cache misses.

    Values are only retained after a successful loader result.  Awaiters use
    ``asyncio.shield`` so a cancelled HTTP request cannot cancel the shared
    work still needed by sibling requests.
    """

    def __init__(
        self,
        ttl_sec: float = 5.0,
        *,
        max_entries: int = 128,
        max_inflight: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_sec = max(0.0, float(ttl_sec))
        self._max_entries = max(1, int(max_entries))
        # Retained values and background single-flight work need independent
        # bounds.  In particular, shielded callers may disconnect while an
        # expensive miss is still running.
        self._max_inflight = max(
            1,
            int(max_inflight if max_inflight is not None else max_entries),
        )
        self._clock = clock
        self._values: OrderedDict[K, tuple[float, T]] = OrderedDict()
        self._inflight: dict[K, asyncio.Task[T]] = {}
        self._lock = asyncio.Lock()

    def clear(self) -> None:
        """Discard retained values without interrupting currently shared work."""
        self._values.clear()

    def _cached_value(self, key: K, *, now: float) -> T | object:
        entry = self._values.get(key)
        if entry is None:
            return _MISSING
        created_at, value = entry
        if self._ttl_sec <= 0 or (now - created_at) >= self._ttl_sec:
            self._values.pop(key, None)
            return _MISSING
        self._values.move_to_end(key)
        return value

    async def get_or_create(
        self,
        key: K,
        loader: Callable[[], Awaitable[T]],
    ) -> T:
        """Return a fresh cached value or coalesce one call to ``loader``."""
        bypass_single_flight = False
        async with self._lock:
            cached = self._cached_value(key, now=self._clock())
            if cached is not _MISSING:
                return cast(T, cached)
            task = self._inflight.get(key)
            if task is None:
                if len(self._inflight) >= self._max_inflight:
                    # Do not queue unlimited detached work for arbitrary keys.
                    # The request can still make progress normally; it merely
                    # bypasses caching/coalescing until capacity is available.
                    bypass_single_flight = True
                else:
                    task = asyncio.create_task(self._load(key, loader))
                    # If every shielded waiter disconnects, observing the
                    # outcome here prevents an unhandled-task warning while
                    # preserving the exception for any active waiters.
                    task.add_done_callback(self._observe_task_outcome)
                    self._inflight[key] = task
        if bypass_single_flight:
            return await loader()
        assert task is not None
        return await asyncio.shield(task)

    @staticmethod
    def _observe_task_outcome(task: asyncio.Task[T]) -> None:
        """Mark a detached task exception as observed without swallowing it."""
        if task.cancelled():
            return
        try:
            task.exception()
        except asyncio.CancelledError:
            # ``Task.cancelled`` can race with callback scheduling.
            return

    async def _load(self, key: K, loader: Callable[[], Awaitable[T]]) -> T:
        try:
            value = await loader()
            if self._ttl_sec > 0:
                async with self._lock:
                    self._values[key] = (self._clock(), value)
                    self._values.move_to_end(key)
                    while len(self._values) > self._max_entries:
                        self._values.popitem(last=False)
            return value
        finally:
            async with self._lock:
                self._inflight.pop(key, None)
