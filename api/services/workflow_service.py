"""CRUD + projection for workbench workflow definitions."""

from __future__ import annotations

import time
from typing import Any

from api.auth.claims import ADMIN_SCOPE, ActorLike, actor_id, has_scope
from api.persistence import workflows as workflow_store
from api.services.workflow_compiler import (
    WorkflowDefinitionError,
    list_executor_options,
    validate_and_normalize_definition,
)
from api.utils.pagination import pagination_meta


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
        "enabled": bool(row.get("enabled", True)),
        "version": int(row.get("version") or 1),
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


async def create_workflow_for_actor(
    actor: ActorLike,
    *,
    name: str | None,
    description: str | None,
    definition: object,
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
    record = {
        "id": workflow_store.new_workflow_id(),
        "name": normalized["name"],
        "description": normalized["description"],
        "owner_user_id": actor_id(actor),
        "definition": normalized,
        "enabled": True,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }
    row = await workflow_store.insert_workflow(record)
    return _row_payload(row)


async def update_workflow_for_actor(
    actor: ActorLike,
    workflow_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    definition: object | None = None,
    enabled: bool | None = None,
) -> dict[str, Any] | None:
    existing = await get_workflow_for_actor(actor, workflow_id)
    if existing is None:
        return None
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
    owner = None if has_scope(actor, ADMIN_SCOPE) else actor_id(actor)
    row = await workflow_store.update_workflow(
        workflow_id, owner_user_id=owner, values=values
    )
    return _row_payload(row) if row else None


async def delete_workflow_for_actor(actor: ActorLike, workflow_id: str) -> bool:
    existing = await get_workflow_for_actor(actor, workflow_id)
    if existing is None:
        return False
    owner = None if has_scope(actor, ADMIN_SCOPE) else actor_id(actor)
    return await workflow_store.delete_workflow(workflow_id, owner_user_id=owner)


def executor_catalog() -> list[dict[str, str]]:
    return list_executor_options()
