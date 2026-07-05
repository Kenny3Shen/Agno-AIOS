from __future__ import annotations

from dotenv import load_dotenv
from anyio import to_thread

_RUNTIME_ENV_LOADED = False


def _load_runtime_env_once() -> None:
    global _RUNTIME_ENV_LOADED
    if _RUNTIME_ENV_LOADED:
        return
    load_dotenv(override=True)
    _RUNTIME_ENV_LOADED = True


async def load_runtime_env_async() -> None:
    await to_thread.run_sync(_load_runtime_env_once)
