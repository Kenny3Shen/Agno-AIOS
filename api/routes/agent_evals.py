from __future__ import annotations

from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from api.auth.models import User
from api.auth.scopes import require_scope
from api.persistence.agent_evals import ActiveEvalSuiteRunError
from api.services import agent_eval_case_store as case_store
from api.services import agent_eval_result_service as result_service
from api.services import agent_eval_runner
from api.services import agent_eval_report_service as report_service
from api.services import safety_eval_pack_service as pack_service
from api.services.agent_eval_suite_queue import enqueue_suite_run
from api.services.audit_service import record_audit_event_async
from api.services.eval_targets import list_eval_targets
from api.utils.pagination import pagination_meta

router = APIRouter(prefix="/api/agent-evals", tags=["Agent Evals"])

EvalType = Literal["accuracy", "agent_as_judge", "reliability", "performance"]
JudgeMode = Literal["binary", "numeric"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvalPerformanceConfig(_StrictModel):
    """Bounded, complete configuration for one Agno ``PerformanceEval``."""

    warmup_runs: StrictInt = Field(
        default=case_store.DEFAULT_PERFORMANCE_WARMUP_RUNS,
        ge=0,
        le=case_store.MAX_PERFORMANCE_WARMUP_RUNS,
    )
    num_iterations: StrictInt = Field(
        default=case_store.DEFAULT_PERFORMANCE_NUM_ITERATIONS,
        ge=1,
        le=case_store.MAX_PERFORMANCE_NUM_ITERATIONS,
    )
    measure_runtime: StrictBool = True
    measure_memory: StrictBool = False

    @model_validator(mode="after")
    def require_enabled_measurement(self) -> "EvalPerformanceConfig":
        if not self.measure_runtime and not self.measure_memory:
            raise ValueError(
                "performance_config must enable measure_runtime or measure_memory"
            )
        return self


class EvalPackImportRequest(_StrictModel):
    pack_id: str = Field(min_length=1)
    pack_version: str = ""


class EvalTargetRequest(_StrictModel):
    kind: Literal["agent", "team"]
    id: str = Field(min_length=1)


class EvalSuiteCreateRequest(_StrictModel):
    name: str = Field(min_length=1)
    description: str = ""
    target: EvalTargetRequest
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)


