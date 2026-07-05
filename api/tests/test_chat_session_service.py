from unittest.mock import patch

from agno.session.agent import AgentSession
import pytest

from api.services import chat_session_service


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


@pytest.mark.asyncio
async def test_get_all_sessions_projects_sorted_archived_session_rows():
    rows = [
        {
            "session_id": "older",
            "created_at": 1,
            "updated_at": 2,
            "user_id": "u1",
            "runs": [{"input": {"input_content": "older preview"}}],
            "metadata": {},
        },
        {
            "session_id": "newer",
            "created_at": 3,
            "updated_at": 4,
            "user_id": "u1",
            "runs": [{"input": "newer preview"}],
            "metadata": {"agno_aios_archived": True},
        },
    ]
    db = AsyncFakeAgnoDb(rows)
    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(chat_session_service, "get_async_agno_postgres_db", return_value=db),
    ):
        sessions = await chat_session_service.get_all_sessions_async(
            include_archived=True, owner_user_id="u1", include_runs=True
        )
    kwargs = db.get_sessions_kwargs
    assert kwargs is not None
    assert kwargs["user_id"] == "u1"
    assert kwargs["limit"] == 500
    assert not kwargs["deserialize"]
    assert [session["session_id"] for session in sessions] == ["newer", "older"]
    assert sessions[0]["preview"] == "newer preview"
    assert sessions[0]["archived"]
    assert sessions[0]["runs"] == [{"input": "newer preview"}]
    assert not sessions[1]["archived"]
    assert sessions[1]["preview"] == "older preview"


@pytest.mark.asyncio
async def test_get_all_sessions_async_projects_sorted_archived_session_rows():
    rows = [
        {
            "session_id": "older",
            "created_at": 1,
            "updated_at": 2,
            "user_id": "u1",
            "runs": [{"input": {"input_content": "older preview"}}],
            "metadata": {},
        },
        {
            "session_id": "newer",
            "created_at": 3,
            "updated_at": 4,
            "user_id": "u1",
            "runs": [{"input": "newer preview"}],
            "metadata": {"agno_aios_archived": True},
        },
    ]
    db = AsyncFakeAgnoDb(rows)
    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(chat_session_service, "get_async_agno_postgres_db", return_value=db),
    ):
        sessions = await chat_session_service.get_all_sessions_async(
            include_archived=True, owner_user_id="u1", include_runs=True
        )
    kwargs = db.get_sessions_kwargs
    assert kwargs is not None
    assert kwargs["user_id"] == "u1"
    assert kwargs["limit"] == 500
    assert not kwargs["deserialize"]
    assert [session["session_id"] for session in sessions] == ["newer", "older"]
    assert sessions[0]["preview"] == "newer preview"
    assert sessions[0]["archived"]
    assert sessions[0]["runs"] == [{"input": "newer preview"}]
    assert not sessions[1]["archived"]
    assert sessions[1]["preview"] == "older preview"


@pytest.mark.asyncio
async def test_get_all_sessions_filters_archived_by_default():
    db = AsyncFakeAgnoDb(
        [
            {"session_id": "active", "metadata": {}, "runs": []},
            {
                "session_id": "archived",
                "metadata": {"agno_aios_archived": True},
                "runs": [],
            },
        ]
    )
    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(chat_session_service, "get_async_agno_postgres_db", return_value=db),
    ):
        sessions = await chat_session_service.get_all_sessions_async()
    assert [session["session_id"] for session in sessions] == ["active"]


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
