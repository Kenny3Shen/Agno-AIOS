# Native Visibility and Governance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement native private/public visibility for Skill, MCP, and Knowledge resources, remove remaining scopes compatibility paths, and move Trace to the first system governance item.

**Architecture:** Keep FastAPI Users as identity and Agno AgentOS scopes as authorization. Store visibility in each resource's native source of truth: Skill front matter, MCP JSON config entries, and Knowledge metadata. Add small shared helpers for visibility normalization/ownership checks so routes and services do not duplicate policy logic.

**Tech Stack:** FastAPI, Pydantic, FastAPI Users, Agno AgentOS scopes/JWT middleware, Vue 3, Pinia, Element Plus, `uv`, `ruff`, `ty`, `pytest`, `bun`.

## Global Constraints

- WSL2 Ubuntu 24.04 environment.
- Python commands run through `uv run`.
- Python formatting/static checks use `uv run ruff check <file_name>` and `uv run ty check <file_name>`.
- Backend tests use `pytest`.
- Frontend verification uses `cd frontend && bun run test:shell`, `cd frontend && bun run test:auth`, and `cd frontend && bun run build`.
- Do not replace FastAPI Users.
- Do not add a new role, scope, or ACL framework.
- Do not broaden role scope grants in this slice.
- Do not preserve legacy MCP TOML migration behavior.
- Existing resources without visibility metadata are read as private.
- New resources default to private when visibility is omitted.
- Unknown client-supplied visibility values are rejected.

---

## File Structure

- Create `api/auth/visibility.py`: shared `ResourceVisibility`, normalization, read/manage predicates, and HTTP ownership error helpers.
- Modify `api/auth/claims.py`: remove `ScopeClaims.permissions`.
- Modify `api/auth/schemas.py`: remove `UserRead.permissions`.
- Modify `api/mcp/config.py`: remove TOML compatibility and persist visibility fields for `mcp_servers`.
- Modify `api/services/mcp_config_service.py`: upload visibility/owner metadata and add server visibility update/list filtering helpers.
- Modify `api/routes/mcp.py`: expose visible custom MCP servers and a visibility update endpoint.
- Modify `api/services/skill_service.py`: parse/write Skill front matter visibility and owner metadata, filter list results, and update visibility.
- Modify `api/routes/skills.py`: accept visibility on upload, filter by actor, and add visibility update endpoint.
- Modify `api/services/knowledge_document_service.py`: add visibility metadata helpers and projection fields.
- Modify `api/services/knowledge_service.py`: persist visibility, enforce public-or-owner list/search/delete/clear behavior, and update visibility through Agno `Knowledge.apatch_content`.
- Modify `api/routes/knowledge.py`: accept visibility on creation and add visibility update endpoint.
- Modify `frontend/src/lib/scopes.ts`, `frontend/src/types/index.ts`, `frontend/src/composables/useApi.ts`: scopes-only auth and visibility-aware API contracts.
- Modify `frontend/src/App.vue`, `frontend/src/modules/shellNavigation.test.mjs`: Trace default group order.
- Create `frontend/src/modules/resourceVisibility.ts`: shared frontend visibility options, validation, and next-state helper.
- Modify `frontend/src/components/Skills.vue`, `frontend/src/components/MCP.vue`, `frontend/src/components/Knowledge.vue`: visibility controls, badges, and update actions.
- Modify `frontend/src/i18n/locales/en-US.ts`, `frontend/src/i18n/locales/zh-CN.ts`: visibility labels and messages.
- Modify tests under `api/tests/` and `frontend/src/*.test.mjs` for behavior assertions.

---

### Task 1: Scopes-Only Claims and Trace Governance Defaults

**Files:**
- Modify: `api/auth/claims.py`
- Modify: `api/auth/schemas.py`
- Modify: `api/tests/test_rbac_permissions.py`
- Modify: `frontend/src/lib/scopes.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/modules/shellNavigation.test.mjs`
- Modify: `frontend/src/App.vue`

**Interfaces:**
- Produces: `ScopeClaims(role: Role, scopes: list[str])` with no `permissions` property.
- Produces: frontend `ScopeUser` and `AuthUser` with `scopes?: readonly string[]` only.
- Produces: default sidebar groups where governance starts with `trace`.

- [ ] **Step 1: Write failing backend auth tests**

In `api/tests/test_rbac_permissions.py`, replace compatibility assertions with scopes-only behavior:

