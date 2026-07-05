import inspect
from api.routes import chat
from api.services import llm_service


def test_chat_route_uses_archive_service_for_delete_endpoint():
    source = inspect.getsource(chat.remove_session)
    assert "archive_session" in source
    assert "delete_session(" not in source


def test_session_service_exposes_archive_without_hiding_trace_data():
    assert hasattr(llm_service, "archive_session")
    assert hasattr(llm_service, "is_session_archived_async")
    assert not hasattr(llm_service, "ensure_chat_session_archive_table")
    signature = inspect.signature(llm_service.get_all_sessions_async)
    assert "include_archived" in signature.parameters
    archive_source = inspect.getsource(llm_service.archive_session)
    assert "delete_session" not in archive_source
    assert "upsert_session" in archive_source
    assert "chat_session_archives" not in archive_source
