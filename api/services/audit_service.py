from __future__ import annotations

from typing import Any

from loguru import logger
from psycopg import sql
from psycopg.types.json import Jsonb

from api.services.postgres_store import app_schema, postgres_connect


def _actor_id(actor: Any) -> str:
    return str(getattr(actor, "id", "") or "")


def _actor_role(actor: Any) -> str:
    if bool(getattr(actor, "is_superuser", False)):
        return "admin"
    role = str(getattr(actor, "role", "user") or "user").lower()
    return role if role in {"admin", "user", "guest"} else "user"


def ensure_audit_log_table() -> None:
    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                    sql.Identifier(app_schema())
                )
            )
            table = sql.Identifier(app_schema(), "audit_logs")
            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {} (
                        id BIGSERIAL PRIMARY KEY,
                        actor_user_id TEXT NOT NULL,
                        actor_email TEXT NOT NULL DEFAULT '',
                        actor_role TEXT NOT NULL,
                        action TEXT NOT NULL,
                        resource_type TEXT NOT NULL,
                        resource_id TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'success',
                        ip_address TEXT NOT NULL DEFAULT '',
                        user_agent TEXT NOT NULL DEFAULT '',
                        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                ).format(table)
            )
            cursor.execute(
                sql.SQL(
                    "CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_time ON {} (actor_user_id, created_at DESC)"
                ).format(table)
            )
            cursor.execute(
                sql.SQL(
                    "CREATE INDEX IF NOT EXISTS idx_audit_logs_action_time ON {} (action, created_at DESC)"
                ).format(table)
            )


def record_audit_event(
    actor: Any,
    *,
    action: str,
    resource_type: str,
    resource_id: str = "",
    status: str = "success",
    metadata: dict[str, Any] | None = None,
    ip_address: str = "",
    user_agent: str = "",
) -> None:
    try:
        ensure_audit_log_table()
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        """
                        INSERT INTO {} (
                            actor_user_id,
                            actor_email,
                            actor_role,
                            action,
                            resource_type,
                            resource_id,
                            status,
                            ip_address,
                            user_agent,
                            metadata
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """
                    ).format(sql.Identifier(app_schema(), "audit_logs")),
                    (
                        _actor_id(actor),
                        str(getattr(actor, "email", "") or ""),
                        _actor_role(actor),
                        action,
                        resource_type,
                        resource_id,
                        status,
                        ip_address,
                        user_agent,
                        Jsonb(metadata or {}),
                    ),
                )
    except Exception as exc:
        logger.warning("审计日志写入失败: {}", exc)
