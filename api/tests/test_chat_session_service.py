from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agno.session.agent import AgentSession
import pytest

from api.services import chat_session_service
from api.services.chat_run_events import approval_rejection_reason


class FakeAgnoDb:
    def __init__(
        self,
        rows: list[dict],
        session_row: dict | None = None,
        session: AgentSession | None = None,
    ):
        self.rows = rows
        self.session_row = session_row
        self.session = session
        self.get_sessions_kwargs = None
        self.upserted = None

    def get_sessions(self, **kwargs):
        self.get_sessions_kwargs = kwargs
        return (list(self.rows), len(self.rows))

    def get_session(self, session_id: str, deserialize: bool = True):
        if deserialize:
            return self.session
        return self.session_row

    def upsert_session(self, session):
        self.upserted = session
        return session

    async def _get_table(self, **_kwargs):
        return None


class AsyncFakeAgnoDb(FakeAgnoDb):
    async def get_sessions(self, **kwargs):
        self.get_sessions_kwargs = kwargs
        return (list(self.rows), len(self.rows))

    async def get_session(self, session_id: str, deserialize: bool = True):
        if deserialize:
            return self.session
        return self.session_row

    async def upsert_session(self, session):
        self.upserted = session
        return session


def test_approval_rejection_reason_prefers_agno_requirement_note():
    run = {
        "requirements": [
            {
                "confirmation_note": "Rejected by administrator: 保留取证后再处理",
                "tool_execution": {"confirmation_note": "Tool call was rejected"},
            }
        ],
        "tools": [{"confirmation_note": "Tool call was rejected"}],
        "metadata": {"approval": {"resolution_data": {"note": "旧的备注"}}},
    }

    assert approval_rejection_reason(run) == "保留取证后再处理"



def test_approval_rejection_reason_ignores_legacy_resolution_rejection_reason():
    run = {
        "requirements": [],
        "tools": [],
        "metadata": {
            "approval": {
                "resolution_data": {
                    "rejection_reason": "legacy only",
                    "note": "canonical note",
                }
            }
        },
    }
    assert approval_rejection_reason(run) == "canonical note"

    legacy_only = {
        "requirements": [],
        "tools": [],
        "metadata": {"approval": {"resolution_data": {"rejection_reason": "legacy only"}}},
    }
    assert approval_rejection_reason(legacy_only) == ""


@pytest.mark.asyncio
async def test_list_sessions_async_projects_sorted_archived_session_rows():
    # Rows arrive newest-first from SQL; service keeps order when already_sorted.
    rows = [
        {
            "session_id": "newer",
            "created_at": 3,
            "updated_at": 4,
            "user_id": "u1",
            "runs": [{"input": "newer preview"}],
            "metadata": {"agno_aios_archived": True},
        },
        {
            "session_id": "older",
            "created_at": 1,
            "updated_at": 2,
            "user_id": "u1",
            "runs": [{"input": {"input_content": "older preview"}}],
            "metadata": {},
        },
    ]

    async def fake_query(**kwargs):
        assert kwargs["include_archived"] is True
        assert kwargs["owner_user_id"] == "u1"
        assert kwargs["page"] == 1
        assert kwargs["limit"] == 40
        return rows, 2

    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(chat_session_service, "_query_sessions_page", fake_query),
    ):
        result = await chat_session_service.list_sessions_async(
            include_archived=True, owner_user_id="u1", include_runs=True
        )
    assert set(result.keys()) == {"data", "meta"}
    sessions = result["data"]
    assert result["meta"]["total_count"] == 2
    assert result["meta"]["page"] == 1
    assert result["meta"]["limit"] == 40
    assert [session["session_id"] for session in sessions] == ["newer", "older"]
    assert sessions[0]["preview"] == "newer preview"
    assert sessions[0]["archived"]
    assert sessions[0]["runs"] == [{"input": "newer preview"}]
    assert not sessions[1]["archived"]
    assert sessions[1]["preview"] == "older preview"
    assert sessions[0].get("session_type") == "agent"
    assert sessions[1].get("session_type") == "agent"


