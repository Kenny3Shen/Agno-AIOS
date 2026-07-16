import pytest

from api.utils.async_once import AsyncOnce


@pytest.mark.asyncio
async def test_async_once_runs_factory_only_once() -> None:
    calls = 0
    once = AsyncOnce()

    async def factory() -> None:
        nonlocal calls
        calls += 1

    await once.run(factory)
    await once.run(factory)
    assert calls == 1
    assert once.done is True


@pytest.mark.asyncio
async def test_async_once_reset_allows_rerun() -> None:
    calls = 0
    once = AsyncOnce()

    async def factory() -> None:
        nonlocal calls
        calls += 1

    await once.run(factory)
    once.reset()
    await once.run(factory)
    assert calls == 2