```python
def test_scope_claims_are_expanded_as_agentos_scopes():
    user_claims = scope_claims(user("user"))

    assert user_claims.role == "user"
    assert "sessions:read" in user_claims.scopes
    assert "evals:read" in user_claims.scopes
    assert not hasattr(user_claims, "permissions")


def test_user_read_serializes_scopes_without_permissions_alias():
    from api.auth.schemas import UserRead

    payload = UserRead(
        id=uuid4(),
        email="admin@example.com",
        role="admin",
        is_active=True,
        is_superuser=True,
        is_verified=False,
    ).model_dump()

    assert payload["scopes"] == [ADMIN_SCOPE]
    assert "permissions" not in payload
```

- [ ] **Step 2: Write failing frontend scope/navigation tests**

In `frontend/src/modules/shellNavigation.test.mjs`, change `permissions` fixtures to `scopes` and add a default group assertion:

```js
assert.equal(
  hasUserScope({ role: "guest", scopes: ["evals:read"] }, "evals:read"),
  true,
  "frontend scope checks must use server-issued scope claims",
)

assert.equal(
  hasUserScope({ role: "user", scopes: ["sessions:read"] }, "evals:read"),
  false,
  "frontend scope checks must not re-grant missing scopes when claims are present",
)

assert.equal(
  hasUserScope({ role: "guest", scopes: ["agent_os:admin"] }, "config:write"),
  true,
  "frontend scope checks must honor AgentOS admin scope claims",
)
```

Update the default group fixture in the existing `buildSidebarNavGroups` test:

```js
defaultGroups: [
  { key: "operations", ids: ["home", "dashboard", "chat", "workflow"] },
  { key: "knowledge", ids: ["skills", "mcp", "knowledge", "memory"] },
  { key: "governance", ids: ["trace", "evaluation", "approvals", "scheduler"] },
  { key: "securityData", ids: ["cve", "collect"] },
  { key: "settings", ids: ["settings"] },
],
```

- [ ] **Step 3: Run failing tests**

Run:

```bash
pytest api/tests/test_rbac_permissions.py -q
cd frontend && bun run test:shell
```

Expected: backend fails on `permissions` still being present; frontend fails because `permissions` fixtures no longer match the implementation and Trace is still in operations defaults.

- [ ] **Step 4: Implement scopes-only claims**

In `api/auth/claims.py`, delete the `permissions` property from `ScopeClaims`.

In `api/auth/schemas.py`, delete:

```python
    @computed_field
    @property
    def permissions(self) -> list[str]:
        return scope_claims(self).permissions
```

In `frontend/src/lib/scopes.ts`, change the type and lookup:

```ts
export type ScopeUser = {
  role?: UserRole
  is_superuser?: boolean
  scopes?: readonly string[]
}

export const hasUserScope = (
  user: ScopeUser | null | undefined,
  permission: string,
) => {
  const scopes = user?.scopes
  if (scopes) {
    return scopes.includes(ADMIN_SCOPE) || scopes.includes(permission)
  }
  return hasRoleScope(userRole(user), permission)
}
```

In `frontend/src/types/index.ts`, remove `permissions?: string[]` from `AuthUser`.

- [ ] **Step 5: Implement Trace governance defaults**

In `frontend/src/App.vue`, change `defaultSidebarNavGroupIds` to:

```ts
const defaultSidebarNavGroupIds: Array<{ key: SidebarNavGroupKey; ids: NavId[] }> = [
  { key: "operations", ids: ["home", "dashboard", "chat", "workflow"] },
  { key: "knowledge", ids: ["skills", "mcp", "knowledge", "memory"] },
  { key: "governance", ids: ["trace", "evaluation", "approvals", "scheduler"] },
  { key: "securityData", ids: ["cve", "collect"] },
  { key: "settings", ids: ["settings"] },
]
```

- [ ] **Step 6: Verify Task 1**

Run:

```bash
uv run ruff check api/auth/claims.py api/auth/schemas.py api/tests/test_rbac_permissions.py
uv run ty check api/auth/claims.py api/auth/schemas.py
pytest api/tests/test_rbac_permissions.py -q
cd frontend && bun run test:shell
```

Expected: all commands pass.

---

### Task 2: Shared Visibility Policy

**Files:**
- Create: `api/auth/visibility.py`
- Test: `api/tests/test_resource_visibility.py`

**Interfaces:**
- Produces: `ResourceVisibility = Literal["private", "public"]`
- Produces: `normalize_visibility(value: str | None, *, strict: bool = False) -> ResourceVisibility`
- Produces: `visibility_metadata(visibility: str | None, owner_user_id: str | None) -> dict[str, str]`
- Produces: `metadata_visibility(metadata: Mapping[str, Any]) -> ResourceVisibility`
- Produces: `metadata_owner_user_id(metadata: Mapping[str, Any]) -> str`
- Produces: `can_read_resource(user: Any, metadata: Mapping[str, Any]) -> bool`
- Produces: `can_manage_resource(user: Any, metadata: Mapping[str, Any]) -> bool`

