import inspect
from pathlib import Path
from typing import Any, cast

import pytest

from api.auth import database as auth_database
from api.persistence import audit_logs
from api.persistence.audit_logs import audit_logs_table
from api.persistence import database
from api.persistence.mcp import (
    _token_insert_values,
    mcp_tokens_table,
)
from api.mcp import config as mcp_config
from api.mcp.tools import basic as basic_mcp_tool
from api.mcp.tools import playbook as playbook_mcp_tool
from api.routes import settings as settings_route
from api.routes import skills as skills_route
from api.mcp import server as mcp_server
from api.services import audit_service
from api.services import mcp_config_service
from api.services import model_config_service
from api.services import os_evaluation_control, os_metrics_control, postgres_store, tracing_service
from api.services import knowledge_service
from api.services import security_run_runtime
from api.services import skill_service
from api.core import logging as core_logging
from api.tasks import update_cve
from api.tasks import cve_sources
import api.main as api_main


def test_app_table_bootstrap_no_longer_creates_audit_logs_with_raw_sql() -> None:
    assert not hasattr(postgres_store, "ensure_app_tables")
    assert not hasattr(postgres_store, "postgres_connect")
    assert not hasattr(postgres_store, "get_agno_postgres_db")
    assert not hasattr(postgres_store, "get_knowledge_postgres_db")
    source = inspect.getsource(postgres_store.ensure_app_tables_async)
    assert "idx_audit_logs" not in source
    assert "actor_user_id TEXT NOT NULL" not in source


def test_agent_evals_router_is_included() -> None:
    main_source = inspect.getsource(api_main)
    assert "agent_evals" in main_source
    assert "app.include_router(agent_evals.router)" in main_source


def test_audit_log_metadata_uses_jsonb_default_in_sqlalchemy_table() -> None:
    metadata_column = audit_logs_table().c.metadata
    server_default = metadata_column.server_default
    assert server_default is not None
    default_arg = cast(Any, server_default).arg
    assert metadata_column.type.__class__.__name__ == "JSONB"
    assert str(default_arg) == "'{}'::jsonb"


def test_async_control_plane_engine_uses_async_psycopg_driver() -> None:
    assert database._async_sqlalchemy_url().startswith("postgresql+psycopg_async://")
    assert not hasattr(database, "get_control_plane_engine")
    assert not hasattr(database, "dispose_control_plane_engine")


def test_auth_database_uses_async_psycopg_driver() -> None:
    source = inspect.getsource(auth_database)
    assert "postgres_async_sqlalchemy_url" in source
    assert "create_async_engine(settings.postgres_sqlalchemy_url" not in source


def test_audit_persistence_no_longer_exposes_sync_wrappers() -> None:
    assert not hasattr(audit_logs, "ensure_audit_logs_table")
    assert not hasattr(audit_logs, "insert_audit_log")
    assert not hasattr(audit_logs, "list_audit_logs")
    assert not hasattr(audit_service, "ensure_audit_log_table")
    assert not hasattr(audit_service, "record_audit_event")
    assert not hasattr(audit_service, "list_audit_events")


def test_mcp_config_no_longer_uses_raw_sql_for_runtime_tables() -> None:
    source = inspect.getsource(mcp_config)
    assert hasattr(mcp_config, "read_mcp_config")
    assert hasattr(mcp_config, "write_mcp_config")
    assert hasattr(mcp_config, "services_from_config")
    assert hasattr(mcp_config, "enabled_service_ids")
    assert "read_mcp_config_async" not in source
    assert "write_mcp_config_async" not in source
    assert "services_from_config_async" not in source
    assert "enabled_service_ids_async" not in source
    assert "postgres_connect" not in source
    assert "sql.SQL" not in source
    assert "async def list_tokens" in source
    assert "await list_token_rows" in source


def test_mcp_tools_do_not_load_dotenv_at_import_time() -> None:
    basic_source = inspect.getsource(basic_mcp_tool)
    playbook_source = inspect.getsource(playbook_mcp_tool)
    assert "\nload_dotenv(" not in basic_source
    assert "\nload_dotenv(" not in playbook_source
    assert "os.getenv" not in playbook_source
    assert "await load_runtime_env_async()" in playbook_source


