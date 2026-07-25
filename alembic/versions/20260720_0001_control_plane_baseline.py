"""Create the frozen T.A.I.S control-plane baseline.

This is deliberately a schema snapshot, not a call to
``control_plane_metadata()``.  Alembic revisions must describe the schema at
the time they were written; importing the live metadata here caused a fresh
database to create future tables and columns before their owning revisions ran.

Agno owns its own persistence and PgVector table lifecycle, so this revision
creates only tables owned by this repository.  Future changes to those tables
must be represented by a new Alembic revision; application startup must never
perform DDL.

Revision ID: 20260720_0001
Revises:
Create Date: 2026-07-20 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.schema import CreateSchema

from api.config import get_settings

revision: str = "20260720_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


# This is the control-plane schema immediately before 20260720_0002.  The
# ``__APP_SCHEMA__`` and ``__MCP_SCHEMA__`` tokens are rendered as quoted
# identifiers at runtime so deployments can retain configurable schemas.
_BASELINE_DDL = r"""
CREATE TABLE IF NOT EXISTS "user" (
    role VARCHAR(32) DEFAULT 'user' NOT NULL,
    id UUID NOT NULL,
    email VARCHAR(320) NOT NULL,
    hashed_password VARCHAR(1024) NOT NULL,
    is_active BOOLEAN NOT NULL,
    is_superuser BOOLEAN NOT NULL,
    is_verified BOOLEAN NOT NULL,
    PRIMARY KEY (id)
)
;

CREATE UNIQUE INDEX IF NOT EXISTS ix_user_email ON "user" (email)
;

CREATE TABLE IF NOT EXISTS __APP_SCHEMA__.agent_eval_suites (
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '' NOT NULL,
    target_agent_id TEXT DEFAULT 'security-operations' NOT NULL,
    enabled BOOLEAN DEFAULT true NOT NULL,
    tags JSONB DEFAULT '[]'::jsonb NOT NULL,
    created_by TEXT DEFAULT '' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id)
)
;

CREATE INDEX IF NOT EXISTS idx_agent_eval_suites_updated
    ON __APP_SCHEMA__.agent_eval_suites (updated_at DESC)
;

CREATE TABLE IF NOT EXISTS __APP_SCHEMA__.agent_eval_cases (
    id TEXT NOT NULL,
    suite_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '' NOT NULL,
    target_agent_id TEXT DEFAULT 'security-operations' NOT NULL,
    input TEXT NOT NULL,
    expected_output TEXT DEFAULT '' NOT NULL,
    criteria TEXT DEFAULT '' NOT NULL,
    threshold INTEGER DEFAULT 7 NOT NULL,
    eval_types JSONB DEFAULT '["accuracy"]'::jsonb NOT NULL,
    expected_tool_calls JSONB DEFAULT '[]'::jsonb NOT NULL,
    expected_tool_call_arguments JSONB DEFAULT '{}'::jsonb NOT NULL,
    allow_additional_tool_calls BOOLEAN DEFAULT false NOT NULL,
    performance_config JSONB DEFAULT '{}'::jsonb NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb NOT NULL,
    enabled BOOLEAN DEFAULT true NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id)
)
;

CREATE INDEX IF NOT EXISTS idx_agent_eval_cases_enabled
    ON __APP_SCHEMA__.agent_eval_cases (enabled)
;

CREATE INDEX IF NOT EXISTS idx_agent_eval_cases_suite
    ON __APP_SCHEMA__.agent_eval_cases (suite_id, updated_at DESC)
;

CREATE TABLE IF NOT EXISTS __APP_SCHEMA__.agent_eval_suite_runs (
    id TEXT NOT NULL,
    suite_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_by TEXT DEFAULT '' NOT NULL,
    error_summary TEXT DEFAULT '' NOT NULL,
    summary JSONB DEFAULT '{}'::jsonb NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id)
)
;

CREATE INDEX IF NOT EXISTS idx_agent_eval_suite_runs_status
    ON __APP_SCHEMA__.agent_eval_suite_runs (status)
;

CREATE INDEX IF NOT EXISTS idx_agent_eval_suite_runs_suite
    ON __APP_SCHEMA__.agent_eval_suite_runs (suite_id, started_at DESC)
;

CREATE TABLE IF NOT EXISTS __APP_SCHEMA__.agent_eval_case_runs (
    id TEXT NOT NULL,
    suite_run_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    status TEXT NOT NULL,
    agent_run_id TEXT DEFAULT '' NOT NULL,
    session_id TEXT DEFAULT '' NOT NULL,
    trace_id TEXT DEFAULT '' NOT NULL,
    agno_eval_run_ids JSONB DEFAULT '[]'::jsonb NOT NULL,
    error_type TEXT DEFAULT '' NOT NULL,
    error_summary TEXT DEFAULT '' NOT NULL,
    replay_of_case_run_id TEXT DEFAULT '' NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id)
)
;

