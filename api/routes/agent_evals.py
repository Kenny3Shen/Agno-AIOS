from __future__ import annotations

from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from api.auth.models import User
from api.auth.permissions import require_permission
from api.services import agent_eval_case_store as case_store
from api.services import agent_eval_result_service as result_service
from api.services import agent_eval_runner

router = APIRouter(prefix="/api/agent-evals", tags=["Agent Evals"])

EvalType = Literal["accuracy", "agent_as_judge", "reliability", "performance"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvalSuiteCreateRequest(_StrictModel):
    name: str = Field(min_length=1)
    description: str = ""
    target_agent_id: str = "security-operations"
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)


class EvalSuiteUpdateRequest(_StrictModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    target_agent_id: str | None = None
    enabled: bool | None = None
    tags: list[str] | None = None


class EvalCaseCreateRequest(_StrictModel):
    suite_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    target_agent_id: str = "security-operations"
    input: str = Field(min_length=1)
    expected_output: str = ""
    criteria: str = ""
    threshold: int = Field(default=7, ge=1, le=10)
    eval_types: list[EvalType] = cast(
        list[EvalType],
        Field(default_factory=lambda: ["accuracy"]),
    )
    expected_tool_calls: list[str] = Field(default_factory=list)
    expected_tool_call_arguments: dict[str, Any] = Field(default_factory=dict)
    allow_additional_tool_calls: bool = False
    performance_config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class EvalCaseUpdateRequest(_StrictModel):
    suite_id: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    target_agent_id: str | None = None
    input: str | None = Field(default=None, min_length=1)
    expected_output: str | None = None
    criteria: str | None = None
    threshold: int | None = Field(default=None, ge=1, le=10)
    eval_types: list[EvalType] | None = None
    expected_tool_calls: list[str] | None = None
    expected_tool_call_arguments: dict[str, Any] | None = None
    allow_additional_tool_calls: bool | None = None
    performance_config: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    enabled: bool | None = None


def _http_from_value_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    lowered = message.lower()
    if "not found" in lowered:
        return HTTPException(status_code=404, detail=message)
    if "disabled" in lowered:
        return HTTPException(status_code=409, detail=message)
    return HTTPException(status_code=422, detail=message)


def _not_found(resource: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{resource} not found")


def _eval_run_id(run: dict[str, Any]) -> str:
    for key in ("run_id", "id"):
        value = run.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _with_case_run_replay_link(
    run: dict[str, Any],
    case_runs_by_eval_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    eval_run_id = _eval_run_id(run)
    if not eval_run_id:
        return run
    case_run = case_runs_by_eval_id.get(eval_run_id)
    if case_run is None:
        return run

    enriched = dict(run)
    data = run.get("data")
    enriched_data = dict(data) if isinstance(data, dict) else {}
    enriched["case_run_id"] = case_run["id"]
    enriched["case_id"] = case_run["case_id"]
    enriched["suite_run_id"] = case_run["suite_run_id"]
    enriched_data["case_run_id"] = case_run["id"]
    enriched_data["case_id"] = case_run["case_id"]
    enriched_data["suite_run_id"] = case_run["suite_run_id"]
    enriched["data"] = enriched_data
    return enriched


@router.get("/suites")
async def list_eval_suites(
    enabled: bool | None = None,
    user: User = Depends(require_permission("evals:read")),
):
    del user
    return await case_store.list_suites(enabled=enabled)


@router.post("/suites")
async def create_eval_suite(
    body: EvalSuiteCreateRequest,
    user: User = Depends(require_permission("evals:write")),
):
    try:
        return await case_store.create_suite(body.model_dump(), user)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error(f"创建 Agent Eval 套件失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to create eval suite") from exc


@router.get("/suites/{suite_id}")
async def get_eval_suite(
    suite_id: str,
    user: User = Depends(require_permission("evals:read")),
):
    del user
    suite = await case_store.get_suite(suite_id)
    if suite is None:
        raise _not_found("Eval suite")
    return suite


@router.patch("/suites/{suite_id}")
async def update_eval_suite(
    suite_id: str,
    body: EvalSuiteUpdateRequest,
    user: User = Depends(require_permission("evals:write")),
):
    del user
    try:
        suite = await case_store.update_suite(suite_id, body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error(f"更新 Agent Eval 套件失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to update eval suite") from exc
    if suite is None:
        raise _not_found("Eval suite")
    return suite


@router.get("/cases")
async def list_eval_cases(
    suite_id: str | None = None,
    enabled: bool | None = None,
    user: User = Depends(require_permission("evals:read")),
):
    del user
    return await case_store.list_cases(suite_id=suite_id, enabled=enabled)


@router.post("/cases")
async def create_eval_case(
    body: EvalCaseCreateRequest,
    user: User = Depends(require_permission("evals:write")),
):
    del user
    try:
        return await case_store.create_case(body.model_dump())
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error(f"创建 Agent Eval 用例失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to create eval case") from exc


@router.get("/cases/{case_id}")
async def get_eval_case(
    case_id: str,
    user: User = Depends(require_permission("evals:read")),
):
    del user
    case = await case_store.get_case(case_id)
    if case is None:
        raise _not_found("Eval case")
    return case


@router.patch("/cases/{case_id}")
async def update_eval_case(
    case_id: str,
    body: EvalCaseUpdateRequest,
    user: User = Depends(require_permission("evals:write")),
):
    del user
    try:
        case = await case_store.update_case(case_id, body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error(f"更新 Agent Eval 用例失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to update eval case") from exc
    if case is None:
        raise _not_found("Eval case")
    return case


@router.get("/suites/{suite_id}/runs")
async def list_eval_suite_runs(
    suite_id: str,
    status: str | None = None,
    user: User = Depends(require_permission("evals:read")),
):
    del user
    return await case_store.list_suite_runs(suite_id=suite_id, status=status)


@router.post("/suites/{suite_id}/runs")
async def run_eval_suite(
    suite_id: str,
    user: User = Depends(require_permission("evals:write")),
):
    try:
        return await agent_eval_runner.run_suite(suite_id, actor=user)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error(f"运行 Agent Eval 套件失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to run eval suite") from exc


@router.get("/cases/{case_id}/runs")
async def list_eval_case_runs(
    case_id: str,
    status: str | None = None,
    user: User = Depends(require_permission("evals:read")),
):
    del user
    return await case_store.list_case_runs(case_id=case_id, status=status)


@router.post("/cases/{case_id}/runs")
async def run_eval_case(
    case_id: str,
    user: User = Depends(require_permission("evals:write")),
):
    try:
        return await agent_eval_runner.run_case(case_id, actor=user)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error(f"运行 Agent Eval 用例失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to run eval case") from exc


@router.post("/case-runs/{case_run_id}/replay")
async def replay_eval_case_run(
    case_run_id: str,
    user: User = Depends(require_permission("evals:write")),
):
    try:
        return await agent_eval_runner.replay_case_run(case_run_id, actor=user)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error(f"重放 Agent Eval 用例运行失败: {exc}")
        raise HTTPException(status_code=500, detail="Failed to replay eval case run") from exc


@router.get("/agno-runs")
async def list_agno_eval_runs(
    limit: int = Query(default=50, ge=1, le=100),
    page: int = Query(default=1, ge=1),
    eval_type: list[EvalType] | None = Query(default=None),
    agent_id: str | None = None,
    user: User = Depends(require_permission("evals:read")),
):
    del user
    return await result_service.list_agno_eval_runs(
        limit=limit,
        page=page,
        eval_type=list(eval_type) if eval_type is not None else None,
        agent_id=agent_id,
    )


@router.get("/agno-runs/{eval_run_id}")
async def get_agno_eval_run(
    eval_run_id: str,
    user: User = Depends(require_permission("evals:read")),
):
    del user
    result = await result_service.get_agno_eval_run(eval_run_id)
    if result is None:
        raise _not_found("Agno eval run")
    return result


@router.get("/trends")
async def get_eval_trends(
    limit: int = Query(default=50, ge=1, le=100),
    page: int = Query(default=1, ge=1),
    eval_type: list[EvalType] | None = Query(default=None),
    agent_id: str | None = None,
    user: User = Depends(require_permission("evals:read")),
):
    del user
    result = await result_service.list_agno_eval_runs(
        limit=limit,
        page=page,
        eval_type=list(eval_type) if eval_type is not None else None,
        agent_id=agent_id,
    )
    return result["trends"]


@router.get("/failures")
async def list_eval_failures(
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(require_permission("evals:read")),
):
    del user
    failures = await result_service.list_failed_eval_runs(limit=limit)
    eval_run_ids = [eval_run_id for item in failures if (eval_run_id := _eval_run_id(item))]
    case_runs_by_eval_id = await case_store.list_case_runs_by_agno_eval_run_ids(eval_run_ids)
    return [_with_case_run_replay_link(item, case_runs_by_eval_id) for item in failures]
