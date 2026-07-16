from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from inspect import isawaitable
from typing import Any

from agno.eval.accuracy import AccuracyEval
from agno.eval.agent_as_judge import AgentAsJudgeEval
from agno.eval.performance import PerformanceEval
from agno.eval.reliability import ReliabilityEval

from api.auth.claims import actor_id
from api.services import agent_eval_case_store as case_store
from api.services.postgres_store import get_async_agno_postgres_db
from api.services.security_run_runtime import (
    DEFAULT_SECURITY_RUN_RUNTIME,
    SecurityRunRequest,
    SecurityRunRuntime,
)


@dataclass(frozen=True)
class AgentEvalRunnerDependencies:
    security_runtime: SecurityRunRuntime = DEFAULT_SECURITY_RUN_RUNTIME
    get_eval_db: Callable[[], Any] = get_async_agno_postgres_db
    accuracy_eval_cls: Any = AccuracyEval
    judge_eval_cls: Any = AgentAsJudgeEval
    reliability_eval_cls: Any = ReliabilityEval
    performance_eval_cls: Any = PerformanceEval


async def _maybe_await(value: Any) -> Any:
    if isawaitable(value):
        return await value
    return value


def _case_session_id(case_run_id: str) -> str:
    return f"eval_{case_run_id}"


def _eval_types(case: dict[str, Any]) -> set[str]:
    values = case.get("eval_types")
    if not isinstance(values, list):
        return {"accuracy"}
    return {str(value) for value in values}


