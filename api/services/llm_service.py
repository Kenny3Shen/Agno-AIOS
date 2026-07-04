import os
from dotenv import load_dotenv
from agno.tracing import setup_tracing
from api.services.chat_session_service import (
    archive_session as archive_session,
    get_all_sessions as get_all_sessions,
    get_session_messages as get_session_messages,
    get_session_owner as get_session_owner,
    is_session_archived as is_session_archived,
)
from api.services.postgres_store import (
    get_agno_postgres_db,
)
from api.services.security_run_runtime import (
    _build_fallback_agent as _build_fallback_agent,
    _is_provider_block_error as _is_provider_block_error,
    stream_chat_with_agent as stream_chat_with_agent,
)

load_dotenv(override=True)
# Set up database for traces
db = get_agno_postgres_db()
# Enable tracing (call once at startup)
setup_tracing(db=db, batch_processing=False)


def _get_env(key: str, default: str = "") -> str:
    """优先从 os.environ 读取（支持运行时动态修改），回退到默认值"""
    return os.environ.get(key, default)