@pytest.mark.asyncio
async def test_list_sessions_projects_workflow_session_preview_and_type():
    rows = [
        {
            "session_id": "wf-1",
            "created_at": 1,
            "updated_at": 2,
            "user_id": "u1",
            "session_type": "workflow",
            "workflow_id": "w-1",
            "runs": [{"input": {"content": "triage phishing alert"}}],
            "metadata": {},
        },
        {
            "session_id": "wf-2",
            "created_at": 1,
            "updated_at": 1,
            "user_id": "u1",
            "workflow_id": "w-2",
            "runs": [],
            "metadata": {},
        },
    ]

    async def fake_query(**kwargs):
        return rows, 2

    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(chat_session_service, "_query_sessions_page", fake_query),
    ):
        result = await chat_session_service.list_sessions_async(owner_user_id="u1")

    sessions = result["data"]
    assert sessions[0]["session_type"] == "workflow"
    assert sessions[0]["preview"] == "triage phishing alert"
    assert sessions[0]["workflow_id"] == "w-1"
    assert sessions[1]["session_type"] == "workflow"
    assert sessions[1]["preview"] == "工作流运行"
    assert sessions[1]["workflow_id"] == "w-2"



@pytest.mark.asyncio
async def test_list_sessions_filters_archived_by_default():
    async def fake_query(**kwargs):
        assert kwargs["include_archived"] is False
        return [{"session_id": "active", "metadata": {}, "runs": [], "updated_at": 1}], 1

    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(chat_session_service, "_query_sessions_page", fake_query),
    ):
        result = await chat_session_service.list_sessions_async()
    assert [session["session_id"] for session in result["data"]] == ["active"]
    assert result["meta"]["total_count"] == 1



@pytest.mark.asyncio
async def test_list_sessions_paginates_filtered_rows():
    async def fake_query(**kwargs):
        assert kwargs["page"] == 2
        assert kwargs["limit"] == 1
        return [
            {
                "session_id": "s2",
                "created_at": 2,
                "updated_at": 2,
                "user_id": "u1",
                "runs": [],
                "metadata": {},
            }
        ], 3

    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(chat_session_service, "_query_sessions_page", fake_query),
    ):
        result = await chat_session_service.list_sessions_async(
            owner_user_id="u1", page=2, limit=1
        )
    assert [row["session_id"] for row in result["data"]] == ["s2"]
    assert result["meta"] == {
        "page": 2,
        "limit": 1,
        "total_pages": 3,
        "total_count": 3,
        "search_time_ms": 0.0,
    }



@pytest.mark.asyncio
async def test_archive_session_updates_agno_session_metadata():
    session = AgentSession(
        session_id="s1", user_id="u1", metadata={"existing": "value"}
    )
    db = AsyncFakeAgnoDb(
        rows=[], session_row={"session_id": "s1", "user_id": "u1"}, session=session
    )
    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(chat_session_service, "get_async_agno_postgres_db", return_value=db),
        patch.object(chat_session_service, "record_audit_event_async"),
    ):
        archived = await chat_session_service.archive_session("s1", user_id="u1")
    assert archived
    assert db.upserted is session
    metadata = session.metadata
    assert metadata is not None
    assert metadata["existing"] == "value"
    assert metadata["agno_aios_archived"] is True
    assert metadata["agno_aios_archived_by"] == "u1"
    assert metadata["agno_aios_archived_at"]


@pytest.mark.asyncio
async def test_session_history_messages_keep_their_session_id():
    db = AsyncFakeAgnoDb(
        rows=[],
        session_row={
            "session_id": "session-1",
            "runs": [
                {
                    "run_id": "run-1",
                    "input": {"input_content": "Investigate this alert"},
                    "content": "Investigation complete",
                    "status": "completed",
                }
            ],
        },
    )
    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(chat_session_service, "get_async_agno_postgres_db", return_value=db),
    ):
        messages = await chat_session_service.get_session_messages_async("session-1")

    assert [message["session_id"] for message in messages] == ["session-1", "session-1"]