CREATE INDEX IF NOT EXISTS idx_agent_eval_case_runs_status
    ON __APP_SCHEMA__.agent_eval_case_runs (status)
;

CREATE INDEX IF NOT EXISTS idx_agent_eval_case_runs_case
    ON __APP_SCHEMA__.agent_eval_case_runs (case_id, started_at DESC)
;

CREATE INDEX IF NOT EXISTS idx_agent_eval_case_runs_suite_run
    ON __APP_SCHEMA__.agent_eval_case_runs (suite_run_id, started_at DESC)
;

CREATE TABLE IF NOT EXISTS __APP_SCHEMA__.audit_logs (
    id BIGSERIAL NOT NULL,
    actor_user_id TEXT NOT NULL,
    actor_email TEXT DEFAULT '' NOT NULL,
    actor_role TEXT NOT NULL,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT DEFAULT '' NOT NULL,
    status TEXT DEFAULT 'success' NOT NULL,
    ip_address TEXT DEFAULT '' NOT NULL,
    user_agent TEXT DEFAULT '' NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id)
)
;

CREATE INDEX IF NOT EXISTS idx_audit_logs_ip_time
    ON __APP_SCHEMA__.audit_logs (ip_address, created_at DESC)
;

CREATE INDEX IF NOT EXISTS idx_audit_logs_created_time
    ON __APP_SCHEMA__.audit_logs (created_at DESC)
;

CREATE INDEX IF NOT EXISTS idx_audit_logs_action_time
    ON __APP_SCHEMA__.audit_logs (action, created_at DESC)
;

CREATE INDEX IF NOT EXISTS idx_audit_logs_status_time
    ON __APP_SCHEMA__.audit_logs (status, created_at DESC)
;

CREATE INDEX IF NOT EXISTS idx_audit_logs_resource_type_time
    ON __APP_SCHEMA__.audit_logs (resource_type, created_at DESC)
;

CREATE INDEX IF NOT EXISTS idx_audit_logs_email_time
    ON __APP_SCHEMA__.audit_logs (actor_email, created_at DESC)
;

CREATE INDEX IF NOT EXISTS idx_audit_logs_resource_id_time
    ON __APP_SCHEMA__.audit_logs (resource_id, created_at DESC)
;

CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_time
    ON __APP_SCHEMA__.audit_logs (actor_user_id, created_at DESC)
;

CREATE TABLE IF NOT EXISTS __APP_SCHEMA__.user_capability_preferences (
    user_id VARCHAR(255) NOT NULL,
    capability_type VARCHAR(32) NOT NULL,
    capability_key VARCHAR(255) NOT NULL,
    state VARCHAR(16) NOT NULL,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    PRIMARY KEY (user_id, capability_type, capability_key),
    CONSTRAINT ck_user_capability_preferences_state CHECK (state = 'disabled'),
    CONSTRAINT ck_user_capability_preferences_type
        CHECK (capability_type IN ('skill', 'mcp_server'))
)
;

CREATE INDEX IF NOT EXISTS idx_user_capability_preferences_user
    ON __APP_SCHEMA__.user_capability_preferences (user_id, capability_type)
;

CREATE TABLE IF NOT EXISTS __APP_SCHEMA__.chat_settings (
    id VARCHAR(32) NOT NULL,
    show_raw_reasoning BOOLEAN DEFAULT 'false' NOT NULL,
    show_raw_tool_io BOOLEAN DEFAULT 'false' NOT NULL,
    show_thought_chain BOOLEAN DEFAULT 'true' NOT NULL,
    memory_enabled BOOLEAN DEFAULT 'true' NOT NULL,
    updated_at BIGINT NOT NULL,
    PRIMARY KEY (id)
)
;

CREATE TABLE IF NOT EXISTS __APP_SCHEMA__.collect_articles (
    id BIGSERIAL NOT NULL,
    url TEXT NOT NULL,
    source_domain TEXT DEFAULT '' NOT NULL,
    title TEXT DEFAULT '' NOT NULL,
    markdown TEXT DEFAULT '' NOT NULL,
    summary TEXT DEFAULT '' NOT NULL,
    cve_ids TEXT[] DEFAULT '{}'::text[] NOT NULL,
    status TEXT DEFAULT 'ok' NOT NULL,
    error_message TEXT DEFAULT '' NOT NULL,
    fetched_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_collect_articles_url UNIQUE (url)
)
;