def test_cve_update_task_uses_async_persistence_helpers() -> None:
    source = inspect.getsource(update_cve.update_cve_database)
    assert "psycopg" not in source
    assert "sql.SQL" not in source
    assert "insert_new_cve_rows" in source
    assert "delete_cve_rows" in source
    assert "count_cve_rows" in source


def test_cve_update_task_keeps_cache_io_off_event_loop() -> None:
    source = inspect.getsource(update_cve)
    get_add_del_source = inspect.getsource(update_cve.get_add_del_data)
    assert "AsyncPath" in source
    assert "to_thread.run_sync" in source
    assert "await _configure_file_logging_async()" in source
    assert "os.getenv" not in source
    assert "LOG_LEVEL =" not in source
    assert "os.makedirs(log_dir" not in source
    assert "os.path.exists" not in get_add_del_source
    assert "os.makedirs" not in get_add_del_source
    assert "open(" not in get_add_del_source
    assert "pl.read_csv(" not in get_add_del_source
    assert ".write_csv(" not in get_add_del_source
    assert "source.parse_data(" not in get_add_del_source
    assert "source.compare_with_local(" not in get_add_del_source


def test_cve_sources_do_not_read_config_at_import_time() -> None:
    source = inspect.getsource(cve_sources)
    assert "AsyncPath" in source
    assert "async def load_cve_source_config" in source
    assert "\nload_dotenv(" not in source
    assert "await load_runtime_env_async()" in source
    assert "os.getenv" not in source
    assert "with open(" not in source
    assert "tomllib.load(" not in source
    assert "CONFIG =" not in source


def test_cve_intel_skill_cache_fallback_uses_async_file_io() -> None:
    base_source = Path(
        "api/agent/skills/cve-intel-skill/scripts/base.py"
    ).read_text(encoding="utf-8")
    cve_intel_source = Path(
        "api/agent/skills/cve-intel-skill/scripts/cve_intel.py"
    ).read_text(encoding="utf-8")
    assert "async def fetch_from_cache_async" in base_source
    assert "await async_path.read_text" in base_source
    assert "path.open(" not in base_source
    assert "def fetch_from_cache(" not in base_source
    assert "await fetch_from_cache_async" in cve_intel_source


def test_local_config_services_are_sync_first_without_blocking_event_loop_regressions() -> None:
    settings_source = inspect.getsource(settings_route)
    assert "public_model_config()" in settings_source
    assert "save_model_config" in settings_source
    assert "load_model_config" in settings_source
    assert "await to_thread.run_sync" in settings_source
    assert "public_model_config_async" not in settings_source
    assert "save_model_config_async" not in settings_source
    assert "load_model_config_async" not in settings_source

    skills_source = inspect.getsource(skills_route)
    assert "list_skill_infos(user)" in skills_source
    assert "set_skill_enabled" in skills_source
    assert "await to_thread.run_sync(" in skills_source
    assert "install_skill_archive_async" not in skills_source

    mcp_server_source = inspect.getsource(mcp_server.IntegratedMcpRuntime)
    assert "build_main_mcp(enabled_service_ids())" in mcp_server_source
    assert not hasattr(mcp_server, "build_main_mcp_async")

    assert "to_thread.run_sync" not in inspect.getsource(model_config_service)
    assert "os.getenv" not in inspect.getsource(model_config_service)
    assert hasattr(model_config_service, "model_config_file")
    assert hasattr(model_config_service, "load_model_config")
    assert hasattr(model_config_service, "public_model_config")
    assert hasattr(model_config_service, "save_model_config")
    assert hasattr(model_config_service, "get_model_for_run")
    assert not hasattr(model_config_service, "load_model_config_async")
    assert not hasattr(model_config_service, "public_model_config_async")
    assert not hasattr(model_config_service, "save_model_config_async")
    assert not hasattr(model_config_service, "get_model_for_run_async")
    assert "to_thread.run_sync" not in inspect.getsource(mcp_config)
    assert "to_thread.run_sync" not in inspect.getsource(mcp_config_service)
    assert hasattr(mcp_config_service, "apply_service_toggle")
    assert hasattr(mcp_config_service, "apply_mcp_upload")
    assert not hasattr(mcp_config_service, "apply_service_toggle_async")
    assert not hasattr(mcp_config_service, "apply_mcp_upload_async")
    assert "to_thread.run_sync" not in inspect.getsource(
        security_run_runtime._load_prompt_async
    )
    assert "os.getenv" not in inspect.getsource(skill_service)
    assert hasattr(skill_service, "load_skills_config")
    assert hasattr(skill_service, "save_skills_config")
    assert hasattr(skill_service, "list_skill_infos")
    assert hasattr(skill_service, "set_skill_enabled")
    assert hasattr(skill_service, "get_enabled_skill_dirs")
    assert not hasattr(skill_service, "load_skills_config_async")
    assert not hasattr(skill_service, "save_skills_config_async")
    assert not hasattr(skill_service, "list_skill_infos_async")
    assert not hasattr(skill_service, "set_skill_enabled_async")
    assert not hasattr(skill_service, "get_enabled_skill_dirs_async")
    assert not hasattr(skill_service, "install_skill_archive_async")

    runtime_source = inspect.getsource(security_run_runtime)
    assert "get_enabled_skill_dirs" in runtime_source
    assert "_run_sync_dependency" in runtime_source
    assert "to_thread.run_sync(_load_local_skills" in runtime_source
    assert "\ndef _build_fallback_agent(" not in runtime_source