@pytest.mark.asyncio
async def test_session_history_maps_paused_status_and_approval_id():
    db = AsyncFakeAgnoDb(
        rows=[],
        session_row={
            "session_id": "session-1",
            "runs": [
                {
                    "run_id": "run-paused",
                    "input": {"input_content": "simulate block"},
                    "content": "等待管理员审批",
                    "status": "PAUSED",
                    "tools": [
                        {
                            "tool_name": "simulate_containment",
                            "approval_id": "approval-1",
                            "requires_confirmation": True,
                            "confirmed": None,
                        }
                    ],
                },
                {
                    "run_id": "run-done",
                    "input": {"input_content": "simulate block"},
                    "content": "已执行模拟封禁",
                    "status": "COMPLETED",
                    "tools": [
                        {
                            "tool_name": "simulate_containment",
                            "approval_id": "approval-2",
                            "requires_confirmation": True,
                            "confirmed": True,
                        }
                    ],
                },
            ],
        },
    )
    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(chat_session_service, "get_async_agno_postgres_db", return_value=db),
        patch.object(
            chat_session_service,
            "get_chat_settings_async",
            new=AsyncMock(return_value=__import__("types").SimpleNamespace(show_raw_tool_io=False, show_thought_chain=True, show_raw_reasoning=False)),
        ),
    ):
        messages = await chat_session_service.get_session_messages_async("session-1")

    assistant = [message for message in messages if message["role"] == "assistant"]
    assert assistant[0]["status"] == "paused"
    assert assistant[0]["approval_id"] == "approval-1"
    assert assistant[1]["status"] == "completed"


@pytest.mark.asyncio
async def test_session_history_uses_approval_resolution_note_for_full_rejection_reason():
    db = AsyncFakeAgnoDb(
        rows=[],
        session_row={
            "session_id": "session-1",
            "runs": [
                {
                    "run_id": "run-rejected",
                    "input": {"input_content": "simulate block"},
                    "content": "等待管理员审批",
                    "status": "COMPLETED",
                    "metadata": {
                        "approval": {
                            "resolution_data": {
                                "note": "证据不足，暂不封禁该目标，保留观察。"
                            }
                        }
                    },
                    "tools": [
                        {
                            "tool_name": "hitl_simulate_containment",
                            "approval_id": "approval-1",
                            "requires_confirmation": True,
                            "confirmed": False,
                            "confirmation_note": "Tool call was rejected",
                            "tool_args": {"target": "10.0.0.8"},
                        }
                    ],
                }
            ],
        },
    )
    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(chat_session_service, "get_async_agno_postgres_db", return_value=db),
        patch.object(
            chat_session_service,
            "get_chat_settings_async",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    show_raw_tool_io=False,
                    show_thought_chain=True,
                    show_raw_reasoning=False,
                )
            ),
        ),
    ):
        messages = await chat_session_service.get_session_messages_async("session-1")

    assistant = next(message for message in messages if message["role"] == "assistant")
    assert assistant["status"] == "completed"
    assert "证据不足，暂不封禁该目标，保留观察。" in assistant["content"]
    assert [message["id"] for message in messages].count("run-rejected") == 1

@pytest.mark.asyncio
async def test_list_sessions_archived_only_filters_sql():
    async def fake_query(**kwargs):
        assert kwargs["archived_only"] is True
        assert kwargs["include_archived"] is True
        return [
            {
                "session_id": "archived-1",
                "created_at": 2,
                "updated_at": 2,
                "user_id": "u1",
                "runs": [],
                "metadata": {"agno_aios_archived": True},
            }
        ], 1

    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(chat_session_service, "_query_sessions_page", fake_query),
    ):
        result = await chat_session_service.list_sessions_async(
            archived_only=True, owner_user_id="u1"
        )
    assert [row["session_id"] for row in result["data"]] == ["archived-1"]
    assert result["data"][0]["archived"] is True
    assert result["meta"]["total_count"] == 1



