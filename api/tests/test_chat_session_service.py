"""Critical chat session service business tests."""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from agno.session.agent import AgentSession
import pytest
from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.dialects.postgresql import JSONB, dialect

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
        return [
            {"session_id": "active", "metadata": {}, "runs": [], "updated_at": 1}
        ], 1

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
        patch.object(
            chat_session_service, "get_async_agno_postgres_db", return_value=db
        ),
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
            chat_session_service,
            "ensure_agno_postgres_tables_async",
            new_callable=AsyncMock,
        ),
        patch.object(
            chat_session_service, "get_async_agno_postgres_db", return_value=db
        ),
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
        patch.object(
            chat_session_service, "get_async_agno_postgres_db", return_value=db
        ),
    ):
        messages = await chat_session_service.get_session_messages_async("session-1")

    assert [message["session_id"] for message in messages] == ["session-1", "session-1"]


@pytest.mark.asyncio
async def test_session_history_returns_recent_turn_windows_without_splitting_pairs():
    runs = [
        {
            "run_id": f"run-{index}",
            "input": {"input_content": f"question-{index}"},
            "content": f"answer-{index}",
            "status": "COMPLETED",
        }
        for index in range(1, 6)
    ]
    db = AsyncFakeAgnoDb(
        rows=[],
        session_row={"session_id": "session-1", "runs": runs},
    )
    chat_settings = SimpleNamespace(
        show_raw_tool_io=False,
        show_thought_chain=True,
        show_raw_reasoning=False,
    )
    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(
            chat_session_service, "get_async_agno_postgres_db", return_value=db
        ),
        patch.object(
            chat_session_service,
            "get_chat_settings_async",
            new=AsyncMock(return_value=chat_settings),
        ),
    ):
        newest = await chat_session_service.get_session_messages_page_async(
            "session-1",
            limit=2,
        )
        middle = await chat_session_service.get_session_messages_page_async(
            "session-1",
            before="turn:3",
            limit=2,
        )
        oldest = await chat_session_service.get_session_messages_page_async(
            "session-1",
            before="turn:1",
            limit=2,
        )

    assert [message["id"] for message in newest["data"]] == [
        "history-3:run-4:user",
        "history-3:run-4",
        "history-4:run-5:user",
        "history-4:run-5",
    ]
    assert newest["meta"] == {
        "limit": 2,
        "has_more": True,
        "next_cursor": "turn:3",
        "total_runs": 5,
    }
    assert [message["id"] for message in middle["data"]] == [
        "history-1:run-2:user",
        "history-1:run-2",
        "history-2:run-3:user",
        "history-2:run-3",
    ]
    assert middle["meta"]["next_cursor"] == "turn:1"
    assert [message["id"] for message in oldest["data"]] == [
        "history-0:run-1:user",
        "history-0:run-1",
    ]
    assert oldest["meta"]["has_more"] is False
    assert oldest["meta"]["next_cursor"] is None


@pytest.mark.asyncio
async def test_session_history_duplicate_run_ids_use_ordinal_cursors_without_skipping_turns():
    """An imported duplicate run id must not make the next page jump backwards."""
    runs = [
        {
            "run_id": run_id,
            "input": {"input_content": f"question-{index}"},
            "content": f"answer-{index}",
            "status": "COMPLETED",
        }
        for index, run_id in enumerate(("a", "dup", "b", "dup", "c"))
    ]
    db = AsyncFakeAgnoDb(
        rows=[],
        session_row={"session_id": "session-1", "runs": runs},
    )
    settings = SimpleNamespace(
        show_raw_tool_io=False,
        show_thought_chain=True,
        show_raw_reasoning=False,
    )
    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(
            chat_session_service, "get_async_agno_postgres_db", return_value=db
        ),
        patch.object(
            chat_session_service,
            "get_chat_settings_async",
            new=AsyncMock(return_value=settings),
        ),
    ):
        newest = await chat_session_service.get_session_messages_page_async(
            "session-1", limit=2
        )
        middle = await chat_session_service.get_session_messages_page_async(
            "session-1", before="turn:3", limit=2
        )
        oldest = await chat_session_service.get_session_messages_page_async(
            "session-1", before="turn:1", limit=2
        )

    assert newest["meta"]["next_cursor"] == "turn:3"
    assert [
        message["run_id"]
        for message in middle["data"]
        if message["role"] == "assistant"
    ] == [
        "dup",
        "b",
    ]
    assert middle["meta"]["next_cursor"] == "turn:1"
    assert [
        message["run_id"]
        for message in oldest["data"]
        if message["role"] == "assistant"
    ] == ["a"]
    assert len({message["id"] for message in newest["data"] + middle["data"]}) == len(
        newest["data"] + middle["data"]
    )


def test_history_page_sibling_runs_omit_ambiguous_duplicate_leader_children():
    """Child rows cannot be safely reconstructed when a leader id repeats."""
    first_leader = {"run_id": "duplicate"}
    second_leader = {"run_id": "duplicate"}
    children = [
        {"run_id": "member-1", "parent_run_id": "duplicate", "content": "first"},
        {"run_id": "member-2", "parent_run_id": "duplicate", "content": "second"},
    ]

    sibling_runs = chat_session_service._history_page_sibling_runs(
        [first_leader, children[0], second_leader, children[1]],
        [(0, first_leader)],
    )

    assert sibling_runs == []


