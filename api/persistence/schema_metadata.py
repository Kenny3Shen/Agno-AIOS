"""Canonical SQLAlchemy metadata for T.A.I.S-owned control-plane tables.

Agno owns the schema of its session, trace, approval and vector-store tables.
Those tables deliberately remain outside this metadata: their lifecycle is tied
to the installed Agno version.  Everything owned by this repository belongs in
the control-plane migration stream and is exposed here for Alembic.
"""

from __future__ import annotations

from sqlalchemy import MetaData, Table

from api.auth.models import AuthBase
from api.config import get_settings
from api.persistence.agent_evals import (
    agent_eval_case_runs_table,
    agent_eval_cases_table,
    agent_eval_suite_runs_table,
    agent_eval_suites_table,
)
from api.persistence.audit_logs import audit_logs_table
from api.persistence.capability_preferences import capability_preferences_table
from api.persistence.chat_settings import chat_settings_table
from api.persistence.collect_articles import collect_articles_table
from api.persistence.cves import cves_table
from api.persistence.durable_jobs import durable_jobs_table
from api.persistence.ip_blacklist import ip_blacklist_table
from api.persistence.knowledge_sources import knowledge_sources_table
from api.persistence.guardrail_settings import guardrail_settings_table
from api.persistence.knowledge_rag_settings import knowledge_rag_settings_table
from api.persistence.mcp import (
    mcp_component_overrides_table,
    mcp_servers_table,
    mcp_tokens_table,
)
from api.persistence.model_configs import model_configs_table
from api.persistence.notifications import _table as notifications_table
from api.persistence.upload_approvals import upload_approvals_table
from api.persistence.user_notification_settings import user_notification_settings_table
from api.persistence.workflows import workflow_versions_table, workflows_table
from api.persistence.workflow_custom_nodes import workflow_custom_nodes_table


def _copy_tables(target: MetaData, tables: list[Table]) -> None:
    """Copy source tables (and their indexes/constraints) to one metadata graph."""
    for table in tables:
        if table.schema is None:
            table.to_metadata(target)
        else:
            table.to_metadata(target, schema=table.schema)


def control_plane_metadata() -> MetaData:
    """Return all repository-owned tables for Alembic and schema checks.

    The individual persistence modules intentionally create isolated metadata
    objects so they can be used without a global import graph.  Alembic needs
    one graph, therefore this function copies their frozen definitions without
    changing any runtime query path.
    """
    target = MetaData()

    _copy_tables(target, list(AuthBase.metadata.sorted_tables))

    app_tables = [
        agent_eval_suites_table(),
        agent_eval_cases_table(),
        agent_eval_suite_runs_table(),
        agent_eval_case_runs_table(),
        audit_logs_table(),
        capability_preferences_table(),
        chat_settings_table(),
        collect_articles_table(),
        cves_table(),
        ip_blacklist_table(),
        durable_jobs_table(),
        knowledge_sources_table(),
        knowledge_rag_settings_table(),
        guardrail_settings_table(),
        model_configs_table(),
        notifications_table(),
        upload_approvals_table(),
        user_notification_settings_table(),
        workflow_custom_nodes_table(),
    ]
    settings = get_settings()
    workflow_metadata = MetaData(schema=settings.agno_app_schema)
    app_tables.extend(
        [
            workflows_table(workflow_metadata),
            workflow_versions_table(workflow_metadata),
        ]
    )
    _copy_tables(target, app_tables)

    mcp_metadata = MetaData(schema=settings.agno_mcp_schema)
    _copy_tables(
        target,
        [
            mcp_tokens_table(mcp_metadata),
            mcp_servers_table(mcp_metadata),
            mcp_component_overrides_table(mcp_metadata),
        ],
    )
    return target