- [ ] **Step 1: Write failing visibility tests**

Create `api/tests/test_resource_visibility.py`:

```python
from types import SimpleNamespace
from uuid import uuid4

import pytest

from api.auth.visibility import (
    can_manage_resource,
    can_read_resource,
    metadata_visibility,
    normalize_visibility,
    visibility_metadata,
)


def actor(actor_id: str, role: str = "user", is_superuser: bool = False):
    return SimpleNamespace(id=actor_id, role=role, is_superuser=is_superuser)


def test_visibility_normalizes_missing_values_to_private():
    assert normalize_visibility(None) == "private"
    assert normalize_visibility("") == "private"
    assert metadata_visibility({}) == "private"
    assert metadata_visibility({"visibility": "unexpected"}) == "private"


def test_visibility_rejects_unknown_client_values():
    with pytest.raises(ValueError):
        normalize_visibility("shared", strict=True)


def test_visibility_metadata_includes_owner_when_present():
    assert visibility_metadata("public", "u1") == {
        "visibility": "public",
        "owner_user_id": "u1",
        "user_id": "u1",
    }


def test_public_read_and_owner_admin_manage_rules():
    owner = actor("u1")
    other = actor("u2")
    admin = actor(str(uuid4()), role="admin", is_superuser=True)
    public = {"visibility": "public", "owner_user_id": "u1"}
    private = {"visibility": "private", "owner_user_id": "u1"}

    assert can_read_resource(other, public)
    assert can_read_resource(owner, private)
    assert not can_read_resource(other, private)
    assert can_read_resource(admin, private)

    assert can_manage_resource(owner, public)
    assert can_manage_resource(admin, public)
    assert not can_manage_resource(other, public)
```

- [ ] **Step 2: Run failing test**

Run:

```bash
pytest api/tests/test_resource_visibility.py -q
```

Expected: fails because `api.auth.visibility` does not exist.

- [ ] **Step 3: Implement visibility helper**

Create `api/auth/visibility.py`:

```python
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from api.auth.claims import ADMIN_SCOPE, actor_id, has_scope

ResourceVisibility = Literal["private", "public"]
VALID_VISIBILITIES: set[str] = {"private", "public"}


def normalize_visibility(value: str | None, *, strict: bool = False) -> ResourceVisibility:
    raw = (value or "").strip().lower()
    if not raw:
        return "private"
    if raw in VALID_VISIBILITIES:
        return raw  # type: ignore[return-value]
    if strict:
        raise ValueError("visibility must be private or public")
    return "private"


def visibility_metadata(
    visibility: str | None,
    owner_user_id: str | None,
) -> dict[str, str]:
    clean_owner = (owner_user_id or "").strip()
    metadata = {"visibility": normalize_visibility(visibility)}
    if clean_owner:
        metadata["owner_user_id"] = clean_owner
        metadata["user_id"] = clean_owner
    return metadata


def metadata_visibility(metadata: Mapping[str, Any]) -> ResourceVisibility:
    return normalize_visibility(str(metadata.get("visibility") or ""))


def metadata_owner_user_id(metadata: Mapping[str, Any]) -> str:
    return str(metadata.get("owner_user_id") or metadata.get("user_id") or "").strip()


def _is_admin(user: Any) -> bool:
    return bool(user is not None and has_scope(user, ADMIN_SCOPE))


def can_read_resource(user: Any, metadata: Mapping[str, Any]) -> bool:
    if _is_admin(user):
        return True
    if metadata_visibility(metadata) == "public":
        return True
    return bool(user is not None and metadata_owner_user_id(metadata) == actor_id(user))


def can_manage_resource(user: Any, metadata: Mapping[str, Any]) -> bool:
    if _is_admin(user):
        return True
    return bool(user is not None and metadata_owner_user_id(metadata) == actor_id(user))
```

- [ ] **Step 4: Verify Task 2**

Run:

```bash
uv run ruff check api/auth/visibility.py api/tests/test_resource_visibility.py
uv run ty check api/auth/visibility.py
pytest api/tests/test_resource_visibility.py -q
```

Expected: all commands pass.

---

### Task 3: MCP JSON-Only Config and Server Visibility

**Files:**
- Modify: `api/mcp/config.py`
- Modify: `api/services/mcp_config_service.py`
- Modify: `api/routes/mcp.py`
- Modify: `api/tests/test_mcp_config_service.py`

**Interfaces:**
- Produces: MCP server entries with `visibility`, `owner_user_id`.
- Produces: `visible_mcp_servers(entries: Any, user: Any) -> list[dict[str, Any]]`
- Produces: `apply_mcp_server_visibility(name: str, visibility: str, user: Any) -> McpConfigChange`

- [ ] **Step 1: Write failing MCP tests**

