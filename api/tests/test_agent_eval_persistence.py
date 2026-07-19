import asyncio
from unittest.mock import AsyncMock

import pytest

from api.persistence import agent_evals as persistence
from api.utils.async_once import AsyncOnce


@pytest.mark.asyncio
async def test_ensure_agent_eval_tables_serializes_concurrent_schema_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(persistence, "_agent_eval_tables_once", AsyncOnce())
    schema_check = AsyncMock()
    monkeypatch.setattr(
        persistence,
        "ensure_control_plane_schema_current",
        schema_check,
    )

    await asyncio.gather(
        persistence.ensure_agent_eval_tables_async(),
        persistence.ensure_agent_eval_tables_async(),
    )

    schema_check.assert_awaited_once_with()
