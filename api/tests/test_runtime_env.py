from unittest.mock import patch

import pytest

from api.services import runtime_env


@pytest.mark.asyncio
async def test_runtime_env_loader_runs_dotenv_once() -> None:
    runtime_env._RUNTIME_ENV_LOADED = False
    calls: list[dict] = []

    with patch.object(runtime_env, "load_dotenv", side_effect=lambda **kwargs: calls.append(kwargs)):
        await runtime_env.load_runtime_env_async()
        await runtime_env.load_runtime_env_async()

    assert calls == [{"override": True}]