def test_agentos_registers_async_fallback_agent_factory() -> None:
    main_source = inspect.getsource(api_main)
    assert "AgentFactory(" in main_source
    assert "async def _build_agentos_fallback_agent" in main_source
    assert "agents=[_build_fallback_agent()]" not in main_source
    assert "_build_fallback_agent" not in main_source


def test_logging_setup_avoids_import_time_directory_creation() -> None:
    logging_source = inspect.getsource(core_logging)
    main_source = inspect.getsource(api_main)
    assert "async def configure_logging_async" in logging_source
    assert "await configure_logging_async(app_settings)" in main_source
    assert "configure_logging(app_settings)" not in main_source


def test_frontend_static_mount_defers_directory_check() -> None:
    main_source = inspect.getsource(api_main)
    assert "class LazyFrontendStaticFiles" in main_source
    assert inspect.iscoroutinefunction(api_main.frontend_static_dir)
    assert "await frontend_static_dir()" in main_source
    assert "from pathlib import Path" not in main_source
    assert "StaticFiles(directory=frontend_static_dir()" not in main_source
    assert "check_dir=False" in main_source


@pytest.mark.asyncio
async def test_lazy_frontend_static_files_prefers_source_dir(tmp_path, monkeypatch) -> None:
    (tmp_path / "source").mkdir()
    monkeypatch.chdir(tmp_path)

    static_app = api_main.LazyFrontendStaticFiles()
    resolved = await static_app._get_app()
    assert resolved.directory == "source"


def test_tracing_uses_async_agno_postgres_db() -> None:
    source = inspect.getsource(tracing_service.setup_agno_tracing)
    assert "get_async_agno_postgres_db" in source
    assert "get_agno_postgres_db" not in source
    assert "load_dotenv" not in source
    assert "os.environ" not in source


def test_os_control_agno_runtime_uses_agno_async_api() -> None:
    source = inspect.getsource(os_metrics_control)
    metrics_source = inspect.getsource(os_metrics_control.get_metrics_payload)
    assert "get_async_agno_postgres_db" in source
    assert "get_postgres_pool" not in source
    assert "from psycopg import sql" not in source
    assert "await db.get_traces" in metrics_source
    assert "await db.get_trace_stats" in metrics_source
    assert "await db.get_sessions" in metrics_source
    assert "await db.get_user_memory_stats" in metrics_source
    assert "agno_traces" not in metrics_source
    assert "agno_sessions" not in metrics_source
    assert "agno_memories" not in metrics_source


