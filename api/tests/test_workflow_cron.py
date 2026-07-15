from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from api.services.workflow_cron import _cron_due, tick_workflow_crons


def test_cron_due_every_minute():
    now = datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc).timestamp()
    last = datetime(2026, 1, 1, 12, 3, 0, tzinfo=timezone.utc).timestamp()
    assert _cron_due("* * * * *", last, now) is True


def test_cron_not_due_future():
    now = datetime(2026, 1, 1, 12, 0, 10, tzinfo=timezone.utc).timestamp()
    last = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
    assert _cron_due("* * * * *", last, now) is False


def test_invalid_cron():
    assert _cron_due("not a cron", 0, 1_700_000_000) is False


@pytest.mark.asyncio
async def test_tick_skips_when_claim_lost():
    row = {
        "id": "wf-1",
        "enabled": True,
        "owner_user_id": "owner-1",
        "triggers": {
            "cron": {"enabled": True, "expression": "* * * * *", "last_run_at": 0},
            "webhook": {"enabled": False, "secret": ""},
        },
        "published_definition": {
            "name": "x",
            "description": "",
            "steps": [
                {
                    "id": "s1",
                    "type": "step",
                    "name": "S",
                    "executor": {"kind": "agent", "ref": "safe-fallback"},
                }
            ],
        },
    }
    with (
        patch(
            "api.services.workflow_cron.workflow_store.list_workflows_for_cron",
            AsyncMock(return_value=[row]),
        ),
        patch("api.services.workflow_cron.try_claim_cron_run", AsyncMock(return_value=False)) as claim,
        patch("api.services.workflow_cron.asyncio.create_task", return_value=None) as create_task,
    ):
        started = await tick_workflow_crons()
    assert started == 0
    claim.assert_awaited_once()
    create_task.assert_not_called()


@pytest.mark.asyncio
async def test_tick_claims_and_starts_task():
    row = {
        "id": "wf-2",
        "enabled": True,
        "owner_user_id": "owner-2",
        "triggers": {
            "cron": {"enabled": True, "expression": "* * * * *", "last_run_at": 0},
            "webhook": {"enabled": False, "secret": ""},
        },
        "published_definition": {
            "name": "x",
            "description": "",
            "steps": [
                {
                    "id": "s1",
                    "type": "step",
                    "name": "S",
                    "executor": {"kind": "agent", "ref": "safe-fallback"},
                }
            ],
        },
    }
    with (
        patch(
            "api.services.workflow_cron.workflow_store.list_workflows_for_cron",
            AsyncMock(return_value=[row]),
        ),
        patch("api.services.workflow_cron.try_claim_cron_run", AsyncMock(return_value=True)),
        patch("api.services.workflow_cron.asyncio.create_task", return_value=None) as create_task,
    ):
        started = await tick_workflow_crons()
    assert started == 1
    create_task.assert_called_once()
