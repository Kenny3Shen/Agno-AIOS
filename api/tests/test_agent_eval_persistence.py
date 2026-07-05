from types import SimpleNamespace

from api.auth.permissions import has_permission
from api.persistence.agent_evals import (
    agent_eval_case_runs_table,
    agent_eval_cases_table,
    agent_eval_suite_runs_table,
    agent_eval_suites_table,
    create_case_row_async,
    create_case_run_row_async,
    create_suite_row_async,
    create_suite_run_row_async,
    get_case_row_async,
    get_case_run_row_async,
    get_suite_row_async,
    get_suite_run_row_async,
    list_case_rows_async,
    list_case_run_rows_async,
    list_suite_rows_async,
    list_suite_run_rows_async,
    update_case_row_async,
    update_case_run_row_async,
    update_suite_row_async,
    update_suite_run_row_async,
)
from api.services.security_policy import CONTROL_MODULE_PERMISSIONS


def actor(role: str):
    return SimpleNamespace(role=role, is_superuser=False)


def test_evaluation_control_module_uses_agent_eval_read_permission():
    assert CONTROL_MODULE_PERMISSIONS["evaluation"] == "agent_eval:read"
    assert has_permission(actor("user"), CONTROL_MODULE_PERMISSIONS["evaluation"])


def test_agent_eval_tables_use_jsonb_and_expected_names():
    suites = agent_eval_suites_table()
    cases = agent_eval_cases_table()
    suite_runs = agent_eval_suite_runs_table()
    case_runs = agent_eval_case_runs_table()

    assert suites.name == "agent_eval_suites"
    assert cases.name == "agent_eval_cases"
    assert suite_runs.name == "agent_eval_suite_runs"
    assert case_runs.name == "agent_eval_case_runs"
    assert cases.c.eval_types.type.__class__.__name__ == "JSONB"
    assert cases.c.expected_tool_calls.type.__class__.__name__ == "JSONB"
    assert case_runs.c.agno_eval_run_ids.type.__class__.__name__ == "JSONB"


def test_agent_eval_crud_helpers_are_exported():
    assert create_suite_row_async
    assert list_suite_rows_async
    assert get_suite_row_async
    assert update_suite_row_async
    assert create_case_row_async
    assert list_case_rows_async
    assert get_case_row_async
    assert update_case_row_async
    assert create_suite_run_row_async
    assert list_suite_run_rows_async
    assert get_suite_run_row_async
    assert update_suite_run_row_async
    assert create_case_run_row_async
    assert list_case_run_rows_async
    assert get_case_run_row_async
    assert update_case_run_row_async