@pytest.mark.asyncio
async def test_list_sessions_forwards_q():
    captured: dict = {}

    async def fake_query(**kwargs):
        captured.update(kwargs)
        return [], 0

    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(chat_session_service, "_query_sessions_page", fake_query),
    ):
        await chat_session_service.list_sessions_async(q="risk")
    assert captured["q"] == "risk"


@pytest.mark.asyncio
async def test_session_history_projects_lean_mode_and_skill_names():
    db = AsyncFakeAgnoDb(
        rows=[],
        session_row={
            "session_id": "session-1",
            "runs": [
                {
                    "run_id": "run-lean",
                    "input": {"input_content": "ping"},
                    "content": "pong",
                    "status": "COMPLETED",
                    "metadata": {
                        "tais_runtime": {
                            "version": 1,
                            "enable_tools": True,
                            "skill_names": [],
                        }
                    },
                },
                {
                    "run_id": "run-skills",
                    "input": {"input_content": "CVE-2024-1234"},
                    "content": "analysis",
                    "status": "COMPLETED",
                    "metadata": {
                        "tais_runtime": {
                            "version": 1,
                            "enable_tools": True,
                            "skill_names": ["cve-intel-skill"],
                        }
                    },
                },
                {
                    "run_id": "run-all",
                    "input": {"input_content": "full security ops"},
                    "content": "report",
                    "status": "COMPLETED",
                    "metadata": {
                        "tais_runtime": {
                            "version": 1,
                            "enable_tools": True,
                            "skill_names": None,
                        }
                    },
                },
                {
                    "run_id": "run-tools-off",
                    "input": {"input_content": "hello"},
                    "content": "hi",
                    "status": "COMPLETED",
                    "metadata": {
                        "tais_runtime": {
                            "version": 1,
                            "enable_tools": False,
                            "skill_names": [],
                        }
                    },
                },
            ],
        },
    )
    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(chat_session_service, "get_async_agno_postgres_db", return_value=db),
        patch.object(
            chat_session_service,
            "get_chat_settings_async",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    show_raw_tool_io=False,
                    show_thought_chain=False,
                    show_raw_reasoning=False,
                )
            ),
        ),
    ):
        messages = await chat_session_service.get_session_messages_async("session-1")

    assistants = {message["run_id"]: message for message in messages if message["role"] == "assistant"}
    assert assistants["run-lean"]["enable_tools"] is True
    assert assistants["run-lean"]["lean_mode"] is True
    assert assistants["run-lean"]["skill_names"] == []
    assert assistants["run-lean"]["search_knowledge"] is False
    assert assistants["run-skills"]["enable_tools"] is True
    assert assistants["run-skills"]["lean_mode"] is False
    assert assistants["run-skills"]["skill_names"] == ["cve-intel-skill"]
    assert assistants["run-skills"]["search_knowledge"] is True
    assert assistants["run-all"]["enable_tools"] is True
    assert assistants["run-all"]["lean_mode"] is False
    assert assistants["run-all"]["skill_names"] is None
    assert assistants["run-all"]["search_knowledge"] is True
    assert assistants["run-tools-off"]["enable_tools"] is False
    assert assistants["run-tools-off"]["lean_mode"] is False
    assert assistants["run-tools-off"]["skill_names"] == []
    assert assistants["run-tools-off"]["search_knowledge"] is False



@pytest.mark.asyncio
async def test_unarchive_session_clears_flags():
    from unittest.mock import AsyncMock, MagicMock, patch

    session = MagicMock()
    session.metadata = {
        "agno_aios_archived": True,
        "agno_aios_archived_by": "u1",
        "agno_aios_archived_at": "2020-01-01T00:00:00+00:00",
        "title": "keep-me",
    }
    db = MagicMock()
    db.get_session = AsyncMock(
        side_effect=[
            {"session_id": "s1", "user_id": "u1"},
            session,
        ]
    )
    db.upsert_session = AsyncMock()
    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async", new_callable=AsyncMock),
        patch.object(chat_session_service, "get_async_agno_postgres_db", return_value=db),
    ):
        ok = await chat_session_service.unarchive_session("s1", user_id="u1")
    assert ok
    db.upsert_session.assert_awaited()
    metadata = session.metadata
    assert metadata.get("agno_aios_archived") is False
    assert "agno_aios_archived_by" not in metadata
    assert "agno_aios_archived_at" not in metadata
    assert metadata.get("title") == "keep-me"