class EvalSuiteUpdateRequest(_StrictModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    enabled: bool | None = None
    tags: list[str] | None = None


class EvalCaseCreateRequest(_StrictModel):
    suite_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    input: str = Field(min_length=1)
    expected_output: str = ""
    criteria: str = ""
    judge_mode: JudgeMode = "binary"
    additional_guidelines: list[str] = Field(default_factory=list, max_length=20)
    threshold: int = Field(default=7, ge=1, le=10)
    # A Case must state its checks explicitly. Choosing Accuracy implicitly
    # made an otherwise valid direct API request fail later for a missing
    # expected_output, and diverged from Agno Case's explicit check contract.
    eval_types: list[EvalType] = cast(list[EvalType], Field(min_length=1))
    expected_tool_calls: list[str] = Field(default_factory=list)
    expected_tool_call_arguments: dict[str, Any] = Field(default_factory=dict)
    # Agno Case / ReliabilityEval default. Security packs may explicitly set
    # this to false when every tool call is part of the safety contract.
    allow_additional_tool_calls: bool = True
    performance_config: EvalPerformanceConfig = Field(
        default_factory=EvalPerformanceConfig
    )
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True


class EvalCaseUpdateRequest(_StrictModel):
    suite_id: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    input: str | None = Field(default=None, min_length=1)
    expected_output: str | None = None
    criteria: str | None = None
    judge_mode: JudgeMode | None = None
    additional_guidelines: list[str] | None = Field(default=None, max_length=20)
    threshold: int | None = Field(default=None, ge=1, le=10)
    eval_types: list[EvalType] | None = None
    expected_tool_calls: list[str] | None = None
    expected_tool_call_arguments: dict[str, Any] | None = None
    allow_additional_tool_calls: bool | None = None
    # Sending an object replaces the complete benchmark configuration.  An
    # explicit null resets it to the server's lightweight defaults.
    performance_config: EvalPerformanceConfig | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    metadata: dict[str, Any] | None = None
    tags: list[str] | None = None
    enabled: bool | None = None


class EvalSuiteRunRequest(_StrictModel):
    """Agno-compatible selectors and per-Case default timeout."""

    tag: str | None = None
    name: str | None = None
    # Matches Agno ``run_cases(..., default_timeout=120)``. A Case-level
    # ``timeout_seconds`` wins when present.
    default_timeout: int = Field(default=120, ge=1, le=3600)


def _http_from_value_error(exc: ValueError) -> HTTPException:
    if isinstance(exc, ActiveEvalSuiteRunError):
        return HTTPException(status_code=409, detail=str(exc))
    message = str(exc)
    lowered = message.lower()
    if "not found" in lowered:
        return HTTPException(status_code=404, detail=message)
    if "disabled" in lowered or "immutable" in lowered:
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
    raw_eval_data = run.get("eval_data")
    eval_data = raw_eval_data if isinstance(raw_eval_data, dict) else {}
    enriched_eval_data = dict(eval_data)
    enriched["case_run_id"] = case_run["id"]
    enriched["case_id"] = case_run["case_id"]
    enriched["suite_run_id"] = case_run["suite_run_id"]
    enriched_eval_data["case_run_id"] = case_run["id"]
    enriched_eval_data["case_id"] = case_run["case_id"]
    enriched_eval_data["suite_run_id"] = case_run["suite_run_id"]
    enriched["eval_data"] = enriched_eval_data
    return enriched


@router.get("/packs")
async def list_eval_packs(
    ready_only: bool = Query(default=True),
    user: User = Depends(require_scope("evals:read")),
):
    """Safety eval pack catalog (registry metadata only; no case prompts)."""
    del user
    try:
        data = pack_service.list_pack_catalog(ready_only=ready_only)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    return {
        "data": data,
        "meta": pagination_meta(page=1, limit=max(len(data), 1), total_count=len(data)),
    }


@router.post("/packs/import")
async def import_eval_pack(
    body: EvalPackImportRequest,
    user: User = Depends(require_scope("evals:write")),
):
    """Idempotent import of a local ready pack into suite/cases."""
    try:
        result = await pack_service.import_pack(
            body.pack_id.strip(),
            user,
            pack_version=body.pack_version.strip(),
            require_ready=True,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error("导入安全评估 pack 失败: {}", exc)
        raise HTTPException(
            status_code=500, detail="Failed to import eval pack"
        ) from exc

    await record_audit_event_async(
        user,
        action="evals.pack_import",
        resource_type="eval_pack",
        resource_id=str(result.get("pack_id") or body.pack_id),
        metadata={
            "suite_id": result.get("suite_id"),
            "suite_name": result.get("suite_name"),
            "cases_created": result.get("cases_created"),
            "cases_updated": result.get("cases_updated"),
            "pack_version": result.get("pack_version"),
            "pack_cases_sha256": result.get("pack_cases_sha256"),
            "pack_cases_count": result.get("pack_cases_count"),
            "pack_sample_seed": result.get("pack_sample_seed"),
        },
    )
    return result


@router.delete("/packs/{pack_id}")
async def remove_eval_pack(
    pack_id: str,
    pack_version: str = Query(min_length=1),
    user: User = Depends(require_scope("evals:delete")),
):
    """Permanently remove one exact imported pack version and its run history."""
    try:
        result = await pack_service.remove_imported_pack(
            pack_id.strip(),
            pack_version=pack_version.strip(),
        )
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error("移除已导入安全评估 pack 失败: {}", exc)
        raise HTTPException(
            status_code=500, detail="Failed to remove imported eval pack"
        ) from exc

    await record_audit_event_async(
        user,
        action="evals.pack_remove",
        resource_type="eval_pack",
        resource_id=str(result.get("pack_id") or pack_id),
        metadata={
            "pack_version": result.get("pack_version") or pack_version.strip(),
            "suite_ids": result.get("suite_ids"),
            "suites_deleted": result.get("suites_deleted"),
            "cases_deleted": result.get("cases_deleted"),
            "suite_runs_deleted": result.get("suite_runs_deleted"),
            "case_runs_deleted": result.get("case_runs_deleted"),
        },
    )
    return result


@router.get("/suites")
async def list_eval_suites(
    enabled: bool | None = None,
    user: User = Depends(require_scope("evals:read")),
):
    del user
    return await case_store.list_suites(enabled=enabled)


@router.get("/targets")
async def list_eval_execution_targets(
    user: User = Depends(require_scope("evals:read")),
):
    """Strict catalog of Agents/Teams that can back a newly authored Suite."""
    del user
    data = list_eval_targets()
    return {
        "data": data,
        "meta": pagination_meta(page=1, limit=max(len(data), 1), total_count=len(data)),
    }


@router.post("/suites")
async def create_eval_suite(
    body: EvalSuiteCreateRequest,
    user: User = Depends(require_scope("evals:write")),
):
    try:
        return await case_store.create_suite(body.model_dump(), user)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error("创建 Agent Eval 套件失败: {}", exc)
        raise HTTPException(
            status_code=500, detail="Failed to create eval suite"
        ) from exc


@router.get("/suites/{suite_id}")
async def get_eval_suite(
    suite_id: str,
    user: User = Depends(require_scope("evals:read")),
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
    user: User = Depends(require_scope("evals:write")),
):
    del user
    try:
        suite = await case_store.update_suite(
            suite_id, body.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error("更新 Agent Eval 套件失败: {}", exc)
        raise HTTPException(
            status_code=500, detail="Failed to update eval suite"
        ) from exc
    if suite is None:
        raise _not_found("Eval suite")
    return suite


@router.delete("/suites/{suite_id}")
async def delete_eval_suite(
    suite_id: str,
    user: User = Depends(require_scope("evals:delete")),
):
    """Permanently delete an author-owned Suite and its workbench history.

    Imported Pack Suites keep their stricter versioned removal endpoint so the
    destructive scope is explicit to the operator.
    """
    try:
        result = await case_store.delete_suite(suite_id)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error("删除 Agent Eval 套件失败: {}", exc)
        raise HTTPException(
            status_code=500, detail="Failed to delete eval suite"
        ) from exc
    if result is None:
        raise _not_found("Eval suite")

    await record_audit_event_async(
        user,
        action="evals.suite_delete",
        resource_type="eval_suite",
        resource_id=suite_id,
        metadata={
            "suite_ids": result.get("suite_ids"),
            "suites_deleted": result.get("suites_deleted"),
            "cases_deleted": result.get("cases_deleted"),
            "suite_runs_deleted": result.get("suite_runs_deleted"),
            "case_runs_deleted": result.get("case_runs_deleted"),
        },
    )
    return result


@router.get("/cases")
async def list_eval_cases(
    suite_id: str | None = None,
    enabled: bool | None = None,
    tag: str | None = None,
    name: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=100, ge=1, le=100),
    user: User = Depends(require_scope("evals:read")),
):
    del user
    try:
        # FastAPI resolves these Query defaults before production calls. Keep
        # direct service-level invocation deterministic for focused tests too.
        safe_page = page if isinstance(page, int) else 1
        safe_limit = limit if isinstance(limit, int) else 100
        return await case_store.list_cases_page(
            suite_id=suite_id,
            enabled=enabled,
            tag=tag,
            name=name,
            page=safe_page,
            limit=safe_limit,
        )
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc


@router.post("/cases")
async def create_eval_case(
    body: EvalCaseCreateRequest,
    user: User = Depends(require_scope("evals:write")),
):
    del user
    try:
        return await case_store.create_case(body.model_dump())
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error("创建 Agent Eval 用例失败: {}", exc)
        raise HTTPException(
            status_code=500, detail="Failed to create eval case"
        ) from exc


@router.get("/cases/{case_id}")
async def get_eval_case(
    case_id: str,
    user: User = Depends(require_scope("evals:read")),
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
    user: User = Depends(require_scope("evals:write")),
):
    del user
    try:
        case = await case_store.update_case(
            case_id, body.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error("更新 Agent Eval 用例失败: {}", exc)
        raise HTTPException(
            status_code=500, detail="Failed to update eval case"
        ) from exc
    if case is None:
        raise _not_found("Eval case")
    return case


@router.delete("/cases/{case_id}")
async def delete_eval_case(
    case_id: str,
    user: User = Depends(require_scope("evals:delete")),
):
    """Delete one author-owned Case definition, retaining historical results."""
    try:
        deleted_case = await case_store.delete_case(case_id)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error("删除 Agent Eval 用例失败: {}", exc)
        raise HTTPException(
            status_code=500, detail="Failed to delete eval case"
        ) from exc
    if deleted_case is None:
        raise _not_found("Eval case")

    await record_audit_event_async(
        user,
        action="evals.case_delete",
        resource_type="eval_case",
        resource_id=case_id,
        metadata={
            "suite_id": deleted_case.get("suite_id"),
            "run_history_retained": True,
        },
    )
    return {
        "case_id": deleted_case["id"],
        "suite_id": deleted_case["suite_id"],
        "run_history_retained": True,
    }


@router.get("/suites/{suite_id}/runs")
async def list_eval_suite_runs(
    suite_id: str,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(require_scope("evals:read")),
):
    del user
    return await case_store.list_suite_runs(
        suite_id=suite_id,
        status=status,
        page=page,
        limit=limit,
    )


@router.get("/suite-runs/{suite_run_id}/case-runs")
async def list_eval_suite_run_case_runs(
    suite_run_id: str,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(require_scope("evals:read")),
):
    """Case runs for one suite run (Agno SuiteResult.cases drill-down)."""
    del user
    suite_run = await case_store.get_suite_run(suite_run_id)
    if suite_run is None:
        raise _not_found("Eval suite run")
    return await case_store.list_case_runs(
        suite_run_id=suite_run_id,
        status=status,
        page=page,
        limit=limit,
    )


@router.post("/suite-runs/{suite_run_id}/report")
async def export_eval_suite_run_report(
    suite_run_id: str,
    user: User = Depends(require_scope("evals:write")),
):
    """Export a privacy-preserving, Agno-shaped SuiteResult JSON artifact.

    Exporting report evidence can expose judge explanations, so it deliberately
    requires ``evals:write`` and produces an audit event.  Raw prompts and model
    outputs are not stored in this report.
    """
    suite_run = await case_store.get_suite_run(suite_run_id)
    if suite_run is None:
        raise _not_found("Eval suite run")
    try:
        report = report_service.build_suite_run_report(
            suite_run,
            case_results=await case_store.list_suite_run_case_result_lites(
                suite_run_id
            ),
        )
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc

    await record_audit_event_async(
        user,
        action="evals.suite_report_export",
        resource_type="eval_suite_run",
        resource_id=suite_run_id,
        metadata={
            "suite_id": report["suite_run"]["suite_id"],
            "format": report["format"],
            "case_count": len(report["cases"]),
            "case_results_available": report["case_results_available"],
            "raw_inputs_included": False,
            "raw_outputs_included": False,
        },
    )
    return report


@router.post("/suites/{suite_id}/runs", status_code=202)
async def run_eval_suite(
    suite_id: str,
    body: EvalSuiteRunRequest | None = None,
    user: User = Depends(require_scope("evals:write")),
):
    try:
        plan = await agent_eval_runner.prepare_suite_run(
            suite_id,
            tag=body.tag if body is not None else None,
            name=body.name if body is not None else None,
            default_timeout=body.default_timeout if body is not None else 120,
        )
        initial_summary = agent_eval_runner.initial_suite_run_summary(plan)
        suite_run, job_id = await enqueue_suite_run(
            suite_id=suite_id,
            actor=user,
            plan=plan,
            summary=initial_summary,
        )
        return {**suite_run, "job_id": job_id}
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error("排队 Agent Eval 套件失败: {}", exc)
        raise HTTPException(status_code=500, detail="Failed to queue eval suite") from exc


@router.post("/suite-runs/{suite_run_id}/cancel", status_code=202)
async def cancel_eval_suite_run(
    suite_run_id: str,
    user: User = Depends(require_scope("evals:write")),
):
    """Request cooperative cancellation for a queued or active SuiteRun."""
    try:
        suite_run = await case_store.request_suite_run_cancel(suite_run_id)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error("取消 Agent Eval 套件运行失败: {}", exc)
        raise HTTPException(
            status_code=500, detail="Failed to cancel eval suite run"
        ) from exc
    if suite_run is None:
        raise _not_found("Eval suite run")

    await record_audit_event_async(
        user,
        action="evals.suite_run_cancel",
        resource_type="eval_suite_run",
        resource_id=suite_run_id,
        metadata={
            "suite_id": suite_run.get("suite_id"),
            "status": suite_run.get("status"),
            "cancel_requested": suite_run.get("status") == "cancelling",
        },
    )
    return suite_run


@router.get("/cases/{case_id}/runs")
async def list_eval_case_runs(
    case_id: str,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(require_scope("evals:read")),
):
    del user
    return await case_store.list_case_runs(
        case_id=case_id,
        status=status,
        page=page,
        limit=limit,
    )


@router.post("/cases/{case_id}/runs")
async def run_eval_case(
    case_id: str,
    user: User = Depends(require_scope("evals:write")),
):
    try:
        return await agent_eval_runner.run_case(case_id, actor=user)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error("运行 Agent Eval 用例失败: {}", exc)
        raise HTTPException(status_code=500, detail="Failed to run eval case") from exc


@router.post("/case-runs/{case_run_id}/replay")
async def replay_eval_case_run(
    case_run_id: str,
    user: User = Depends(require_scope("evals:write")),
):
    try:
        return await agent_eval_runner.replay_case_run(case_run_id, actor=user)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    except Exception as exc:
        logger.error("重放 Agent Eval 用例运行失败: {}", exc)
        raise HTTPException(
            status_code=500, detail="Failed to replay eval case run"
        ) from exc


@router.get("/agno-runs")
async def list_agno_eval_runs(
    limit: int = Query(default=50, ge=1, le=100),
    page: int = Query(default=1, ge=1),
    eval_type: list[EvalType] | None = Query(default=None),
    agent_id: str | None = None,
    user: User = Depends(require_scope("evals:read")),
):
    """List Agno eval runs with AgentOS-style ``data`` / ``meta`` envelope.

    Suites/cases remain under this router as workbench resources; this path is
    the Agno eval-result read surface (maps to AgentOS ``GET /eval-runs``).
    """
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
    user: User = Depends(require_scope("evals:read")),
):
    del user
    result = await result_service.get_agno_eval_run(eval_run_id)
    if result is None:
        raise _not_found("Agno eval run")
    return result


@router.get("/failures")
async def list_eval_failures(
    limit: int = Query(default=50, ge=1, le=100),
    user: User = Depends(require_scope("evals:read")),
):
    del user
    failures = await result_service.list_failed_eval_runs(limit=limit)
    eval_run_ids = [
        eval_run_id for item in failures if (eval_run_id := _eval_run_id(item))
    ]
    case_runs_by_eval_id = await case_store.list_case_runs_by_agno_eval_run_ids(
        eval_run_ids
    )
    items = [
        _with_case_run_replay_link(item, case_runs_by_eval_id) for item in failures
    ]
    return {
        "data": items,
        "meta": pagination_meta(
            page=1,
            limit=max(int(limit or 1), 1),
            total_count=len(items),
        ),
    }
