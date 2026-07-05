from dataclasses import dataclass
from unittest.mock import patch

import pytest
from agno.db.schemas.evals import EvalRunRecord, EvalType

from api.services import agent_eval_result_service as service


class FakeEvalDb:
    def __init__(self):
        self.list_kwargs = {}
        self.get_kwargs = {}

    async def get_eval_runs(self, **kwargs):
        self.list_kwargs = kwargs
        return (
            [
                {
                    "run_id": "eval-1",
                    "eval_type": "accuracy",
                    "agent_id": "security-operations",
                    "name": "CVE baseline",
                    "data": {"overall_score": 1.0, "passed": True},
                    "created_at": 1714560000,
                }
            ],
            37,
        )

    async def get_eval_run(self, eval_run_id: str, **kwargs):
        self.get_kwargs = kwargs
        if eval_run_id == "missing":
            return None
        return {
            "run_id": eval_run_id,
            "eval_type": "reliability",
            "data": {"passed": False, "missing_tool_calls": ["playbook.cve_lookup"]},
        }


class ListOnlyEvalDb:
    async def get_eval_runs(self, **kwargs):
        return [
            {
                "id": "eval-2",
                "eval_type": "quality",
                "data": {"score": 0.4, "passed": False},
                "created_at": "2024-05-02T00:00:00+00:00",
            }
        ]


@dataclass
class EvalObject:
    run_id: str
    eval_type: str
    data: dict
    created_at: int


@pytest.mark.asyncio
async def test_list_agno_eval_runs_uses_async_db_api():
    db = FakeEvalDb()
    with patch(
        "api.services.agent_eval_result_service.get_async_agno_postgres_db",
        return_value=db,
    ):
        result = await service.list_agno_eval_runs(
            limit=10,
            page=2,
            eval_type=["accuracy"],
        )

    assert db.list_kwargs["limit"] == 10
    assert db.list_kwargs["page"] == 2
    assert db.list_kwargs["deserialize"] is False
    assert result["total"] == 37
    assert result["items"][0]["id"] == "eval-1"


@pytest.mark.asyncio
async def test_list_agno_eval_runs_handles_list_result_without_total():
    db = ListOnlyEvalDb()
    with patch(
        "api.services.agent_eval_result_service.get_async_agno_postgres_db",
        return_value=db,
    ):
        result = await service.list_agno_eval_runs(limit=5, page=1)

    assert result["total"] == 1
    assert result["items"][0]["id"] == "eval-2"
    assert result["items"][0]["passed"] is False


@pytest.mark.asyncio
async def test_get_agno_eval_run_returns_none_for_missing():
    db = FakeEvalDb()
    with patch(
        "api.services.agent_eval_result_service.get_async_agno_postgres_db",
        return_value=db,
    ):
        assert await service.get_agno_eval_run("missing") is None
    assert db.get_kwargs["deserialize"] is False


def test_normalize_agno_eval_run_handles_dataclass_objects():
    result = service.normalize_agno_eval_run(
        EvalObject(
            run_id="eval-3",
            eval_type="accuracy",
            data={"overall_score": 0.75},
            created_at=1714646400,
        )
    )

    assert result["id"] == "eval-3"
    assert result["score"] == 0.75
    assert result["passed"] is None


def test_normalize_agno_eval_run_handles_eval_data_and_enum_type():
    result = service.normalize_agno_eval_run(
        EvalRunRecord(
            run_id="eval-4",
            eval_type=EvalType.ACCURACY,
            eval_data={"score": 0.8, "passed": True},
            eval_input={"input": "baseline"},
        )
    )

    assert result["id"] == "eval-4"
    assert result["data"] == {"score": 0.8, "passed": True}
    assert result["passed"] is True
    assert result["score"] == 0.8
    assert result["eval_type"] == "accuracy"


def test_build_eval_trends_groups_by_day_type_and_status():
    trends = service.build_eval_trends(
        [
            {
                "id": "eval-1",
                "eval_type": "accuracy",
                "passed": True,
                "created_at": 1714560000,
            },
            {
                "id": "eval-2",
                "eval_type": "accuracy",
                "passed": False,
                "created_at": 1714560000,
            },
            {
                "id": "eval-3",
                "eval_type": "reliability",
                "passed": None,
                "created_at": "2024-05-02T00:00:00+00:00",
            },
        ]
    )

    assert trends["by_date"] == [
        {"date": "2024-05-01", "total": 2, "passed": 1, "failed": 1},
        {"date": "2024-05-02", "total": 1, "passed": 0, "failed": 0},
    ]
    assert trends["by_eval_type"] == [
        {"eval_type": "accuracy", "total": 2, "passed": 1, "failed": 1},
        {"eval_type": "reliability", "total": 1, "passed": 0, "failed": 0},
    ]
    assert trends["by_status"] == {"failed": 1, "passed": 1, "unknown": 1}


@pytest.mark.asyncio
async def test_list_failed_eval_runs_returns_only_failed_items():
    db = ListOnlyEvalDb()
    with patch(
        "api.services.agent_eval_result_service.get_async_agno_postgres_db",
        return_value=db,
    ):
        result = await service.list_failed_eval_runs(limit=5)

    assert [item["id"] for item in result] == ["eval-2"]
