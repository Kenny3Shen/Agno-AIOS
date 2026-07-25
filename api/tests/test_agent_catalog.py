import pytest
from types import SimpleNamespace

from api.services.agent_catalog import (
    DEFAULT_AGENT_ID,
    get_agent_profile,
    list_workflow_executor_options,
    normalize_agent_id,
    profile_attaches_skills,
    profile_connects_mcp,
)
from api.services.agent_tools import (
    AnalysisWorkspaceRequiredError,
    analysis_workspace_context,
    build_tools_for_profile,
)


def test_normalize_unknown_agent():
    assert normalize_agent_id(None) == DEFAULT_AGENT_ID
    assert normalize_agent_id("nope") == DEFAULT_AGENT_ID
    assert normalize_agent_id("deep-research") == "deep-research"


def test_specialists_skip_mcp_and_skills():
    assert profile_connects_mcp("data-analysis") is False
    assert profile_attaches_skills("data-analysis") is False
    assert profile_connects_mcp("deep-research") is False
    assert profile_attaches_skills("security-operations") is True
    assert profile_connects_mcp("security-operations") is True


def test_workflow_executors_include_builtin_agents():
    items = list_workflow_executor_options()
    refs = {item["ref"] for item in items}
    assert "security-operations" in refs
    assert "safe-fallback" in refs
    by_ref = {item["ref"]: item for item in items}
    assert by_ref["security-operations"]["name"]
    assert by_ref["security-operations"]["description"]
    assert by_ref["security-operations"]["category"] == "operations"
    capabilities = str(by_ref["security-operations"]["capabilities"]).split(",")
    assert "hitl" in capabilities
    assert by_ref["safe-fallback"]["category"] == "lite"
    assert by_ref["safe-fallback"]["recommended_for"]


def test_analysis_tools_require_a_bound_run_workspace():
    with pytest.raises(AnalysisWorkspaceRequiredError):
        build_tools_for_profile(get_agent_profile("data-analysis"))


def test_builtin_tools_load_in_isolated_workspace(monkeypatch):
    # Local Python is intentionally disabled unless a developer consciously
    # enables its unsafe host-process escape hatch.
    monkeypatch.delenv("TAIS_ALLOW_UNSAFE_LOCAL_PYTHON", raising=False)
    with analysis_workspace_context("catalog-tools") as workspace:
        data_tools = build_tools_for_profile(get_agent_profile("data-analysis"))
        research_tools = build_tools_for_profile(get_agent_profile("deep-research"))
        data_names = {type(t).__name__ for t in data_tools}
        research_names = {type(t).__name__ for t in research_tools}
        assert "CalculatorTools" in data_names
        assert "PythonTools" not in data_names
        assert "FileTools" in data_names
        assert "CsvTools" in data_names
        assert "ReasoningTools" in research_names
        assert "WebsiteTools" in research_names
        for tool in data_tools:
            base_dir = getattr(tool, "base_dir", None)
            if base_dir is not None:
                assert base_dir == workspace.path


def test_from_chat_args_specialist_clears_skills():
    from api.services.security_run_runtime import SecurityRunRequest

    req = SecurityRunRequest.from_chat_args(
        "分析这组数字的均值",
        agent_id="data-analysis",
        enable_tools=True,
    )
    assert req.agent_id == "data-analysis"
    assert req.skill_names == []


def test_should_connect_mcp_respects_agent_profile():
    from api.services.security_run_runtime import should_connect_mcp

    assert should_connect_mcp(None, enable_tools=True, agent_id="security-operations") is True
    assert should_connect_mcp(None, enable_tools=True, agent_id="data-analysis") is False
    assert should_connect_mcp([], enable_tools=True, agent_id="security-operations") is False


def test_resolve_chat_run_target_team(monkeypatch):
    from api.services.agent_catalog import resolve_chat_run_target

    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")
    kind, tid = resolve_chat_run_target("research-analysis-team")
    assert kind == "team"
    assert tid == "research-analysis-team"

    monkeypatch.delenv("TAIS_ENABLE_AGNO_TEAM", raising=False)
    kind2, tid2 = resolve_chat_run_target("research-analysis-team")
    assert kind2 == "team"
    assert tid2 == "research-analysis-team"


def test_stage_media_into_analysis_dir():
    from api.services import agent_tools as at

    class _Media:
        def __init__(self, filename: str, content: bytes):
            self.filename = filename
            self.content = content

    with at.analysis_workspace_context("stage-media") as workspace:
        paths = at.stage_media_into_analysis_dir(
            [
                _Media("sample.csv", b"a,b\n1,2\n"),
                _Media("../evil.csv", b"x"),  # basename only
            ]
        )
        assert len(paths) == 2
        assert (workspace.path / "sample.csv").read_bytes() == b"a,b\n1,2\n"
        assert (workspace.path / "evil.csv").exists()


def test_analysis_workspace_is_private_unique_and_cleaned():
    from api.services import agent_tools as at

    class _Media:
        filename = "tenant.csv"
        content = b"value\n7\n"

    with at.analysis_workspace_context("first-run") as first:
        first_path = first.path
        assert first_path.stat().st_mode & 0o777 == 0o700
        staged = at.stage_media_into_analysis_dir([_Media()])
        assert staged == [first_path / "tenant.csv"]
        assert staged[0].read_bytes() == b"value\n7\n"

    assert not first_path.exists()
    with at.analysis_workspace_context("second-run") as second:
        assert second.path != first_path
        assert not (second.path / "tenant.csv").exists()


