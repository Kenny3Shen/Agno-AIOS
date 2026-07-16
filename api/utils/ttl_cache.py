"""Process-local TTL cache for short-lived hot-path reads."""

from __future__ import annotations

import time
from typing import Generic, TypeVar

T = TypeVar("T")


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
