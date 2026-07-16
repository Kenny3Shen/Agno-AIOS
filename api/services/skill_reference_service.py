"""Resolve which saved workflows reference a skill by name."""

from __future__ import annotations

from typing import Any

from api.auth.claims import ADMIN_SCOPE, ActorLike, actor_id, has_scope
from api.persistence import workflows as workflow_store


def _walk_skills(node: Any, found: set[str]) -> None:
    if not isinstance(node, dict):
        if isinstance(node, list):
            for item in node:
                _walk_skills(item, found)
        return
    raw = node.get("skills")
    if isinstance(raw, list):
        for entry in raw:
            name = str(entry or "").strip()
            if name:
                found.add(name)
    for key in ("steps", "then_steps", "else_steps", "choices"):
        child = node.get(key)
        if isinstance(child, list):
            for item in child:
                if key == "choices" and isinstance(item, dict):
                    _walk_skills(item.get("steps"), found)
                else:
                    _walk_skills(item, found)


def skill_names_in_definition(definition: Any) -> set[str]:
    names: set[str] = set()
    if not isinstance(definition, dict):
        return names
    _walk_skills(definition.get("steps"), names)
    return names


async def list_skill_workflow_references(
    actor: ActorLike,
    skill_name: str,
    *,
    limit: int = 50,
) -> list[dict[str, str]]:
    """Return workflows visible to actor that bind ``skill_name`` on any step.

    Scans saved draft definitions (not only published). Bounded page walk.
    """
    needle = (skill_name or "").strip()
    if not needle:
        return []
    owner = None if has_scope(actor, ADMIN_SCOPE) else actor_id(actor)
    safe_limit = max(1, min(int(limit or 50), 100))
    matches: list[dict[str, str]] = []
    page = 1
    # Cap scan so a huge catalog cannot hang the request.
    max_pages = 20
    while page <= max_pages and len(matches) < safe_limit:
        rows, total = await workflow_store.list_workflows(
            owner_user_id=owner,
            page=page,
            limit=100,
        )
        if not rows:
            break
        for row in rows:
            definition = row.get("definition")
            names = skill_names_in_definition(definition)
            if needle not in names:
                continue
            matches.append(
                {
                    "workflow_id": str(row.get("id") or ""),
                    "name": str(row.get("name") or ""),
                    "version": str(row.get("version") or ""),
                }
            )
            if len(matches) >= safe_limit:
                break
        if page * 100 >= int(total or 0):
            break
        page += 1
    return matches