CREATE INDEX IF NOT EXISTS idx_collect_articles_status
    ON __APP_SCHEMA__.collect_articles (status)
;

CREATE INDEX IF NOT EXISTS idx_collect_articles_fetched
    ON __APP_SCHEMA__.collect_articles (fetched_at DESC)
;

CREATE INDEX IF NOT EXISTS idx_collect_articles_domain
    ON __APP_SCHEMA__.collect_articles (source_domain)
;

CREATE TABLE IF NOT EXISTS __APP_SCHEMA__.cves (
    id BIGSERIAL NOT NULL,
    cve_id TEXT NOT NULL,
    description TEXT DEFAULT '' NOT NULL,
    github_url TEXT NOT NULL,
    source TEXT NOT NULL,
    create_time TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id)
)
;

ALTER TABLE __APP_SCHEMA__.cves DROP CONSTRAINT IF EXISTS uq_cves_cve_url
;

CREATE UNIQUE INDEX IF NOT EXISTS uq_cves_cve_url_source
    ON __APP_SCHEMA__.cves (cve_id, github_url, source)
;

CREATE INDEX IF NOT EXISTS idx_cves_cve_id ON __APP_SCHEMA__.cves (cve_id)
;

CREATE INDEX IF NOT EXISTS idx_cves_source ON __APP_SCHEMA__.cves (source)
;

CREATE INDEX IF NOT EXISTS idx_cves_search ON __APP_SCHEMA__.cves USING gin
    (to_tsvector('simple', cve_id || ' ' || coalesce(description, '')))
;

