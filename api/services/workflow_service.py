"""CRUD + projection for workbench workflow definitions (PR4 versions/triggers)."""

from __future__ import annotations

import secrets
import time
from typing import Any
from uuid import uuid4

from api.auth.claims import ADMIN_SCOPE, ActorLike, actor_id, has_scope
from api.persistence import workflows as workflow_store
from api.services.workflow_compiler import (
    WorkflowDefinitionError,
    list_executor_options,
    validate_and_normalize_definition,
)
from api.utils.pagination import pagination_meta


def _normalize_triggers(raw: object | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {
            "webhook": {"enabled": False, "secret": ""},
            "cron": {"enabled": False, "expression": ""},
        }
    webhook_raw = raw.get("webhook")
    cron_raw = raw.get("cron")
    webhook: dict[str, Any] = (
        {str(k): v for k, v in webhook_raw.items()} if isinstance(webhook_raw, dict) else {}
    )
    cron: dict[str, Any] = (
        {str(k): v for k, v in cron_raw.items()} if isinstance(cron_raw, dict) else {}
    )
    secret = str(webhook.get("secret") or "").strip()
    return {
        "webhook": {
            "enabled": bool(webhook.get("enabled")),
            "secret": secret,
        },
        "cron": {
            "enabled": bool(cron.get("enabled")),
            "expression": str(cron.get("expression") or "").strip(),
            "last_run_at": float(cron.get("last_run_at") or 0) or 0,
        },
    }


def _row_payload(row: dict[str, Any]) -> dict[str, Any]:
    definition = row.get("definition")
    if not isinstance(definition, dict):
        definition = {"name": row.get("name") or "", "description": "", "steps": []}
    return {
        "id": str(row.get("id") or ""),
        "name": str(row.get("name") or definition.get("name") or ""),
        "description": str(row.get("description") or definition.get("description") or ""),
        "owner_user_id": str(row.get("owner_user_id") or ""),
        "definition": definition,
        "triggers": _normalize_triggers(row.get("triggers")),
        "enabled": bool(row.get("enabled", True)),
        "version": int(row.get("version") or 1),
        "published_version": (
            int(row["published_version"])
            if row.get("published_version") is not None
            else None
        ),
        "published_at": (
            int(row["published_at"]) if row.get("published_at") is not None else None
        ),
        "has_published": isinstance(row.get("published_definition"), dict)
        and bool(row.get("published_definition")),
        "created_at": int(row.get("created_at") or 0),
        "updated_at": int(row.get("updated_at") or 0),
    }


def _owner_filter(actor: ActorLike, requested_user_id: str | None) -> str | None:
    if has_scope(actor, ADMIN_SCOPE):
        requested = (requested_user_id or "").strip()
        return requested or None
    return actor_id(actor)


async def list_workflows_for_actor(
    actor: ActorLike,
    *,
    user_id: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    started = time.perf_counter()
    owner = _owner_filter(actor, user_id)
    rows, total = await workflow_store.list_workflows(
        owner_user_id=owner,
        page=page,
        limit=limit,
    )
    return {
        "data": [_row_payload(row) for row in rows],
        "meta": pagination_meta(
            page=page,
            limit=limit,
            total_count=total,
            search_time_ms=(time.perf_counter() - started) * 1000,
        ),
    }


async def get_workflow_for_actor(actor: ActorLike, workflow_id: str) -> dict[str, Any] | None:
    row = await workflow_store.get_workflow(workflow_id)
    if row is None:
        return None
    if not has_scope(actor, ADMIN_SCOPE) and str(row.get("owner_user_id") or "") != actor_id(actor):
        return None
    return _row_payload(row)


async def _snapshot_version(
    *,
    row: dict[str, Any],
    created_by: str,
) -> None:
    """Snapshot current row as immutable version history entry."""
    try:
        await workflow_store.insert_workflow_version(
            {
                "id": str(uuid4()),
                "workflow_id": str(row.get("id") or ""),
                "version": int(row.get("version") or 1),
                "name": str(row.get("name") or ""),
                "description": str(row.get("description") or ""),
                "definition": row.get("definition")
                if isinstance(row.get("definition"), dict)
                else {},
                "triggers": _normalize_triggers(row.get("triggers")),
                "created_at": workflow_store.now_ts(),
                "created_by": created_by,
            }
        )
    except Exception:
        # Version history is best-effort; do not fail saves.
        pass


async def create_workflow_for_actor(
    actor: ActorLike,
    *,
    name: str | None,
    description: str | None,
    definition: object,
    triggers: object | None = None,
) -> dict[str, Any]:
    try:
        normalized = validate_and_normalize_definition(
            {
                **(definition if isinstance(definition, dict) else {}),
                "name": name
                or (definition.get("name") if isinstance(definition, dict) else None)
                or "Untitled workflow",
                "description": description
                if description is not None
                else (
                    definition.get("description") if isinstance(definition, dict) else ""
                ),
            }
        )
    except WorkflowDefinitionError:
        raise
    now = workflow_store.now_ts()
    trigger_cfg = _normalize_triggers(triggers)
    if trigger_cfg["webhook"]["enabled"] and not trigger_cfg["webhook"]["secret"]:
        trigger_cfg["webhook"]["secret"] = secrets.token_urlsafe(24)
    record = {
        "id": workflow_store.new_workflow_id(),
        "name": normalized["name"],
        "description": normalized["description"],
        "owner_user_id": actor_id(actor),
        "definition": normalized,
        "triggers": trigger_cfg,
        "enabled": True,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }
    row = await workflow_store.insert_workflow(record)
    await _snapshot_version(row=row, created_by=actor_id(actor))
    return _row_payload(row)


async def update_workflow_for_actor(
    actor: ActorLike,
    workflow_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    definition: object | None = None,
    enabled: bool | None = None,
    triggers: object | None = None,
) -> dict[str, Any] | None:
    existing_row = await workflow_store.get_workflow(workflow_id)
    if existing_row is None:
        return None
    if not has_scope(actor, ADMIN_SCOPE) and str(
        existing_row.get("owner_user_id") or ""
    ) != actor_id(actor):
        return None
    existing = _row_payload(existing_row)
    # Snapshot pre-update state as previous version history
    await _snapshot_version(row=existing_row, created_by=actor_id(actor))

    current_def = existing["definition"]
    if not isinstance(current_def, dict):
        current_def = {}
    next_def_source: dict[str, Any] = dict(current_def)
    if isinstance(definition, dict):
        merged = {str(key): value for key, value in definition.items()}
        next_def_source = {**next_def_source, **merged}
    if name is not None:
        next_def_source["name"] = name
    if description is not None:
        next_def_source["description"] = description
    try:
        normalized = validate_and_normalize_definition(next_def_source)
    except WorkflowDefinitionError:
        raise
    values: dict[str, Any] = {
        "name": normalized["name"],
        "description": normalized["description"],
        "definition": normalized,
        "version": int(existing.get("version") or 1) + 1,
        "updated_at": workflow_store.now_ts(),
    }
    if enabled is not None:
        values["enabled"] = bool(enabled)
    if triggers is not None:
        trigger_cfg = _normalize_triggers(triggers)
        if trigger_cfg["webhook"]["enabled"] and not trigger_cfg["webhook"]["secret"]:
            prev = _normalize_triggers(existing.get("triggers"))
            trigger_cfg["webhook"]["secret"] = (
                prev["webhook"].get("secret") or secrets.token_urlsafe(24)
            )
        values["triggers"] = trigger_cfg
    owner = None if has_scope(actor, ADMIN_SCOPE) else actor_id(actor)
    row = await workflow_store.update_workflow(
        workflow_id, owner_user_id=owner, values=values
    )
    return _row_payload(row) if row else None


async def list_versions_for_actor(
    actor: ActorLike,
    workflow_id: str,
    *,
    page: int = 1,
    limit: int = 20,
) -> dict[str, Any] | None:
    existing = await get_workflow_for_actor(actor, workflow_id)
    if existing is None:
        return None
    started = time.perf_counter()
    rows, total = await workflow_store.list_workflow_versions(
        workflow_id, page=page, limit=limit
    )
    data = [
        {
            "id": str(row.get("id") or ""),
            "workflow_id": workflow_id,
            "version": int(row.get("version") or 0),
            "name": str(row.get("name") or ""),
            "description": str(row.get("description") or ""),
            "definition": row.get("definition")
            if isinstance(row.get("definition"), dict)
            else {},
            "triggers": _normalize_triggers(row.get("triggers")),
            "created_at": int(row.get("created_at") or 0),
            "created_by": str(row.get("created_by") or ""),
        }
        for row in rows
    ]
    return {
        "data": data,
        "meta": pagination_meta(
            page=page,
            limit=limit,
            total_count=total,
            search_time_ms=(time.perf_counter() - started) * 1000,
        ),
    }


async def restore_version_for_actor(
    actor: ActorLike,
    workflow_id: str,
    version: int,
) -> dict[str, Any] | None:
    existing = await get_workflow_for_actor(actor, workflow_id)
    if existing is None:
        return None
    snap = await workflow_store.get_workflow_version(workflow_id, version)
    if snap is None:
        return None
    return await update_workflow_for_actor(
        actor,
        workflow_id,
        name=str(snap.get("name") or existing["name"]),
        description=str(snap.get("description") or ""),
        definition=snap.get("definition")
        if isinstance(snap.get("definition"), dict)
        else existing["definition"],
        triggers=snap.get("triggers"),
    )


async def delete_workflow_for_actor(actor: ActorLike, workflow_id: str) -> bool:
    existing = await get_workflow_for_actor(actor, workflow_id)
    if existing is None:
        return False
    owner = None if has_scope(actor, ADMIN_SCOPE) else actor_id(actor)
    return await workflow_store.delete_workflow(workflow_id, owner_user_id=owner)


def executor_catalog() -> list[dict[str, str]]:
    return list_executor_options()


def verify_webhook_secret(row: dict[str, Any], secret: str | None) -> bool:
    triggers = _normalize_triggers(row.get("triggers"))
    webhook = triggers.get("webhook") or {}
    if not webhook.get("enabled"):
        return False
    expected = str(webhook.get("secret") or "")
    if not expected:
        return False
    return secrets.compare_digest(expected, str(secret or ""))



def get_published_definition(row: dict[str, Any]) -> dict[str, Any] | None:
    """Return published definition only (triggers use this for webhook/cron)."""
    published = row.get("published_definition")
    if isinstance(published, dict) and published.get("steps") is not None:
        return published
    return None


async def publish_workflow_for_actor(actor: ActorLike, workflow_id: str) -> dict[str, Any] | None:
    """Snapshot current draft definition as the live published revision."""
    existing = await get_workflow_for_actor(actor, workflow_id)
    if existing is None:
        return None
    row = await workflow_store.get_workflow(workflow_id)
    if row is None:
        return None
    definition = row.get("definition")
    if not isinstance(definition, dict):
        raise WorkflowDefinitionError("Workflow definition is invalid")
    # re-validate draft before publish
    normalized = validate_and_normalize_definition(definition)
    now = workflow_store.now_ts()
    version = int(row.get("version") or 1)
    updated = await workflow_store.update_workflow(
        workflow_id,
        owner_user_id=None if has_scope(actor, ADMIN_SCOPE) else actor_id(actor),
        values={
            "published_definition": normalized,
            "published_version": version,
            "published_at": now,
            "updated_at": now,
        },
    )
    if updated is None:
        return None
    await _snapshot_version(row={**updated, "definition": normalized, "version": version}, created_by=actor_id(actor) or "system")
    return _row_payload(updated)


async def mark_cron_last_run(workflow_id: str, ts: float) -> None:
    row = await workflow_store.get_workflow(workflow_id)
    if row is None:
        return
    triggers = _normalize_triggers(row.get("triggers"))
    triggers["cron"]["last_run_at"] = float(ts)
    await workflow_store.update_workflow(
        workflow_id,
        values={"triggers": triggers, "updated_at": workflow_store.now_ts()},
    )
