from __future__ import annotations

from dotenv import load_dotenv
from anyio import to_thread

from api.utils.async_once import AsyncOnce

_runtime_env_once = AsyncOnce()


async def _load_runtime_env() -> None:
    await to_thread.run_sync(lambda: load_dotenv(override=True))


async def load_runtime_env_async() -> None:
    await _runtime_env_once.run(_load_runtime_env)
