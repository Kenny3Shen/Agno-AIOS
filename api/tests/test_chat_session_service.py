"""Critical chat session service business tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from agno.session.agent import AgentSession
import pytest

from api.services import chat_session_service


class AsyncFakeAgnoDb:
    def __init__(
        self,
        rows: list[dict] | None = None,
        session_row: dict | None = None,
        session: AgentSession | None = None,
    ):
        self.rows = rows or []
        self.session_row = session_row
        self.session = session
        self.get_sessions_kwargs = None
        self.upserted = None

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

    async def _get_table(self, **_kwargs):
        return None


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
async def test_unarchive_session_clears_flags():
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
        patch.object(
            chat_session_service, "ensure_agno_postgres_tables_async", new_callable=AsyncMock
        ),
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

    assistant = [message for message in messages if message["role"] == "assistant"]
    assert assistant[0]["status"] == "paused"
    assert assistant[0]["approval_id"] == "approval-1"
    assert assistant[1]["status"] == "completed"


@pytest.mark.asyncio
async def test_team_history_skips_child_member_runs(monkeypatch):
    """Member agent runs stored with parent_run_id must not become extra chat turns."""
    leader_run = {
        "run_id": "team-leader-1",
        "team_id": "research-analysis-team",
        "status": "COMPLETED",
        "content": "56",
        "input": "请委派 data-analysis 计算 7*8",
        "tools": [
            {
                "tool_call_id": "d1",
                "tool_name": "delegate_task_to_member",
                "result": "56",
            }
        ],
        "member_responses": [
            {
                "run_id": "member-1",
                "agent_id": "data-analysis",
                "agent_name": "数据分析助手",
                "status": "COMPLETED",
                "content": "56",
                "tools": [
                    {"tool_call_id": "t1", "tool_name": "multiply", "result": "56"}
                ],
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