Update `api/tests/test_mcp_config_service.py`:

```python
def test_apply_mcp_upload_persists_visibility_and_owner_metadata():
    stored = {"mcp_servers": []}
    writes: list[dict] = []
    manifest = '{"mcpServers":{"tool":{"command":"python"}}}'
    actor = type("Actor", (), {"id": "u1", "role": "user", "is_superuser": False})()
    with (
        patch.object(mcp_config_service, "read_mcp_config", return_value=stored),
        patch.object(mcp_config_service, "write_mcp_config", side_effect=writes.append),
    ):
        change = mcp_config_service.apply_mcp_upload(
            name="Tool",
            manifest=manifest,
            visibility="public",
            owner_user_id=str(actor.id),
        )

    assert writes[0]["mcp_servers"][0]["visibility"] == "public"
    assert writes[0]["mcp_servers"][0]["owner_user_id"] == "u1"
    assert change.metadata == {
        "kind": "mcp-json",
        "has_manifest": True,
        "visibility": "public",
    }


def test_mcp_config_is_json_only_and_ignores_legacy_toml(tmp_path, monkeypatch):
    config_file = tmp_path / "mcp_config.json"
    legacy_file = tmp_path / "mcp_config.toml"
    legacy_file.write_text("[mcp]\nplaybook = false\n", encoding="utf-8")
    monkeypatch.setattr(mcp_config, "MCP_DATA_DIR", tmp_path)
    monkeypatch.setattr(mcp_config, "MCP_CONFIG_FILE", config_file)

    assert mcp_config.read_mcp_config() == {
        "mcp": {"playbook": True, "basic": True},
        "mcp_servers": [],
    }
    assert not config_file.exists()
```

- [ ] **Step 2: Run failing MCP tests**

Run:

```bash
pytest api/tests/test_mcp_config_service.py -q
```

Expected: fails because `apply_mcp_upload` does not accept visibility/owner and legacy TOML is still migrated.

- [ ] **Step 3: Implement JSON-only config normalization**

In `api/mcp/config.py`:

- Remove `import tomllib`.
- Remove `_legacy_mcp_config_file()` and `_read_legacy_mcp_config()`.
- In `read_mcp_config()`, return `_default_config()` when JSON is absent.
- In `normalize_mcp_servers()`, include:

```python
"visibility": normalize_visibility(str(entry.get("visibility") or "")),
"owner_user_id": str(entry.get("owner_user_id") or entry.get("user_id") or "").strip(),
```

Import `normalize_visibility` from `api.auth.visibility`.

- [ ] **Step 4: Implement MCP visibility service functions**

In `api/services/mcp_config_service.py`, update `apply_mcp_upload` signature:

```python
def apply_mcp_upload(
    *,
    name: str,
    description: str = "",
    manifest: str = "",
    enabled: bool = True,
    visibility: str = "private",
    owner_user_id: str | None = None,
) -> McpConfigChange:
```

Normalize visibility with `normalize_visibility(visibility, strict=True)`, store `visibility` and `owner_user_id`, and include visibility in audit metadata.

Add:

```python
def visible_mcp_servers(entries: Any, user: Any) -> list[dict[str, Any]]:
    return [
        entry
        for entry in normalize_mcp_servers(entries)
        if can_read_resource(user, entry)
    ]


def apply_mcp_server_visibility(
    name: str,
    visibility: str,
    user: Any,
) -> McpConfigChange:
    normalized_visibility = normalize_visibility(visibility, strict=True)
    data = read_mcp_config()
    servers = normalize_mcp_servers(data.get("mcp_servers", []))
    for entry in servers:
        if entry["name"] != name:
            continue
        if not can_manage_resource(user, entry):
            raise HTTPException(status_code=403, detail="MCP server is not manageable")
        entry["visibility"] = normalized_visibility
        data["mcp_servers"] = servers
        write_mcp_config(data)
        return McpConfigChange(
            response={"success": True, "name": name, "visibility": normalized_visibility},
            action="mcp.visibility_update",
            resource_type="mcp",
            resource_id=name,
            metadata={"visibility": normalized_visibility},
        )
    raise HTTPException(status_code=404, detail="MCP server not found")
```

- [ ] **Step 5: Update MCP routes**

In `api/routes/mcp.py`:

- Add `visibility: str = "private"` to `McpUploadRequest`.
- Add `McpVisibilityRequest` with `visibility: str`.
- Return `"mcp_servers": visible_mcp_servers(data.get("mcp_servers", []), user)` from `get_config`.
- Pass `visibility=body.visibility` and `owner_user_id=actor_id(user)` into `apply_mcp_upload`.
- Add `PUT /api/mcp/servers/{server_name}/visibility` calling `apply_mcp_server_visibility`.