CREATE TABLE IF NOT EXISTS __APP_SCHEMA__.durable_jobs (
    id VARCHAR(36) NOT NULL,
    kind VARCHAR(64) NOT NULL,
    payload JSONB DEFAULT '{}'::jsonb NOT NULL,
    idempotency_key TEXT NOT NULL,
    state VARCHAR(16) DEFAULT 'queued' NOT NULL,
    priority INTEGER DEFAULT '0' NOT NULL,
    attempt_count INTEGER DEFAULT '0' NOT NULL,
    max_attempts INTEGER DEFAULT '5' NOT NULL,
    available_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    lease_owner TEXT,
    lease_expires_at TIMESTAMP WITH TIME ZONE,
    heartbeat_at TIMESTAMP WITH TIME ZONE,
    last_error TEXT,
    result JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT ck_durable_jobs_attempt_count CHECK (attempt_count >= 0),
    CONSTRAINT ck_durable_jobs_max_attempts CHECK (max_attempts > 0),
    CONSTRAINT ck_durable_jobs_state
        CHECK (state IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    CONSTRAINT uq_durable_jobs_kind_key UNIQUE (kind, idempotency_key)
)
;

CREATE INDEX IF NOT EXISTS idx_durable_jobs_kind_state
    ON __APP_SCHEMA__.durable_jobs (kind, state)
;

CREATE INDEX IF NOT EXISTS idx_durable_jobs_claim
    ON __APP_SCHEMA__.durable_jobs (state, available_at, priority DESC, created_at)
;

CREATE INDEX IF NOT EXISTS idx_durable_jobs_lease
    ON __APP_SCHEMA__.durable_jobs (state, lease_expires_at)
;

CREATE TABLE IF NOT EXISTS __APP_SCHEMA__.knowledge_sources (
    content_id TEXT NOT NULL,
    source JSONB DEFAULT '{}'::jsonb NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (content_id)
)
;

CREATE TABLE IF NOT EXISTS __APP_SCHEMA__.model_configs (
    id VARCHAR(255) NOT NULL,
    name TEXT NOT NULL,
    model_id TEXT NOT NULL,
    provider VARCHAR(64) NOT NULL,
    api_protocol VARCHAR(64) NOT NULL,
    structured_output_mode VARCHAR(32) NOT NULL,
    default_reasoning_effort VARCHAR(16),
    parallel_tool_calls BOOLEAN,
    live_search_enabled BOOLEAN DEFAULT 'false' NOT NULL,
    retries BIGINT DEFAULT '4' NOT NULL,
    delay_between_retries BIGINT DEFAULT '1' NOT NULL,
    exponential_backoff BOOLEAN DEFAULT 'true' NOT NULL,
    http_max_retries BIGINT,
    base_url TEXT DEFAULT '' NOT NULL,
    api_key TEXT DEFAULT '' NOT NULL,
    description TEXT DEFAULT '' NOT NULL,
    enabled BOOLEAN DEFAULT 'true' NOT NULL,
    builtin BOOLEAN DEFAULT 'false' NOT NULL,
    active BOOLEAN DEFAULT 'false' NOT NULL,
    sort_order BIGINT NOT NULL,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    PRIMARY KEY (id)
)
;

CREATE INDEX IF NOT EXISTS idx_model_configs_active
    ON __APP_SCHEMA__.model_configs (active)
;

CREATE INDEX IF NOT EXISTS idx_model_configs_sort_order
    ON __APP_SCHEMA__.model_configs (sort_order)
;

CREATE TABLE IF NOT EXISTS __APP_SCHEMA__.notifications (
    id BIGSERIAL NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    data JSONB NOT NULL,
    read BOOLEAN DEFAULT 'false' NOT NULL,
    created_at BIGINT NOT NULL,
    read_at BIGINT,
    PRIMARY KEY (id)
)
;

CREATE INDEX IF NOT EXISTS idx_notifications_user_id
    ON __APP_SCHEMA__.notifications (user_id, id)
;

CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
    ON __APP_SCHEMA__.notifications (user_id, read)
;

CREATE INDEX IF NOT EXISTS idx_notifications_user_created
    ON __APP_SCHEMA__.notifications (user_id, created_at DESC)
;

CREATE TABLE IF NOT EXISTS __APP_SCHEMA__.upload_approvals (
    id VARCHAR(36) NOT NULL,
    resource_type VARCHAR(16) NOT NULL,
    status VARCHAR(16) DEFAULT 'pending' NOT NULL,
    submitted_by VARCHAR(255) NOT NULL,
    submitted_by_email VARCHAR(320) DEFAULT '' NOT NULL,
    resolved_by VARCHAR(255),
    resolved_by_email VARCHAR(320),
    rejection_reason VARCHAR(2000),
    payload JSONB NOT NULL,
    created_at BIGINT NOT NULL,
    resolved_at BIGINT,
    updated_at BIGINT NOT NULL,
    PRIMARY KEY (id)
)
;

CREATE TABLE IF NOT EXISTS __APP_SCHEMA__.workflow_custom_nodes (
    id VARCHAR(64) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT DEFAULT '' NOT NULL,
    color VARCHAR(32) DEFAULT '#1677ff' NOT NULL,
    definition JSONB DEFAULT '{}' NOT NULL,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    PRIMARY KEY (id)
)
;

CREATE TABLE IF NOT EXISTS __APP_SCHEMA__.workflows (
    id VARCHAR(36) NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '' NOT NULL,
    owner_user_id VARCHAR(255) NOT NULL,
    definition JSONB NOT NULL,
    triggers JSONB DEFAULT '{}' NOT NULL,
    enabled BOOLEAN DEFAULT 'true' NOT NULL,
    version BIGINT DEFAULT '1' NOT NULL,
    published_definition JSONB,
    published_version BIGINT,
    published_at BIGINT,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    PRIMARY KEY (id)
)
;

CREATE INDEX IF NOT EXISTS idx_workflows_updated
    ON __APP_SCHEMA__.workflows (updated_at)
;

CREATE INDEX IF NOT EXISTS idx_workflows_owner
    ON __APP_SCHEMA__.workflows (owner_user_id)
;

CREATE TABLE IF NOT EXISTS __APP_SCHEMA__.workflow_versions (
    id VARCHAR(36) NOT NULL,
    workflow_id VARCHAR(36) NOT NULL,
    version BIGINT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '' NOT NULL,
    definition JSONB NOT NULL,
    triggers JSONB DEFAULT '{}' NOT NULL,
    created_at BIGINT NOT NULL,
    created_by VARCHAR(255) DEFAULT '' NOT NULL,
    PRIMARY KEY (id)
)
;

CREATE INDEX IF NOT EXISTS ix_app_workflow_versions_workflow_id
    ON __APP_SCHEMA__.workflow_versions (workflow_id)
;

CREATE INDEX IF NOT EXISTS idx_workflow_versions_wf
    ON __APP_SCHEMA__.workflow_versions (workflow_id, version)
;

CREATE TABLE IF NOT EXISTS __MCP_SCHEMA__.mcp_tokens (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY,
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    owner_user_id VARCHAR(255),
    token_kind VARCHAR(16) DEFAULT 'service' NOT NULL,
    created_at BIGINT NOT NULL,
    expires_at BIGINT NOT NULL,
    PRIMARY KEY (id)
)
;

CREATE UNIQUE INDEX IF NOT EXISTS uq_mcp_tokens_token_hash
    ON __MCP_SCHEMA__.mcp_tokens (token_hash)
;

CREATE TABLE IF NOT EXISTS __MCP_SCHEMA__.mcp_servers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY,
    name VARCHAR(255) NOT NULL,
    namespace VARCHAR(128) NOT NULL,
    description TEXT DEFAULT '' NOT NULL,
    server_type VARCHAR(32) NOT NULL,
    transport VARCHAR(32) NOT NULL,
    enabled BOOLEAN DEFAULT 'true' NOT NULL,
    visibility VARCHAR(16) DEFAULT 'private' NOT NULL,
    owner_user_id VARCHAR(255) DEFAULT '' NOT NULL,
    config JSONB DEFAULT '{}' NOT NULL,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (name),
    UNIQUE (namespace)
)
;

