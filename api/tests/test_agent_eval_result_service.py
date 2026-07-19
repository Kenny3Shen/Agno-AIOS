from unittest.mock import patch

import pytest

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
                    "eval_data": {"overall_score": 1.0, "passed": True},
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
            "eval_data": {
                "passed": False,
                "missing_tool_calls": ["basic_send_feishu_notify"],
            },
        }


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
    assert result["meta"]["total_count"] == 37
    assert result["meta"]["page"] == 2
    assert result["meta"]["limit"] == 10
    assert result["data"][0]["id"] == "eval-1"
    assert result["data"][0]["eval_data"] == {"overall_score": 1.0, "passed": True}
    assert result["data"][0]["score"] == 1.0
    assert result["data"][0]["passed"] is True
    assert "items" not in result
    assert "trends" not in result


@pytest.mark.asyncio
async def test_get_agno_eval_run_returns_none_for_missing():
    db = FakeEvalDb()
    with patch(
        "api.services.agent_eval_result_service.get_async_agno_postgres_db",
        return_value=db,
    ):
        assert await service.get_agno_eval_run("missing") is None
    assert db.get_kwargs["deserialize"] is False


@pytest.mark.asyncio
async def test_list_failed_eval_runs_returns_only_failed_items():
    class FailedEvalDb:
        async def get_eval_runs(self, **kwargs):
            return (
                [
                    {
                        "run_id": "eval-2",
                        "eval_type": "quality",
                        "eval_data": {"score": 0.4, "passed": False},
                        "created_at": "2024-05-02T00:00:00+00:00",
                    }
                ],
                1,
            )

    db = FailedEvalDb()
    with patch(
        "api.services.agent_eval_result_service.get_async_agno_postgres_db",
        return_value=db,
    ):
        result = await service.list_failed_eval_runs(limit=5)

    assert [item["id"] for item in result] == ["eval-2"]

@pytest.mark.asyncio
async def test_list_failed_eval_runs_scans_pages_until_limit():
    """Failures may sit past page 1 when most recent runs passed."""
    calls: list[int] = []
    # 50 passing rows then two failures so page_size=50 needs a second page.
    catalog = [
        {
            "run_id": f"pass-{index}",
            "eval_type": "accuracy",
            "eval_data": {"passed": True},
            "created_at": 1000 - index,
        }
        for index in range(50)
    ] + [
        {
            "run_id": "fail-1",
            "eval_type": "accuracy",
            "eval_data": {"passed": False},
            "created_at": 1,
        },
        {
            "run_id": "fail-2",
            "eval_type": "quality",
            "eval_data": {"passed": False},
            "created_at": 0,
        },
    ]

    class PagedEvalDb:
        async def get_eval_runs(self, **kwargs):
            page = int(kwargs.get("page") or 1)
            limit = int(kwargs.get("limit") or 50)
            calls.append(page)
            start = (page - 1) * limit
            return catalog[start : start + limit], len(catalog)

    with patch(
        "api.services.agent_eval_result_service.get_async_agno_postgres_db",
        return_value=PagedEvalDb(),
    ):
        result = await service.list_failed_eval_runs(limit=2)

    assert [item["id"] for item in result] == ["fail-1", "fail-2"]
    assert calls == [1, 2]