def _eval_id(eval_instance: Any) -> str | None:
    value = getattr(eval_instance, "eval_id", None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _response_value(response: Any, name: str) -> str:
    value = getattr(response, name, "")
    if value is None:
        return ""
    return str(value)


async def run_case(
    case_id: str,
    actor: Any,
    suite_run_id: str | None = None,
    replay_of_case_run_id: str | None = None,
    dependencies: AgentEvalRunnerDependencies | None = None,
) -> dict[str, Any]:
    deps = dependencies or AgentEvalRunnerDependencies()
    case = await case_store.get_case(case_id)
    if case is None:
        raise ValueError(f"Eval case not found: {case_id}")
    if not bool(case.get("enabled", True)):
        raise ValueError(f"Eval case is disabled: {case_id}")

    case_run = await case_store.create_case_run(
        case_id,
        suite_run_id=suite_run_id,
        replay_of_case_run_id=replay_of_case_run_id,
    )
    case_run_id = str(case_run["id"])
    session_id = _case_session_id(case_run_id)
    eval_db = await _maybe_await(deps.get_eval_db())
    enabled_eval_types = _eval_types(case)
    eval_run_ids: list[str] = []
    response: Any | None = None

    try:
        request = SecurityRunRequest.from_chat_args(
            str(case.get("input", "")),
            session_id=session_id,
            user_id=actor_id(actor),
        )
        async with deps.security_runtime.security_agent_context(request) as agent:
            if "accuracy" in enabled_eval_types:
                accuracy_eval = deps.accuracy_eval_cls(
                    input=case.get("input", ""),
                    expected_output=case.get("expected_output", ""),
                    agent=agent,
                    name=case.get("name"),
                    db=eval_db,
                )
                await accuracy_eval.arun(print_summary=False, print_results=False)
                if eval_id := _eval_id(accuracy_eval):
                    eval_run_ids.append(eval_id)

            if enabled_eval_types & {"agent_as_judge", "reliability"}:
                response = await agent.arun(
                    case.get("input", ""),
                    session_id=session_id,
                    user_id=actor_id(actor),
                    stream=False,
                )

            if "agent_as_judge" in enabled_eval_types:
                judge_eval = deps.judge_eval_cls(
                    criteria=case.get("criteria", ""),
                    threshold=case.get("threshold", 7),
                    name=case.get("name"),
                    db=eval_db,
                )
                await judge_eval.arun(
                    input=case.get("input", ""),
                    output=str(getattr(response, "content", "")),
                    print_summary=False,
                    print_results=False,
                )
                if eval_id := _eval_id(judge_eval):
                    eval_run_ids.append(eval_id)

            if "reliability" in enabled_eval_types:
                reliability_eval = deps.reliability_eval_cls(
                    name=case.get("name"),
                    agent_response=response,
                    expected_tool_calls=case.get("expected_tool_calls", []),
                    allow_additional_tool_calls=case.get("allow_additional_tool_calls", False),
                    expected_tool_call_arguments=case.get("expected_tool_call_arguments", {}),
                    db=eval_db,
                )
                await reliability_eval.arun(print_results=False)
                if eval_id := _eval_id(reliability_eval):
                    eval_run_ids.append(eval_id)

            if "performance" in enabled_eval_types:

                async def performance_func() -> Any:
                    return await agent.arun(
                        case.get("input", ""),
                        session_id=session_id,
                        user_id=actor_id(actor),
                        stream=False,
                    )

                performance_config = case.get("performance_config")
                if not isinstance(performance_config, dict):
                    performance_config = {}
                performance_eval = deps.performance_eval_cls(
                    func=performance_func,
                    name=case.get("name"),
                    db=eval_db,
                    warmup_runs=performance_config.get("warmup_runs", 10),
                    num_iterations=performance_config.get("num_iterations", 50),
                    measure_runtime=performance_config.get("measure_runtime", True),
                    measure_memory=performance_config.get("measure_memory", True),
                )
                await performance_eval.arun(print_summary=False, print_results=False)
                if eval_id := _eval_id(performance_eval):
                    eval_run_ids.append(eval_id)

        values = {
            "session_id": session_id,
            "agno_eval_run_ids": eval_run_ids,
            "agent_run_id": _response_value(response, "run_id"),
            "trace_id": _response_value(response, "trace_id"),
        }
        marked = await case_store.mark_case_run(case_run_id, "passed", values)
        return marked or {**case_run, "status": "passed", **values}
    except Exception as exc:
        values = {
            "session_id": session_id,
            "agno_eval_run_ids": eval_run_ids,
            "error_type": type(exc).__name__,
            "error_summary": str(exc),
        }
        marked = await case_store.mark_case_run(case_run_id, "failed", values)
        if marked is not None:
            return marked
        return {**case_run, "status": "failed", **values}


async def run_suite(
    suite_id: str,
    actor: Any,
    dependencies: AgentEvalRunnerDependencies | None = None,
) -> dict[str, Any]:
    suite = await case_store.get_suite(suite_id)
    if suite is None:
        raise ValueError(f"Eval suite not found: {suite_id}")
    if not bool(suite.get("enabled", True)):
        raise ValueError(f"Eval suite is disabled: {suite_id}")

    suite_run = await case_store.create_suite_run(suite_id, actor)
    suite_run_id = str(suite_run["id"])
    cases_payload = await case_store.list_cases(suite_id=suite_id)
    cases = cases_payload.get("data") if isinstance(cases_payload, dict) else cases_payload
    if not isinstance(cases, list):
        cases = []
    summary = {"passed": 0, "failed": 0, "errored": 0, "skipped": 0}

    for case in cases:
        case_id = str(case.get("id", ""))
        if not case_id:
            summary["errored"] += 1
            continue
        if not bool(case.get("enabled", True)):
            summary["skipped"] += 1
            continue
        try:
            result = await run_case(
                case_id,
                actor=actor,
                suite_run_id=suite_run_id,
                dependencies=dependencies,
            )
        except Exception:
            summary["errored"] += 1
            continue
        status = str(result.get("status", ""))
        if status == "passed":
            summary["passed"] += 1
        elif status == "failed":
            summary["failed"] += 1
        else:
            summary["errored"] += 1

    status = "passed" if summary["failed"] == 0 and summary["errored"] == 0 else "failed"
    marked = await case_store.mark_suite_run(suite_run_id, status, summary=summary)
    return marked or {**suite_run, "status": status, "summary": summary}


async def replay_case_run(
    case_run_id: str,
    actor: Any,
    dependencies: AgentEvalRunnerDependencies | None = None,
) -> dict[str, Any]:
    source_run = await case_store.get_case_run(case_run_id)
    if source_run is None:
        raise ValueError(f"Eval case run not found: {case_run_id}")
    case_id = str(source_run.get("case_id", "")).strip()
    if not case_id:
        raise ValueError(f"Eval case run has no case_id: {case_run_id}")
    return await run_case(
        case_id,
        actor=actor,
        replay_of_case_run_id=case_run_id,
        dependencies=dependencies,
    )