@pytest.mark.asyncio
async def test_get_session_summary_projects_list_fields():
    row = {
        "session_id": "wf-deep",
        "user_id": "u1",
        "session_type": "workflow",
        "workflow_id": "flow-9",
        "agent_id": None,
        "team_id": None,
        "created_at": 10,
        "updated_at": 20,
        "runs": [{"input": "triage alert"}],
        "metadata": {"agno_aios_title": "IR 分诊"},
    }
    db = AsyncFakeAgnoDb(rows=[], session_row=row)
    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(chat_session_service, "get_async_agno_postgres_db", return_value=db),
    ):
        summary = await chat_session_service.get_session_summary_async("wf-deep")
    assert summary is not None
    assert summary["session_id"] == "wf-deep"
    assert summary["session_type"] == "workflow"
    assert summary["workflow_id"] == "flow-9"
    assert summary["title"] == "IR 分诊"
    assert summary["preview"] == "triage alert"


@pytest.mark.asyncio
async def test_get_session_summary_returns_none_when_missing():
    db = AsyncFakeAgnoDb(rows=[], session_row=None)
    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(chat_session_service, "get_async_agno_postgres_db", return_value=db),
    ):
        assert await chat_session_service.get_session_summary_async("missing") is None


@pytest.mark.asyncio
async def test_team_history_projects_member_thoughts_and_tools(monkeypatch):
    """Team runs store member_responses; history should expose thought_chain + member tools."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import api.services.chat_session_service as chat_session_service

    team_run = {
        "run_id": "team-run-h1",
        "team_id": "research-analysis-team",
        "status": "COMPLETED",
        "content": "队长综合结论",
        "input": "调研并核算",
        "tools": [],
        "member_responses": [
            {
                "run_id": "member-1",
                "agent_id": "deep-research",
                "agent_name": "深度研究助手",
                "status": "COMPLETED",
                "content": "调研摘要",
                "tools": [
                    {
                        "tool_call_id": "t1",
                        "tool_name": "read_url",
                        "result": "ok",
                    }
                ],
            },
            {
                "run_id": "member-2",
                "agent_id": "data-analysis",
                "agent_name": "数据分析助手",
                "status": "COMPLETED",
                "content": "指标 42",
                "tools": [],
            },
        ],
        "metrics": {"total_tokens": 12},
        "citations": [],
        "followups": [],
        "metadata": {},
    }

    class FakeDb:
        async def get_session(self, session_id, deserialize=False):
            return {
                "session_id": session_id,
                "user_id": "u1",
                "session_type": "team",
                "team_id": "research-analysis-team",
                "runs": [team_run],
            }

    monkeypatch.setattr(
        chat_session_service,
        "ensure_agno_postgres_tables_async",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        chat_session_service,
        "get_async_agno_postgres_db",
        lambda: FakeDb(),
    )
    monkeypatch.setattr(
        chat_session_service,
        "get_chat_settings_async",
        AsyncMock(
            return_value=SimpleNamespace(
                show_raw_tool_io=False,
                show_thought_chain=True,
                show_raw_reasoning=False,
            )
        ),
    )

    messages = await chat_session_service.get_session_messages_async("session-team")
    assistant = next(m for m in messages if m.get("role") == "assistant")
    assert assistant["content"] == "队长综合结论"
    thoughts = assistant.get("thought_chain") or []
    assert {t["id"] for t in thoughts} >= {
        "member:deep-research",
        "member:data-analysis",
    }
    tools = assistant.get("tools") or []
    assert any(
        str(t.get("id", "")).startswith("member:deep-research:")
        and str(t.get("name", "")).startswith("[深度研究助手]")
        for t in tools
    )


@pytest.mark.asyncio
async def test_team_history_skips_child_member_runs(monkeypatch):
    """Member agent runs stored with parent_run_id must not become extra chat turns."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import api.services.chat_session_service as chat_session_service

    leader_run = {
        "run_id": "team-leader-1",
        "team_id": "research-analysis-team",
        "status": "COMPLETED",
        "content": "56",
        "input": "请委派 data-analysis 计算 7*8",
        "tools": [{"tool_call_id": "d1", "tool_name": "delegate_task_to_member", "result": "56"}],
        "member_responses": [
            {
                "run_id": "member-1",
                "agent_id": "data-analysis",
                "agent_name": "数据分析助手",
                "status": "COMPLETED",
                "content": "56",
                "tools": [{"tool_call_id": "t1", "tool_name": "multiply", "result": "56"}],
            }
        ],
        "metrics": {},
        "citations": [],
        "followups": [],
        "metadata": {},
    }
    member_run = {
        "run_id": "member-1",
        "agent_id": "data-analysis",
        "agent_name": "数据分析助手",
        "parent_run_id": "team-leader-1",
        "status": "COMPLETED",
        "content": "56",
        "input": "计算 7*8，只返回计算结果数字。",
        "tools": [{"tool_call_id": "t1", "tool_name": "multiply", "result": "56"}],
        "metrics": {},
        "metadata": {},
    }

    class FakeDb:
        async def get_session(self, session_id, deserialize=False):
            return {
                "session_id": session_id,
                "user_id": "u1",
                "session_type": "team",
                "team_id": "research-analysis-team",
                "runs": [member_run, leader_run],
            }

    monkeypatch.setattr(
        chat_session_service,
        "ensure_agno_postgres_tables_async",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        chat_session_service,
        "get_async_agno_postgres_db",
        lambda: FakeDb(),
    )
    monkeypatch.setattr(
        chat_session_service,
        "get_chat_settings_async",
        AsyncMock(
            return_value=SimpleNamespace(
                show_raw_tool_io=False,
                show_thought_chain=True,
                show_raw_reasoning=False,
            )
        ),
    )

    messages = await chat_session_service.get_session_messages_async("session-team")
    users = [m for m in messages if m.get("role") == "user"]
    assistants = [m for m in messages if m.get("role") == "assistant"]
    assert len(users) == 1
    assert len(assistants) == 1
    assert assistants[0]["run_id"] == "team-leader-1"
    assert any(
        str(t.get("id", "")).startswith("member:data-analysis:")
        for t in (assistants[0].get("tools") or [])
    )


