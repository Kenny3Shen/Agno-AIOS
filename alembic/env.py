"""Alembic environment for repository-owned PostgreSQL control-plane tables."""

from __future__ import annotations

from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.schema import SchemaItem

from api.config import get_settings
from api.persistence.schema_metadata import control_plane_metadata

config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.postgres_sqlalchemy_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = control_plane_metadata()
_MANAGED_SCHEMAS = frozenset(
    {None, "public", settings.agno_app_schema, settings.agno_mcp_schema}
)


def include_object(
    object_: SchemaItem,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: SchemaItem | None,
) -> bool:
    """Exclude Agno-owned trace/session/vector tables from autogenerate.

    Their schema is versioned by Agno itself.  Alembic governs only the
    repository control plane, otherwise a revision autogenerate could propose
    destructive drops for every Agno table it does not recognise.
    """
    del name, reflected, compare_to
    if type_ == "schema":
        return getattr(object_, "name", None) in _MANAGED_SCHEMAS
    table = object_ if type_ == "table" else getattr(object_, "table", None)
    if table is None:
        return True
    return getattr(table, "schema", None) in _MANAGED_SCHEMAS


def _configure(**kwargs: Any) -> None:
    context.configure(
        target_metadata=target_metadata,
        include_schemas=True,
        include_object=include_object,
        compare_type=True,
        **kwargs,
    )


def run_migrations_offline() -> None:
    """Run migrations without opening a database connection."""
    _configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against PostgreSQL using a one-off, unpooled connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        _configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