CREATE TABLE IF NOT EXISTS oauth_account (
    id UUID NOT NULL,
    user_id UUID NOT NULL,
    oauth_name VARCHAR(100) NOT NULL,
    access_token VARCHAR(1024) NOT NULL,
    expires_at INTEGER,
    refresh_token VARCHAR(1024),
    account_id VARCHAR(320) NOT NULL,
    account_email VARCHAR(320) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(user_id) REFERENCES "user" (id) ON DELETE cascade
)
;

CREATE INDEX IF NOT EXISTS ix_oauth_account_oauth_name
    ON oauth_account (oauth_name)
;

CREATE INDEX IF NOT EXISTS ix_oauth_account_account_id
    ON oauth_account (account_id)
;

CREATE TABLE IF NOT EXISTS __MCP_SCHEMA__.mcp_component_overrides (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY,
    server_id BIGINT NOT NULL,
    component_type VARCHAR(16) NOT NULL,
    component_name VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL,
    updated_at BIGINT NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_mcp_component_override
        UNIQUE (server_id, component_type, component_name),
    FOREIGN KEY(server_id) REFERENCES __MCP_SCHEMA__.mcp_servers (id) ON DELETE CASCADE
)
;
"""


_BASELINE_TABLES_IN_REVERSE_DEPENDENCY_ORDER = (
    ("mcp", "mcp_component_overrides"),
    (None, "oauth_account"),
    ("mcp", "mcp_servers"),
    ("mcp", "mcp_tokens"),
    ("app", "workflow_versions"),
    ("app", "workflows"),
    ("app", "workflow_custom_nodes"),
    ("app", "upload_approvals"),
    ("app", "notifications"),
    ("app", "model_configs"),
    ("app", "knowledge_sources"),
    ("app", "durable_jobs"),
    ("app", "cves"),
    ("app", "collect_articles"),
    ("app", "chat_settings"),
    ("app", "user_capability_preferences"),
    ("app", "audit_logs"),
    ("app", "agent_eval_case_runs"),
    ("app", "agent_eval_suite_runs"),
    ("app", "agent_eval_cases"),
    ("app", "agent_eval_suites"),
    (None, "user"),
)


def _render_baseline_ddl(*, app_schema: str, mcp_schema: str) -> tuple[str, ...]:
    rendered = (
        _BASELINE_DDL.replace("__APP_SCHEMA__", _identifier(app_schema))
        .replace("__MCP_SCHEMA__", _identifier(mcp_schema))
        .strip()
    )
    return tuple(statement.strip() for statement in rendered.split("\n;\n") if statement.strip())


def upgrade() -> None:
    """Create the revision's frozen table and index snapshot."""
    bind = op.get_bind()
    settings = get_settings()

    bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    for schema in (
        settings.agno_app_schema,
        settings.agno_db_schema,
        settings.agno_mcp_schema,
        settings.agno_knowledge_schema,
    ):
        bind.execute(CreateSchema(schema, if_not_exists=True))

    for statement in _render_baseline_ddl(
        app_schema=settings.agno_app_schema,
        mcp_schema=settings.agno_mcp_schema,
    ):
        bind.execute(sa.text(statement))


def downgrade() -> None:
    """Drop only the tables created by this frozen revision."""
    settings = get_settings()
    schemas = {
        "app": _identifier(settings.agno_app_schema),
        "mcp": _identifier(settings.agno_mcp_schema),
    }
    bind = op.get_bind()
    for schema_key, table_name in _BASELINE_TABLES_IN_REVERSE_DEPENDENCY_ORDER:
        table = _identifier(table_name)
        qualified_table = table if schema_key is None else f"{schemas[schema_key]}.{table}"
        bind.execute(sa.text(f"DROP TABLE IF EXISTS {qualified_table}"))