def test_team_history_reconstructs_members_from_child_runs():
    from api.services.chat_session_service import (
        _history_team_thoughts,
        _history_team_tools,
        _member_rows,
    )

    leader = {
        "run_id": "leader-1",
        "team_id": "research-analysis-team",
        "content": "42",
        "tools": [{"tool_name": "delegate_task_to_member", "tool_call_id": "d1", "result": "42"}],
        "member_responses": None,
    }
    child = {
        "run_id": "child-1",
        "parent_run_id": "leader-1",
        "agent_id": "data-analysis",
        "agent_name": "数据分析助手",
        "content": "42",
        "status": "COMPLETED",
        "tools": [{"tool_name": "multiply", "tool_call_id": "m1", "result": "42"}],
    }
    members = _member_rows(leader, sibling_runs=[leader, child])
    assert len(members) == 1
    assert members[0]["agent_id"] == "data-analysis"
    tools = _history_team_tools(
        leader, tool_status="completed", include_raw_io=True, sibling_runs=[leader, child]
    )
    names = [row["name"] for row in tools]
    assert "delegate_task_to_member" in names
    assert any("multiply" in n for n in names)
    thoughts = _history_team_thoughts(
        leader, tool_status="completed", sibling_runs=[leader, child]
    )
    assert thoughts and thoughts[0]["id"] == "member:data-analysis"


def test_preview_prefers_latest_run():
    from api.services.chat_session_service import _preview_from_runs

    assert _preview_from_runs(
        [
            {"input": "first turn"},
            {"input": "latest turn"},
        ]
    ) == "latest turn"
    # Skip non-dict tails
    assert _preview_from_runs([{"input": "only"}, "bad"]) == "only"


