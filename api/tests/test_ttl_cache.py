"""Focused regressions for keyed async TTL caching."""

import asyncio
import gc

import pytest

from api.utils.ttl_cache import AsyncTtlCache


@pytest.mark.asyncio
async def test_async_ttl_cache_coalesces_concurrent_misses_and_returns_cached_value():
    cache: AsyncTtlCache[str, dict[str, int]] = AsyncTtlCache(ttl_sec=5.0)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def load() -> dict[str, int]:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"calls": calls}

    first = asyncio.create_task(cache.get_or_create("overview", load))
    await started.wait()
    second = asyncio.create_task(cache.get_or_create("overview", load))
    await asyncio.sleep(0)
    assert calls == 1

    release.set()
    assert await first == {"calls": 1}
    assert await second == {"calls": 1}
    assert await cache.get_or_create("overview", load) == {"calls": 1}
    assert calls == 1


@pytest.mark.asyncio
async def test_async_ttl_cache_expires_and_does_not_retain_failures():
    current = 0.0
    cache: AsyncTtlCache[str, int] = AsyncTtlCache(
        ttl_sec=3.0,
        clock=lambda: current,
    )
    calls = 0

    async def fail_once() -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient database failure")
        return calls

    with pytest.raises(RuntimeError, match="transient"):
        await cache.get_or_create("overview", fail_once)
    assert await cache.get_or_create("overview", fail_once) == 2

    current = 2.9
    assert await cache.get_or_create("overview", fail_once) == 2
    current = 3.0
    assert await cache.get_or_create("overview", fail_once) == 3


@pytest.mark.asyncio
async def test_async_ttl_cache_observes_detached_loader_failure_after_waiters_cancel():
    cache: AsyncTtlCache[str, int] = AsyncTtlCache(ttl_sec=5.0)
    started = asyncio.Event()
    release = asyncio.Event()
    reported: list[dict[str, object]] = []
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()

    async def fail_after_disconnect() -> int:
        started.set()
        await release.wait()
        raise RuntimeError("detached loader failure")

    loop.set_exception_handler(lambda _loop, context: reported.append(context))
    try:
        waiter = asyncio.create_task(cache.get_or_create("overview", fail_after_disconnect))
        await started.wait()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        release.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        gc.collect()
        assert not reported
    finally:
        loop.set_exception_handler(previous_handler)


@pytest.mark.asyncio
async def test_async_ttl_cache_bounds_detached_inflight_work_by_bypassing_overflow():
    cache: AsyncTtlCache[str, int] = AsyncTtlCache(ttl_sec=5.0, max_inflight=1)
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_load() -> int:
        started.set()
        await release.wait()
        return 1

    first = asyncio.create_task(cache.get_or_create("first", slow_load))
    await started.wait()

    calls = 0

    async def overflow_load() -> int:
        nonlocal calls
        calls += 1
        return 2

    assert await cache.get_or_create("second", overflow_load) == 2
    # Overflow work is request-owned rather than another retained/inflight
    # task; a later request can cache it once capacity is back.
    assert calls == 1
    release.set()
    assert await first == 1
    assert await cache.get_or_create("second", overflow_load) == 2
    assert calls == 2


@pytest.mark.asyncio
async def test_async_ttl_cache_evicts_least_recently_used_retained_key():
    cache: AsyncTtlCache[str, str] = AsyncTtlCache(ttl_sec=5.0, max_entries=2)
    calls: dict[str, int] = {}

    def loader(key: str):
        async def load() -> str:
            calls[key] = calls.get(key, 0) + 1
            return f"{key}-{calls[key]}"

        return load

    assert await cache.get_or_create("first", loader("first")) == "first-1"
    assert await cache.get_or_create("second", loader("second")) == "second-1"
    # Touch first, so second is the LRU entry when a third key arrives.
    assert await cache.get_or_create("first", loader("first")) == "first-1"
    assert await cache.get_or_create("third", loader("third")) == "third-1"
    assert await cache.get_or_create("second", loader("second")) == "second-2"
    assert calls == {"first": 1, "second": 2, "third": 1}


@pytest.mark.asyncio
async def test_async_ttl_cache_retains_successful_none_values():
    cache: AsyncTtlCache[str, None] = AsyncTtlCache(ttl_sec=5.0)
    calls = 0

    async def load() -> None:
        nonlocal calls
        calls += 1

    assert await cache.get_or_create("empty", load) is None
    assert await cache.get_or_create("empty", load) is None
    assert calls == 1
