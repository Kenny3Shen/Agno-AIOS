from api.services.agent_catalog import (
    DEFAULT_AGENT_ID,
    get_agent_profile,
    list_chat_agents,
    list_workflow_executor_options,
    normalize_agent_id,
    profile_attaches_skills,
    profile_connects_mcp,
)
from api.services.agent_tools import build_tools_for_profile


def test_chat_agents_include_analysis_and_research():
    ids = {row["id"] for row in list_chat_agents()}
    assert ids == {"security-operations", "data-analysis", "deep-research"}


def test_workflow_executors_include_safe_fallback():
    refs = {row["ref"] for row in list_workflow_executor_options()}
    assert "security-operations" in refs
    assert "data-analysis" in refs
    assert "deep-research" in refs
    assert "safe-fallback" in refs


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


def test_builtin_tools_load():
    for agent_id in ("data-analysis", "deep-research"):
        tools = build_tools_for_profile(get_agent_profile(agent_id))
        assert tools, f"{agent_id} should have tools"
        names = {type(t).__name__ for t in tools}
        if agent_id == "data-analysis":
            assert "CalculatorTools" in names
            assert "PythonTools" in names
            assert "FileTools" in names
            assert "CsvTools" in names
        if agent_id == "deep-research":
            assert "ReasoningTools" in names
            assert "WebsiteTools" in names


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
    kind2, aid = resolve_chat_run_target("research-analysis-team")
    assert kind2 == "agent"
    assert aid == "security-operations"


def test_deep_research_declares_web_search():
    profile = get_agent_profile("deep-research")
    assert "web_search" in tuple(profile.get("builtin_tools") or ())


def test_stage_media_into_analysis_dir(tmp_path, monkeypatch):
    from api.services import agent_tools as at

    monkeypatch.setattr(at, "analysis_work_dir", lambda: tmp_path)

    class _Media:
        def __init__(self, filename: str, content: bytes):
            self.filename = filename
            self.content = content

    paths = at.stage_media_into_analysis_dir(
        [
            _Media("sample.csv", b"a,b\n1,2\n"),
            _Media("../evil.csv", b"x"),  # basename only
        ]
    )
    assert len(paths) == 2
    assert (tmp_path / "sample.csv").read_bytes() == b"a,b\n1,2\n"
    assert (tmp_path / "evil.csv").exists()


def test_profile_uses_analysis_sandbox():
    from api.services.agent_tools import profile_uses_analysis_sandbox

    assert profile_uses_analysis_sandbox(get_agent_profile("data-analysis")) is True
    assert profile_uses_analysis_sandbox(get_agent_profile("deep-research")) is False
    assert profile_uses_analysis_sandbox(get_agent_profile("security-operations")) is False


def test_csv_tools_see_staged_files(tmp_path, monkeypatch):
    from api.services import agent_tools as at

    monkeypatch.setattr(at, "analysis_work_dir", lambda: tmp_path)
    (tmp_path / "metrics.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    tools = at.build_tools_for_profile(get_agent_profile("data-analysis"))
    csv_tools = next(t for t in tools if type(t).__name__ == "CsvTools")
    names = {p.name for p in getattr(csv_tools, "csvs", [])}
    assert "metrics.csv" in names


def test_sql_tools_soft_fail_without_url(monkeypatch):
    from api.services import agent_tools as at
    from api.services.agent_catalog import get_agent_profile

    monkeypatch.delenv("TAIS_DATA_SQL_URL", raising=False)
    monkeypatch.delenv("TAIS_ANALYTICS_DB_URL", raising=False)
    tools = at.build_tools_for_profile(get_agent_profile("data-analysis"))
    names = {type(t).__name__ for t in tools}
    assert "SQLTools" not in names
    assert "PythonTools" in names
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
        tools = at.build_tools_for_profile(get_agent_profile("data-analysis"))
        assert any(type(t).__name__ == "_FakeSQL" for t in tools)
    finally:
        if original is not None:
            at._BUILDERS["sql"] = original


def test_csv_tools_disable_query_and_web_search_mounts(tmp_path, monkeypatch):
    """CSV is list/read only; SQL is SQLTools; web search still mounts with ddgs."""
    import api.services.agent_tools as at
    from api.services.agent_catalog import get_agent_profile

    work = tmp_path / "sandbox"
    work.mkdir()
    (work / "demo.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    monkeypatch.setattr(at, "analysis_work_dir", lambda: work)
    monkeypatch.delenv("TAIS_DATA_SQL_URL", raising=False)

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

