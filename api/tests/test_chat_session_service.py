from unittest.mock import patch
from agno.session.agent import AgentSession
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


def test_get_all_sessions_projects_sorted_archived_session_rows():
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
    db = FakeAgnoDb(rows)
    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables"),
        patch.object(chat_session_service, "get_agno_postgres_db", return_value=db),
    ):
        sessions = chat_session_service.get_all_sessions(
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


def test_get_all_sessions_filters_archived_by_default():
    db = FakeAgnoDb(
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
        patch.object(chat_session_service, "ensure_agno_postgres_tables"),
        patch.object(chat_session_service, "get_agno_postgres_db", return_value=db),
    ):
        sessions = chat_session_service.get_all_sessions()
    assert [session["session_id"] for session in sessions] == ["active"]


def test_archive_session_updates_agno_session_metadata():
    session = AgentSession(
        session_id="s1", user_id="u1", metadata={"existing": "value"}
    )
    db = FakeAgnoDb(
        rows=[], session_row={"session_id": "s1", "user_id": "u1"}, session=session
    )
    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables"),
        patch.object(chat_session_service, "get_agno_postgres_db", return_value=db),
        patch.object(chat_session_service, "record_audit_event"),
    ):
        archived = chat_session_service.archive_session("s1", user_id="u1")
    assert archived
    assert db.upserted is session
    metadata = session.metadata
    assert metadata is not None
    assert metadata["existing"] == "value"
    assert metadata["agno_aios_archived"] is True
    assert metadata["agno_aios_archived_by"] == "u1"
    assert metadata["agno_aios_archived_at"]