- [ ] **Step 6: Verify Task 3**

Run:

```bash
uv run ruff check api/mcp/config.py api/services/mcp_config_service.py api/routes/mcp.py api/tests/test_mcp_config_service.py
uv run ty check api/mcp/config.py api/services/mcp_config_service.py api/routes/mcp.py
pytest api/tests/test_mcp_config_service.py -q
```

Expected: all commands pass.

---

### Task 4: Skill Visibility

**Files:**
- Modify: `api/services/skill_service.py`
- Modify: `api/routes/skills.py`
- Test: `api/tests/test_skill_visibility.py`

**Interfaces:**
- Produces: `list_skill_infos(user: Any | None = None) -> list[SkillInfoData]`
- Produces: `install_skill_archive(..., visibility: str = "private", owner_user_id: str | None = None) -> tuple[str, str, Path]`
- Produces: `set_skill_visibility(skill_name: str, visibility: str, user: Any) -> tuple[str, str]`
- Skill info includes `visibility`, `owner_user_id`, `can_manage`.

- [ ] **Step 1: Write failing Skill visibility tests**

Create `api/tests/test_skill_visibility.py` with temporary skills dir/config:

```python
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.services import skill_service


def actor(actor_id: str, role: str = "user", is_superuser: bool = False):
    return SimpleNamespace(id=actor_id, role=role, is_superuser=is_superuser)


def write_skill(root: Path, dirname: str, *, name: str, visibility: str = "private", owner: str = "u1"):
    skill_dir = root / dirname
    skill_dir.mkdir()
    skill_dir.joinpath("SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test\nvisibility: {visibility}\nowner_user_id: {owner}\n---\nBody\n",
        encoding="utf-8",
    )
    return skill_dir


def test_list_skill_infos_filters_public_and_owned_private(tmp_path, monkeypatch):
    monkeypatch.setattr(skill_service, "get_skills_dir", lambda: tmp_path)
    monkeypatch.setattr(skill_service, "load_skills_config", lambda: {})
    write_skill(tmp_path, "owned", name="Owned", visibility="private", owner="u1")
    write_skill(tmp_path, "foreign", name="Foreign", visibility="private", owner="u2")
    write_skill(tmp_path, "public", name="Public", visibility="public", owner="u2")

    names = [item["name"] for item in skill_service.list_skill_infos(actor("u1"))]

    assert names == ["Owned", "Public"]


def test_set_skill_visibility_requires_owner_or_admin(tmp_path, monkeypatch):
    cfg: dict[str, bool] = {}
    monkeypatch.setattr(skill_service, "get_skills_dir", lambda: tmp_path)
    monkeypatch.setattr(skill_service, "load_skills_config", lambda: cfg)
    write_skill(tmp_path, "owned", name="Owned", visibility="private", owner="u1")

    public_name, visibility = skill_service.set_skill_visibility("Owned", "public", actor("u1"))

    assert public_name == "Owned"
    assert visibility == "public"
    assert "visibility: public" in (tmp_path / "owned" / "SKILL.md").read_text(encoding="utf-8")
    with pytest.raises(PermissionError):
        skill_service.set_skill_visibility("Owned", "private", actor("u2"))
```

- [ ] **Step 2: Run failing Skill tests**

Run:

```bash
pytest api/tests/test_skill_visibility.py -q
```

Expected: fails because Skill visibility functions do not exist.

- [ ] **Step 3: Implement Skill metadata parsing/writing**

In `api/services/skill_service.py`:

- Extend `SkillInfoData` with `visibility: str`, `owner_user_id: str`, `can_manage: bool`.
- Change `parse_skill_metadata(skill_dir: Path)` to return a dict or dataclass containing `name`, `description`, `visibility`, `owner_user_id`.
- Add a helper that rewrites YAML front matter preserving the body:

```python
def write_skill_metadata(skill_dir: Path, updates: dict[str, str]) -> None:
    md_path = skill_dir / "SKILL.md"
    raw = md_path.read_text(encoding="utf-8")
    body = raw
    meta: dict[str, object] = {}
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            meta = yaml.safe_load(parts[1]) or {}
            body = parts[2].lstrip("\n")
    meta.update(updates)
    md_path.write_text(
        "---\n" + yaml.safe_dump(meta, sort_keys=False, allow_unicode=True) + "---\n" + body,
        encoding="utf-8",
    )
```

- [ ] **Step 4: Implement Skill filtering and mutation**

Update `list_skill_infos(user: Any | None = None)` to skip resources where `not can_read_resource(user, metadata)`. Compute `can_manage` from `can_manage_resource`.

Update `set_skill_enabled(skill_name, enabled, user=None)` to enforce `can_manage_resource` when `user` is passed.

