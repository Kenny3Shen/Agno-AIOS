from agno.tracing import setup_tracing
from api.services.chat_session_service import (
    archive_session as archive_session,
    get_all_sessions_async as get_all_sessions_async,
    get_session_messages_async as get_session_messages_async,
    get_session_owner_async as get_session_owner_async,
    is_session_archived_async as is_session_archived_async,
)
from api.services.postgres_store import (
    get_async_agno_postgres_db,
)
from api.services.security_run_runtime import (
    _is_provider_block_error as _is_provider_block_error,
    stream_chat_with_agent as stream_chat_with_agent,
)

# Set up database for traces
db = get_async_agno_postgres_db()
# Enable tracing (call once at startup)
setup_tracing(db=db, batch_processing=False)
