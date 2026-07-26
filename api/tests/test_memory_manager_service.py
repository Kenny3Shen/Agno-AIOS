from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.services import memory_manager_service


@pytest.mark.asyncio
async def test_memory_manager_auto_pick_skips_incomplete_model_drafts() -> None:
    """A draft connection cannot shadow a runnable model during auto-pick."""
    store = SimpleNamespace(
        models=[
            SimpleNamespace(
                id="draft-flash",
                model_id="flash-draft",
                enabled=True,
                configured=False,
            ),
            SimpleNamespace(
                id="ready",
                model_id="production-model",
                enabled=True,
                configured=True,
            ),
        ]
    )
    get_model_for_run = AsyncMock(return_value={"id": "ready"})

    with (
        patch.object(
            memory_manager_service,
            "get_memory_model_id",
            AsyncMock(return_value=None),
        ),
        patch.object(
            memory_manager_service,
            "load_model_config_store",
            AsyncMock(return_value=store),
        ),
        patch.object(
            memory_manager_service,
            "get_model_for_run",
            get_model_for_run,
        ),
    ):
        result = await memory_manager_service.resolve_memory_manager_model_config()

    assert result == {"id": "ready"}
    get_model_for_run.assert_awaited_once_with("ready")