Update `install_skill_archive` to accept `visibility` and `owner_user_id`, validate visibility, move the Skill, then call `write_skill_metadata(dest, visibility_metadata(...))`.

Add `set_skill_visibility(skill_name, visibility, user)`.

- [ ] **Step 5: Update Skill routes**

In `api/routes/skills.py`:

- Add fields to `SkillInfo`: `visibility`, `owner_user_id`, `can_manage`.
- Add `visibility: str = Form("private")` to upload route.
- Pass `user` to `list_skill_infos(user)`, `set_skill_enabled(..., user)`, and upload owner metadata.
- Add `SkillVisibilityRequest` and `PUT /api/skills/{skill_name}/visibility`.

- [ ] **Step 6: Verify Task 4**

Run:

```bash
uv run ruff check api/services/skill_service.py api/routes/skills.py api/tests/test_skill_visibility.py
uv run ty check api/services/skill_service.py api/routes/skills.py
pytest api/tests/test_skill_visibility.py -q
```

Expected: all commands pass.

---

### Task 5: Knowledge Visibility

**Files:**
- Modify: `api/services/knowledge_document_service.py`
- Modify: `api/services/knowledge_service.py`
- Modify: `api/routes/knowledge.py`
- Modify: `api/tests/test_knowledge_pipeline.py`

**Interfaces:**
- Produces: `owner_metadata(owner_user_id: str | None, visibility: str = "private") -> dict[str, str]`
- Produces: `content_visible_to_actor(content: Any, user: Any | None) -> bool`
- Produces: Knowledge create requests with `visibility: str = "private"`.
- Produces: `KnowledgeBaseLifecycle.update_document_visibility_async(doc_id, visibility, user) -> dict[str, Any] | None` using Agno `Knowledge.apatch_content(Content(id=..., metadata=...))`.

- [ ] **Step 1: Write failing Knowledge tests**

Update `api/tests/test_knowledge_pipeline.py`:

```python
def test_public_visibility_allows_foreign_knowledge_read() -> None:
    public = SimpleNamespace(metadata={"user_id": "u2", "visibility": "public"})
    private = SimpleNamespace(metadata={"user_id": "u2", "visibility": "private"})

    assert knowledge_document_service.content_visible_to_owner(public, "u1")
    assert not knowledge_document_service.content_visible_to_owner(private, "u1")


@pytest.mark.asyncio
async def test_search_documents_merges_public_and_owner_private_filters() -> None:
    calls: list[dict[str, object]] = []

    async def noop() -> None:
        return None

    async def hydrate_noop(_documents) -> None:
        return None

    def search_callback(*_args: object, **kwargs: object):
        calls.append(kwargs)
        return []

    lifecycle = knowledge_service.KnowledgeBaseLifecycle(
        knowledge_service.KnowledgeBaseLifecycleDependencies(
            get_async_knowledge_base=lambda _search_type=None: StrictAsyncKnowledge(search_callback=search_callback),
            ensure_storage_async=noop,
            hydrate_content_ids_async=hydrate_noop,
        )
    )

    await lifecycle.search_documents_async("policy", 5, owner_user_id="u1")

    assert {"filters": {"visibility": "public"}} in calls
    assert {"filters": {"user_id": "u1", "visibility": "private"}} in calls
```

- [ ] **Step 2: Run failing Knowledge tests**

Run:

```bash
pytest api/tests/test_knowledge_pipeline.py -q
```

Expected: visibility tests fail because public visibility is not recognized and search uses one owner filter.

- [ ] **Step 3: Implement Knowledge metadata visibility**

In `api/services/knowledge_document_service.py`:

- Add `"visibility"` and `"owner_user_id"` to `DOCUMENT_METADATA_KEYS`.
- Update `owner_metadata(owner_user_id, visibility="private")` to return visibility metadata.
- Update `content_visible_to_owner` so public content is visible to any non-empty owner filter.
- Update `content_to_document` to include top-level `"visibility": metadata_visibility(metadata)`.
- Update `result_from_document` to include visibility in metadata naturally.

- [ ] **Step 4: Persist visibility on Knowledge creation**

In `api/services/knowledge_service.py`:

- Add `visibility: str = "private"` to `add_text_document_async` and `add_file_document_async`.
- Pass `visibility` to `_owner_metadata(owner_user_id, visibility)`.
- Validate client values with `normalize_visibility(..., strict=True)` before insert.

Update module-level wrapper functions with the same parameter.

- [ ] **Step 5: Implement public-or-owner list/search behavior**

Keep `owner_user_id=None` as admin/all behavior.

For non-admin owner filters:

- `content_visible_to_owner` returns true for public or same owner.
- `search_documents_async` calls `knowledge.asearch` twice:
  - `filters={"visibility": "public"}`
  - `filters={"user_id": owner_user_id, "visibility": "private"}`