@pytest.mark.asyncio
async def test_session_history_rejects_unknown_page_cursor():
    db = AsyncFakeAgnoDb(
        rows=[],
        session_row={
            "session_id": "session-1",
            "runs": [
                {
                    "run_id": "run-1",
                    "input": {"input_content": "question"},
                    "content": "answer",
                    "status": "COMPLETED",
                }
            ],
        },
    )
    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(
            chat_session_service, "get_async_agno_postgres_db", return_value=db
        ),
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
        with pytest.raises(ValueError, match="cursor"):
            await chat_session_service.get_session_messages_page_async(
                "session-1",
                before="not-a-cursor",
                limit=2,
            )


@pytest.mark.asyncio
async def test_session_history_page_uses_jsonb_window_query_when_sqlalchemy_db_is_available():
    table = Table(
        "agno_sessions",
        MetaData(),
        Column("session_id", String),
        Column("user_id", String),
        Column("runs", JSONB),
    )
    captured: dict[str, Any] = {}
    rows = [
        {
            "user_id": "u1",
            "runs_type": "array",
            "run": {
                "run_id": "run-4",
                "input": {"input_content": "question-4"},
                "content": "answer-4",
                "status": "COMPLETED",
            },
            "run_index": 3,
            "is_leader": True,
            "total_runs": 5,
            "eligible_runs": 5,
            "cursor_matches": 0,
        },
        {
            "user_id": "u1",
            "runs_type": "array",
            "run": {
                "run_id": "run-5",
                "input": {"input_content": "question-5"},
                "content": "answer-5",
                "status": "COMPLETED",
            },
            "run_index": 4,
            "is_leader": True,
            "total_runs": 5,
            "eligible_runs": 5,
            "cursor_matches": 0,
        },
    ]

    class PageSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, statement, parameters):
            captured["statement"] = statement
            captured["parameters"] = parameters

            class Result:
                def mappings(self):
                    return rows

            return Result()

    class SqlPageDb:
        _get_table = AsyncMock(return_value=table)
        get_session = AsyncMock(
            side_effect=AssertionError("paged read must not load full runs")
        )

        @staticmethod
        def async_session_factory():
            return PageSession()

    db = SqlPageDb()
    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(
            chat_session_service, "get_async_agno_postgres_db", return_value=db
        ),
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
        result = await chat_session_service.get_session_messages_page_async(
            "session-1",
            limit=2,
            actor=SimpleNamespace(id="u1", role="user", is_superuser=False),
        )

    assert [message["id"] for message in result["data"]] == [
        "history-3:run-4:user",
        "history-3:run-4",
        "history-4:run-5:user",
        "history-4:run-5",
    ]
    assert result["meta"] == {
        "limit": 2,
        "has_more": True,
        "next_cursor": "turn:3",
        "total_runs": 5,
    }
    assert captured["parameters"] == {
        "history_session_id": "session-1",
        "history_before": "",
        "history_limit": 2,
        "history_owner_user_id": "u1",
    }
    compiled = str(captured["statement"].compile(dialect=dialect()))
    assert "jsonb_array_elements" in compiled
    assert "history_unique_selected_parent_ids" in compiled
    db.get_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_paged_history_falls_back_for_legacy_json_string_runs():
    table = Table(
        "agno_sessions",
        MetaData(),
        Column("session_id", String),
        Column("user_id", String),
        Column("runs", JSONB),
    )
    legacy_runs = [
        {
            "run_id": "run-1",
            "input": {"input_content": "question"},
            "content": "answer",
            "status": "COMPLETED",
        }
    ]

    class PageSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def execute(self, _statement, _parameters):
            class Result:
                def mappings(self):
                    return [
                        {
                            "user_id": "u1",
                            "runs_type": "string",
                            "run": None,
                            "run_index": None,
                            "is_leader": None,
                            "total_runs": 0,
                            "eligible_runs": 0,
                            "cursor_matches": 0,
                        }
                    ]

            return Result()

    class LegacyStringRunsDb:
        _get_table = AsyncMock(return_value=table)
        get_session = AsyncMock(
            return_value={
                "session_id": "session-1",
                "user_id": "u1",
                "runs": json.dumps(legacy_runs),
            }
        )

        @staticmethod
        def async_session_factory():
            return PageSession()

    db = LegacyStringRunsDb()
    with (
        patch.object(chat_session_service, "ensure_agno_postgres_tables_async"),
        patch.object(
            chat_session_service, "get_async_agno_postgres_db", return_value=db
        ),
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
        result = await chat_session_service.get_session_messages_page_async(
            "session-1", limit=2
        )

    assert [message["id"] for message in result["data"]] == [
        "history-0:run-1:user",
        "history-0:run-1",
    ]
    assert result["meta"]["total_runs"] == 1
    db.get_session.assert_awaited_once_with("session-1", deserialize=False)


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
        patch.object(
            chat_session_service, "get_async_agno_postgres_db", return_value=db
        ),
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
