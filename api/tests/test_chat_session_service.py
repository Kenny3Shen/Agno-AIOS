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