- Merge by `(document.content_id, document.name, document.content)`, sort by score metadata descending when present, and return `limit` results.

- [ ] **Step 6: Wire Knowledge visibility updates**

In `api/routes/knowledge.py`:

- Add `visibility: str = "private"` to `KnowledgeTextRequest` and `KnowledgeFileRequest`.
- Pass `request.visibility` into service creation calls.
- Add `KnowledgeVisibilityRequest`.
- In `KnowledgeBaseLifecycle`, add `update_document_visibility_async(doc_id, visibility, user)`:
  - Load the content by id.
  - Return `None` if missing or `not can_manage_resource(user, metadata)`.
  - Patch metadata through `await knowledge.apatch_content(Content(id=doc_id, metadata={"visibility": normalized_visibility}))`.
  - Return the updated document projection.
- Add `PUT /api/knowledge/documents/{doc_id}/visibility` and return 404 when the lifecycle returns `None`.

- [ ] **Step 7: Verify Task 5**

Run:

```bash
uv run ruff check api/services/knowledge_document_service.py api/services/knowledge_service.py api/routes/knowledge.py api/tests/test_knowledge_pipeline.py
uv run ty check api/services/knowledge_document_service.py api/services/knowledge_service.py api/routes/knowledge.py
pytest api/tests/test_knowledge_pipeline.py -q
```

Expected: all commands pass.

---

### Task 6: Frontend Visibility UI and API Contracts

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/composables/useApi.ts`
- Create: `frontend/src/modules/resourceVisibility.ts`
- Test: `frontend/src/modules/resourceVisibility.test.mjs`
- Modify: `frontend/src/components/Skills.vue`
- Modify: `frontend/src/components/MCP.vue`
- Modify: `frontend/src/components/Knowledge.vue`
- Modify: `frontend/src/i18n/locales/en-US.ts`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/uiShell.test.mjs`

**Interfaces:**
- Produces: `type ResourceVisibility = "private" | "public"`.
- Produces: `resourceVisibilityOptions`, `normalizeResourceVisibility`, and `nextResourceVisibility`.
- Produces: upload payloads include `visibility`.
- Produces: `updateSkillVisibility`, `updateMcpServerVisibility`, `updateKnowledgeDocumentVisibility`.

- [ ] **Step 1: Write failing frontend visibility module tests**

Create `frontend/src/modules/resourceVisibility.test.mjs`:

```js
import assert from "node:assert/strict"
import {
  nextResourceVisibility,
  normalizeResourceVisibility,
  resourceVisibilityOptions,
} from "./resourceVisibility.ts"

assert.equal(normalizeResourceVisibility(undefined), "private")
assert.equal(normalizeResourceVisibility("public"), "public")
assert.equal(normalizeResourceVisibility("private"), "private")
assert.equal(normalizeResourceVisibility("unexpected"), "private")
assert.equal(nextResourceVisibility("private"), "public")
assert.equal(nextResourceVisibility("public"), "private")
assert.deepEqual(
  resourceVisibilityOptions.map((option) => option.value),
  ["private", "public"],
)
```

- [ ] **Step 2: Run failing frontend tests**

Run:

```bash
cd frontend && bun run test:shell
```

Expected: fails because `frontend/src/modules/resourceVisibility.ts` does not exist and `uiShell.test.mjs` imports every module test.

- [ ] **Step 3: Add frontend visibility module, types, and API composables**

Create `frontend/src/modules/resourceVisibility.ts`:

```ts
import type { ResourceVisibility } from "../types"

export const resourceVisibilityOptions: Array<{ labelKey: string; value: ResourceVisibility }> = [
  { labelKey: "visibility.private", value: "private" },
  { labelKey: "visibility.public", value: "public" },
]

export const normalizeResourceVisibility = (value: unknown): ResourceVisibility => {
  return value === "public" || value === "private" ? value : "private"
}

export const nextResourceVisibility = (value: ResourceVisibility): ResourceVisibility => {
  return value === "public" ? "private" : "public"
}
```

In `frontend/src/types/index.ts`:

```ts
export type ResourceVisibility = "private" | "public"
```

Add `visibility`, `owner_user_id`, `can_manage` to `SkillInfo` and `KnowledgeDocument`. Add `mcp_servers` to `McpServiceStatusResponse` using a new `McpServerInfo`.

In `frontend/src/composables/useApi.ts`:

- `uploadSkill(payload: { name: string; file: File; visibility: ResourceVisibility })` appends visibility to `FormData`.
- `uploadMcp(payload)` sends `visibility`.
- Knowledge requests include `visibility`.
- Add update visibility methods for Skill/MCP/Knowledge.

- [ ] **Step 4: Add Skill visibility UI**