def test_os_control_control_plane_tables_use_async_sqlalchemy() -> None:
    source = inspect.getsource(os_evaluation_control)
    assert "get_async_control_plane_engine" in source
    assert "Table(" in source
    assert "select(table)" in source
    assert "os_approvals" not in source
    assert "submit_approval_request" not in source
    assert "CREATE TABLE IF NOT EXISTS" not in source


def test_postgres_store_no_longer_exposes_psycopg_pool() -> None:
    source = inspect.getsource(postgres_store)
    assert not hasattr(postgres_store, "get_postgres_pool")
    assert not hasattr(postgres_store, "close_postgres_pool")
    assert "AsyncConnectionPool" not in source
    assert "psycopg_pool" not in source


def test_knowledge_async_lifecycle_uses_agno_async_api() -> None:
    source = inspect.getsource(knowledge_service.KnowledgeBaseLifecycle)
    module_source = inspect.getsource(knowledge_service)
    assert "os.getenv" not in module_source
    assert "def add_text_document(" not in source
    assert "def add_file_document(" not in source
    assert "def list_documents(" not in source
    assert "def delete_document(" not in source
    assert "def clear_knowledge_base(" not in source
    assert "def search_documents(" not in source
    assert "def knowledge_status(" not in source
    assert "await knowledge.ainsert" in source
    assert "await knowledge.asearch" in source
    assert "await knowledge.aget_content" in source
    assert ".insert(" not in source
    assert ".search(" not in source
    assert ".load(" not in source
    assert ".get_content(" not in source
    assert ".get_content_by_id(" not in source
    assert ".remove_content_by_id(" not in source
    assert ".remove_all_content(" not in source
    assert "aremove_content_by_id" not in source
    assert "aremove_all_content" not in source
    assert "await self._delete_content_async" in source
    assert "await _resolve_existing_file_async" in source
    assert ".exists()" not in source
    assert ".is_file()" not in source
    assert "asyncio.to_thread" not in inspect.getsource(
        knowledge_service.KnowledgeBaseLifecycle.list_documents_async
    )
    assert "asyncio.to_thread" not in inspect.getsource(
        knowledge_service.KnowledgeBaseLifecycle.search_documents_async
    )
    assert "asyncio.to_thread" not in inspect.getsource(
        knowledge_service.KnowledgeBaseLifecycle.knowledge_status_async
    )
    assert not hasattr(knowledge_service, "get_knowledge_base")
    assert not hasattr(knowledge_service, "search_documents")
    assert not hasattr(knowledge_service, "delete_document")


def test_security_run_runtime_defaults_to_async_agno_db_and_knowledge() -> None:
    source = inspect.getsource(security_run_runtime.SecurityRunRuntimeDependencies)
    assert "get_async_agno_postgres_db" in source
    assert "get_async_knowledge_base: Callable" in source
    assert "get_enabled_skill_dirs" in source
    assert "get_enabled_skill_dirs_async" not in source
    runtime_source = inspect.getsource(security_run_runtime.SecurityRunRuntime)
    assert "await _load_prompt_async" in runtime_source
    assert "await _run_sync_dependency(self.dependencies.build_model" in runtime_source
    assert "await self._build_enabled_skills()" in runtime_source
    assert "os.environ" not in inspect.getsource(security_run_runtime)
    assert "= get_agno_postgres_db" not in source
    assert "= get_knowledge_base" not in source
    assert not hasattr(security_run_runtime, "_build_enabled_skills")


def test_mcp_tables_are_declared_in_sqlalchemy_persistence() -> None:
    token_table = mcp_tokens_table()
    assert token_table.c.id.identity.__class__.__name__ == "Identity"
    assert token_table.c.token.unique


def test_mcp_token_insert_omits_identity_id_when_absent() -> None:
    values = _token_insert_values(
        {
            "id": None,
            "name": "T.A.I.S Agent",
            "token": "token",
            "created_at": 1,
            "expires_at": 0,
        }
    )

    assert "id" not in values
    assert values["name"] == "T.A.I.S Agent"