@pytest.mark.asyncio
async def test_team_history_omits_tools_when_thought_chain_disabled(monkeypatch):
    """show_thought_chain=false omits timeline tools + member thoughts (product setting)."""
    from api.services import chat_session_service as svc

    leader = {
        "run_id": "leader-tools",
        "team_id": "research-analysis-team",
        "status": "COMPLETED",
        "content": "81",
        "tools": [
            {"tool_call_id": "d1", "tool_name": "delegate_task_to_member", "result": "81"},
        ],
        "member_responses": [
            {
                "agent_id": "data-analysis",
                "agent_name": "数据分析助手",
                "content": "81",
                "status": "completed",
                "tools": [
                    {"tool_call_id": "m1", "tool_name": "multiply", "result": "81"},
                ],
            }
        ],
    }
    db = AsyncFakeAgnoDb(
        rows=[],
        session_row={"session_id": "s-team-tools", "user_id": "u1", "runs": [leader]},
    )
    monkeypatch.setattr(svc, "get_async_agno_postgres_db", lambda: db)
    monkeypatch.setattr(svc, "ensure_agno_postgres_tables_async", AsyncMock())
    monkeypatch.setattr(
        svc,
        "get_chat_settings_async",
        AsyncMock(
            return_value=__import__("types").SimpleNamespace(
                show_raw_tool_io=False,
                show_thought_chain=False,
                show_raw_reasoning=False,
            )
        ),
    )
    messages = await svc.get_session_messages_async("s-team-tools")
    assistant = next(m for m in messages if m.get("role") == "assistant")
    assert (assistant.get("tools") or []) == []
    assert not assistant.get("thought_chain")
    assert assistant.get("content") == "81"



def test_history_member_content_fallback():
    from api.services.chat_session_service import _history_member_content_fallback

    run = {
        "run_id": "L",
        "content": "",
        "member_responses": [
            {"agent_id": "a", "content": "first"},
            {"agent_id": "b", "content": "last-member"},
        ],
    }
    assert _history_member_content_fallback(run) == "last-member"


@pytest.mark.asyncio
async def test_team_history_merges_member_sources(monkeypatch):
    """History should surface member citations with member name prefix (stream parity)."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    import api.services.chat_session_service as chat_session_service

    team_run = {
        "run_id": "team-run-src",
        "team_id": "research-analysis-team",
        "status": "COMPLETED",
        "content": "综合",
        "input": "调研",
        "tools": [],
        "member_responses": [
            {
                "run_id": "m1",
                "agent_id": "deep-research",
                "agent_name": "深度研究助手",
                "status": "COMPLETED",
                "content": "调研摘要",
                "citations": [{"title": "Report", "url": "https://example.com/r"}],
                "tools": [],
            }
        ],
        "metrics": {},
        "citations": [{"title": "Leader note", "url": "https://example.com/leader"}],
        "followups": [],
        "metadata": {},
    }

    class FakeDb:
        async def get_session(self, session_id, deserialize=False):
            return {
                "session_id": session_id,
                "user_id": "u1",
                "session_type": "team",
                "team_id": "research-analysis-team",
                "runs": [team_run],
            }

    monkeypatch.setattr(
        chat_session_service,
        "ensure_agno_postgres_tables_async",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        chat_session_service,
        "get_async_agno_postgres_db",
        lambda: FakeDb(),
    )
    monkeypatch.setattr(
        chat_session_service,
        "get_chat_settings_async",
        AsyncMock(
            return_value=SimpleNamespace(
                show_raw_tool_io=False,
                show_thought_chain=True,
                show_raw_reasoning=False,
            )
        ),
    )

    messages = await chat_session_service.get_session_messages_async("session-team-src")
    assistant = next(m for m in messages if m.get("role") == "assistant")
    sources = assistant.get("sources") or []
    titles = [str(s.get("title") or "") for s in sources]
    assert any("Leader note" in t for t in titles), titles
    assert any("深度研究助手" in t and "Report" in t for t in titles), titles