def test_local_python_requires_explicit_nonproduction_opt_in(monkeypatch):
    from api.services import agent_tools as at

    monkeypatch.setattr(
        at, "get_settings", lambda: SimpleNamespace(environment="development")
    )
    monkeypatch.setenv("TAIS_ALLOW_UNSAFE_LOCAL_PYTHON", "1")
    with at.analysis_workspace_context("unsafe-dev"):
        tools = at.build_tools_for_profile(get_agent_profile("data-analysis"))
    assert "PythonTools" in {type(tool).__name__ for tool in tools}


def test_local_python_fails_closed_in_production(monkeypatch):
    from api.services import agent_tools as at

    monkeypatch.setattr(
        at, "get_settings", lambda: SimpleNamespace(environment="production")
    )
    monkeypatch.setenv("TAIS_ALLOW_UNSAFE_LOCAL_PYTHON", "1")
    with at.analysis_workspace_context("production"):
        tools = at.build_tools_for_profile(get_agent_profile("data-analysis"))
    assert "PythonTools" not in {type(tool).__name__ for tool in tools}


def test_profile_uses_analysis_sandbox():
    from api.services.agent_tools import profile_uses_analysis_sandbox

    assert profile_uses_analysis_sandbox(get_agent_profile("data-analysis")) is True
    assert profile_uses_analysis_sandbox(get_agent_profile("deep-research")) is False
    assert profile_uses_analysis_sandbox(get_agent_profile("security-operations")) is False


def test_csv_tools_see_staged_files():
    from api.services import agent_tools as at

    with at.analysis_workspace_context("csv-files") as workspace:
        (workspace.path / "metrics.csv").write_text("x,y\n1,2\n", encoding="utf-8")
        tools = at.build_tools_for_profile(get_agent_profile("data-analysis"))
        csv_tools = next(t for t in tools if type(t).__name__ == "CsvTools")
        names = {p.name for p in getattr(csv_tools, "csvs", [])}
        assert "metrics.csv" in names


def test_sql_tools_soft_fail_without_url(monkeypatch):
    from api.services import agent_tools as at
    from api.services.agent_catalog import get_agent_profile

    monkeypatch.delenv("TAIS_DATA_SQL_URL", raising=False)
    monkeypatch.delenv("TAIS_ANALYTICS_DB_URL", raising=False)
    with at.analysis_workspace_context("sql-tools-off"):
        tools = at.build_tools_for_profile(get_agent_profile("data-analysis"))
    names = {type(t).__name__ for t in tools}
    assert "SQLTools" not in names
    assert "PythonTools" not in names
    assert "sql" in tuple(get_agent_profile("data-analysis").get("builtin_tools") or ())


def test_sql_tools_load_when_url_set(monkeypatch):
    from api.services import agent_tools as at
    from api.services.agent_catalog import get_agent_profile

    class _FakeSQL:
        pass

    monkeypatch.setenv("TAIS_DATA_SQL_URL", "postgresql+psycopg://readonly@localhost/analytics")
    monkeypatch.setattr(at, "_build_sql", lambda: _FakeSQL())
    # force rebuild path via real builder by patching SQLTools
    # Use build_tools which calls _build_sql through _BUILDERS
    # rebind builders
    original = at._BUILDERS.get("sql")
    at._BUILDERS["sql"] = lambda: _FakeSQL()
    try:
        with at.analysis_workspace_context("sql-tools-on"):
            tools = at.build_tools_for_profile(get_agent_profile("data-analysis"))
        assert any(type(t).__name__ == "_FakeSQL" for t in tools)
    finally:
        if original is not None:
            at._BUILDERS["sql"] = original


def test_csv_tools_disable_query_and_web_search_mounts(monkeypatch):
    """CSV is list/read only; SQL is SQLTools; web search still mounts with ddgs."""
    import api.services.agent_tools as at
    from api.services.agent_catalog import get_agent_profile

    monkeypatch.delenv("TAIS_DATA_SQL_URL", raising=False)

    with at.analysis_workspace_context("csv-functions") as workspace:
        (workspace.path / "demo.csv").write_text("x,y\n1,2\n", encoding="utf-8")
        csv_tool = at._build_csv()
        assert csv_tool is not None
        functions = getattr(csv_tool, "functions", {}) or {}
        assert "query_csv_file" not in functions
        # list/read still available
        assert "list_csv_files" in functions or hasattr(csv_tool, "list_csv_files")

        data_tools = at.build_tools_for_profile(get_agent_profile("data-analysis"))
        assert any(type(t).__name__ == "CsvTools" for t in data_tools)
        assert not any(type(t).__name__ == "SQLTools" for t in data_tools)

    web = at._build_web_search()
    assert web is not None
    research_tools = at.build_tools_for_profile(get_agent_profile("deep-research"))
    assert any("DuckDuckGo" in type(t).__name__ or "WebSearch" in type(t).__name__ for t in research_tools)