In `Skills.vue`:

- Add `visibility: "private"` to `uploadForm`.
- Add an `el-segmented` or `el-radio-group` with private/public choices in the upload panel.
- Include `visibility` in upload payload.
- Show a badge on each skill card.
- Add a small visibility toggle action disabled when `!skill.can_manage`.

- [ ] **Step 5: Add MCP custom server visibility UI**

In `MCP.vue`:

- Add `visibility: "private"` to `uploadForm`.
- Include selector in upload panel.
- Store `mcpServers` from config response.
- Add a `servers` tab or section under services showing uploaded MCP servers with visibility badges and toggle actions.

- [ ] **Step 6: Add Knowledge visibility UI**

In `Knowledge.vue`:

- Add `visibility: "private"` to `browserForm`, `textForm`, and `pathForm`.
- Add selectors to all three creation forms.
- Include visibility in create requests.
- Show document visibility in the document table and metadata drawer.
- Add a visibility toggle action when `row.can_manage`.

- [ ] **Step 7: Add i18n labels**

Add English and Chinese keys under common or each module:

```ts
visibility: {
  label: "Visibility",
  private: "Private",
  public: "Public",
  updated: "Visibility updated",
  updateFailed: "Failed to update visibility",
}
```

Use Chinese equivalents in `zh-CN.ts`.

- [ ] **Step 8: Verify Task 6**

Run:

```bash
cd frontend && bun run test:shell
cd frontend && bun run test:auth
cd frontend && bun run build
```

Expected: all commands pass.

---

### Task 7: Integration Verification and Smoke Test

**Files:**
- Potentially modify: any file found by verification failures.

**Interfaces:**
- Produces: passing backend/frontend checks.
- Produces: preflight server running on `http://localhost:8001`.

- [ ] **Step 1: Run Python focused checks**

Run:

```bash
uv run ruff check api/auth/claims.py api/auth/schemas.py api/auth/visibility.py api/mcp/config.py api/services/mcp_config_service.py api/routes/mcp.py api/services/skill_service.py api/routes/skills.py api/services/knowledge_document_service.py api/services/knowledge_service.py api/routes/knowledge.py
uv run ty check api/auth/claims.py api/auth/schemas.py api/auth/visibility.py api/mcp/config.py api/services/mcp_config_service.py api/routes/mcp.py api/services/skill_service.py api/routes/skills.py api/services/knowledge_document_service.py api/services/knowledge_service.py api/routes/knowledge.py
```

Expected: both commands pass.

- [ ] **Step 2: Run full backend tests**

Run:

```bash
pytest
```

Expected: all backend tests pass.

- [ ] **Step 3: Run full frontend checks**

Run:

```bash
cd frontend && bun run test:shell
cd frontend && bun run test:auth
cd frontend && bun run build
```

Expected: all frontend checks pass.

- [ ] **Step 4: Start preflight server**

Run:

```bash
AGNO_BOOTSTRAP_ADMIN_EMAIL=admin@example.com AGNO_BOOTSTRAP_ADMIN_PASSWORD='AdminPass123!' uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
```

Expected: server starts and listens on port `8001`.

- [ ] **Step 5: Smoke test admin auth and protected APIs**

From another shell while the server runs:

```bash
TOKEN=$(curl -s -X POST http://localhost:8001/api/auth/jwt/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'username=admin@example.com&password=AdminPass123!' | jq -r .access_token)
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8001/api/auth/users/me | jq '{email, scopes, permissions}'
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8001/api/mcp/config | jq '{services, mcp_servers}'
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8001/api/skills | jq '.skills[0] // {}'
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8001/api/knowledge | jq '{status, documents: (.documents | length)}'
```

Expected:

- `/api/auth/users/me` contains `scopes` and no `permissions`.
- MCP config includes `mcp_servers`.
- Skill records include `visibility` and `can_manage`.
- Knowledge documents include visibility metadata when records exist.

- [ ] **Step 6: Commit implementation**

Run:

```bash
git status --short
git add api frontend docs/superpowers/plans/2026-07-07-native-visibility-and-governance-implementation.md
git commit -m "feat: add native resource visibility"
```

Expected: commit succeeds.

---

## Self-Review

- Spec coverage: Tasks cover scopes-only auth, JSON-only MCP, Trace governance order, Skill/MCP/Knowledge create-time visibility, post-create visibility update routes, frontend controls, and verification.
- Compatibility policy: The plan removes `permissions` alias/fallback and TOML migration instead of preserving compatibility shims.
- Type consistency: Visibility values use `private | public` consistently across backend metadata, API models, frontend types, and UI forms.
- Knowledge post-create visibility updates use Agno `Knowledge.apatch_content`, which updates the contents DB and vector metadata for the content id.
