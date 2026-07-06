# API Sync-First Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove async service wrappers that do not perform native async work while preserving event-loop safety for blocking operations.

**Architecture:** AIOS local config, permissions, parsing, projection, and metadata scanning become synchronous service APIs. Agno Runtime, async SQLAlchemy, async HTTP, streaming, ASGI, WebSocket, and DB audit paths remain async. Expensive synchronous work is either executed from a synchronous boundary or isolated locally at the async boundary, not hidden behind public async service facades.

**Tech Stack:** Python 3, FastAPI, Agno, async SQLAlchemy, AnyIO, pytest, ruff, ty.

## Global Constraints

- Do not convert Agno Runtime APIs to sync.
- Do not introduce a new allowlist system for fake async functions.
- Do not replace async SQLAlchemy persistence with sync SQLAlchemy.
- Do not remove blocking isolation where removal would move large sync work onto the event loop.
- Do not redesign the UI or product API shapes in this cleanup.
- Use `uv run python` for Python execution.
- Validate with `uv run pytest api/tests`, `uv run ruff check .`, and `uv run ty check .`.

---

### Task 1: Flip Boundary Tests To Sync-First

**Files:**
- Modify: `api/tests/test_postgres_sql_templates.py`
- Modify: `api/tests/test_settings_model_connectivity.py`

**Interfaces:**
- Consumes: existing modules `api.routes.settings`, `api.routes.mcp`, `api.routes.skills`, `api.services.model_config_service`, `api.services.skill_service`, `api.services.security_run_runtime`.
- Produces: failing tests that require sync local config APIs and preserve blocking isolation where needed.

- [ ] **Step 1: Replace file-backed async wrapper assertions**

Update `test_file_backed_config_routes_use_async_wrappers` into `test_local_config_services_are_sync_first_without_blocking_event_loop_regressions` with assertions shaped like:

```python
def test_local_config_services_are_sync_first_without_blocking_event_loop_regressions() -> None:
    settings_source = inspect.getsource(settings_route)
    assert "public_model_config()" in settings_source
    assert "save_model_config(" in settings_source
    assert "load_model_config(" in settings_source
    assert "public_model_config_async" not in settings_source
    assert "save_model_config_async" not in settings_source
    assert "load_model_config_async" not in settings_source

    skills_source = inspect.getsource(skills_route)
    assert "list_skill_infos()" in skills_source
    assert "set_skill_enabled(" in skills_source
    assert "install_skill_archive_async" not in skills_source

    mcp_source = inspect.getsource(mcp_route)
    assert "services_from_config(" in mcp_source
    assert "services_from_config_async" not in mcp_source
    assert "await apply_service_toggle_async" in mcp_source
    assert "await apply_mcp_upload_async" in mcp_source

    assert hasattr(model_config_service, "load_model_config")
    assert hasattr(model_config_service, "public_model_config")
    assert hasattr(model_config_service, "save_model_config")
    assert hasattr(model_config_service, "get_model_for_run")
    assert not hasattr(model_config_service, "load_model_config_async")
    assert not hasattr(model_config_service, "public_model_config_async")
    assert not hasattr(model_config_service, "save_model_config_async")
    assert not hasattr(model_config_service, "get_model_for_run_async")

    assert hasattr(skill_service, "load_skills_config")
    assert hasattr(skill_service, "save_skills_config")
    assert hasattr(skill_service, "list_skill_infos")
    assert hasattr(skill_service, "set_skill_enabled")
    assert hasattr(skill_service, "get_enabled_skill_dirs")
    assert not hasattr(skill_service, "list_skill_infos_async")
    assert not hasattr(skill_service, "set_skill_enabled_async")
    assert not hasattr(skill_service, "get_enabled_skill_dirs_async")

    runtime_source = inspect.getsource(security_run_runtime)
    assert "to_thread.run_sync(_load_local_skills" in runtime_source
    assert "get_enabled_skill_dirs" in runtime_source
```

- [ ] **Step 2: Update masked model secret test**

Replace the `AsyncMock` patch with a sync mock:

```python
with (
    patch.object(
        settings,
        "load_model_config",
        return_value={"models": [{"id": "m1", "api_key": "saved-secret"}]},
    ),
    patch.object(
        settings.httpx,
        "AsyncClient",
        return_value=FakeClient(FakeResponse(200, payload={"id": "ok"}), captured),
    ),
):
    result = await settings.run_model_connectivity_test(model)
```

Remove the unused `AsyncMock` import.

- [ ] **Step 3: Run RED tests**

Run:

```bash
uv run pytest api/tests/test_postgres_sql_templates.py::test_local_config_services_are_sync_first_without_blocking_event_loop_regressions api/tests/test_settings_model_connectivity.py::test_masked_api_key_uses_saved_secret -q
```

Expected: fail because sync APIs and route calls do not exist yet.

---

### Task 2: Convert Permissions, Model Config, And MCP Config To Sync Core

**Files:**
- Modify: `api/auth/permissions.py`
- Modify: `api/routes/os_control.py`
- Modify: `api/services/model_config_service.py`
- Modify: `api/routes/settings.py`
- Modify: `api/mcp/config.py`
- Modify: `api/services/mcp_config_service.py`
- Modify: `api/routes/mcp.py`
- Modify: `api/mcp/server.py`
- Modify: `api/services/security_run_runtime.py`

**Interfaces:**
- Produces: `require_permission(permission: str) -> Callable[..., User]`
- Produces: `load_model_config_store() -> ModelConfigStore`
- Produces: `load_model_config() -> dict[str, Any]`
- Produces: `public_model_config() -> dict[str, Any]`
- Produces: `save_model_config(models, active_model_id) -> dict[str, Any]`
- Produces: `get_model_for_run(model_id: str | None = None) -> dict[str, Any]`
- Produces: `read_mcp_config() -> dict[str, Any]`
- Produces: `write_mcp_config(data: dict[str, Any]) -> None`
- Produces: `services_from_config(data: dict[str, Any] | None = None) -> dict[str, bool]`

- [ ] **Step 1: Implement sync model config service**

Remove `AsyncPath` from `api/services/model_config_service.py` and replace async functions with synchronous file APIs:

```python
def load_model_config_store() -> ModelConfigStore:
    config_file = model_config_file()
    if not config_file.exists():
        return ModelConfigStore.default()
    try:
        raw = json.loads(config_file.read_text(encoding="utf-8"))
    except Exception:
        return ModelConfigStore.default()
    return ModelConfigStore.from_raw(raw)
```

Use the same store helper for `load_model_config()`, `public_model_config()`, `save_model_config(...)`, and `get_model_for_run(...)`.

- [ ] **Step 2: Update settings route imports and calls**

Import sync functions:

```python
from api.services.model_config_service import (
    ModelConfig,
    ModelConfigUpdate,
    load_model_config,
    public_model_config,
    save_model_config,
)
```

Change `_resolve_model_secret()` to call `load_model_config()` directly while keeping `run_model_connectivity_test()` async because it awaits `httpx.AsyncClient`.

- [ ] **Step 3: Implement sync MCP config read/write and service projection**

In `api/mcp/config.py`, use `Path` for local config and keep token DB functions async:

```python
def read_mcp_config() -> dict[str, Any]:
    MCP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not MCP_CONFIG_FILE.exists():
        legacy_config = _read_legacy_mcp_config()
        return legacy_config if legacy_config is not None else _default_config()
    try:
        data = json.loads(MCP_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _default_config()
    if not isinstance(data, dict):
        return _default_config()
    return _normalize_mcp_config(data)
```

Add `services_from_config(data: dict[str, Any] | None = None) -> dict[str, bool]`.

- [ ] **Step 4: Update MCP callers**

Use sync local config APIs in routes/services. Keep `enabled_service_ids_async()` only if it is needed by async MCP runtime, implemented as a coroutine that calls the sync `services_from_config()` without blocking DB or large I/O.

- [ ] **Step 5: Convert permission dependency helpers**

Change `require_permission` to return a sync dependency and remove `Awaitable` import:

```python
def require_permission(permission: str) -> Callable[..., User]:
    def dependency(user: User = Depends(current_active_user)) -> User:
        if not has_permission(user, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return user

    return dependency
```

Apply the same pattern to no-await permission helpers in `api/routes/os_control.py`.

- [ ] **Step 6: Run GREEN tests for config and permissions**

Run:

```bash
uv run pytest api/tests/test_postgres_sql_templates.py::test_local_config_services_are_sync_first_without_blocking_event_loop_regressions api/tests/test_settings_model_connectivity.py -q
```

Expected: pass.

---

### Task 3: Convert Skill Service To Sync Core With Safe Blocking Boundary

**Files:**
- Modify: `api/services/skill_service.py`
- Modify: `api/routes/skills.py`
- Modify: `api/services/security_run_runtime.py`
- Test: `api/tests/test_postgres_sql_templates.py`

**Interfaces:**
- Produces: `load_skills_config() -> dict[str, bool]`
- Produces: `save_skills_config(cfg: dict[str, bool]) -> None`
- Produces: `iter_skill_dirs() -> list[Path]`
- Produces: `list_skill_scripts(skill_dir: Path) -> list[str]`
- Produces: `find_skill_dir(skill_name: str) -> Path | None`
- Produces: `list_skill_infos() -> list[SkillInfoData]`
- Produces: `set_skill_enabled(skill_name: str, enabled: bool) -> str`
- Produces: `get_enabled_skill_dirs() -> list[Path]`

- [ ] **Step 1: Replace async local file APIs with sync APIs**

Use `Path.exists()`, `Path.read_text()`, `Path.write_text()`, and `Path.iterdir()` in `api/services/skill_service.py`. Keep `install_skill_archive(...)` as the single install implementation.

- [ ] **Step 2: Update skills routes**

Make listing route synchronous:

```python
@router.get("", response_model=SkillListResponse)
def list_skills(_user: User = Depends(require_permission("skill:read"))):
    return SkillListResponse(skills=[SkillInfo(**item) for item in list_skill_infos()])
```

Keep routes that write async audit as async, but call sync Skill service functions directly. For upload, keep route-local blocking isolation only if the route remains async:

```python
public_name, description, dest = await to_thread.run_sync(
    partial(install_skill_archive, await file.read(), requested_name=name.strip())
)
```

- [ ] **Step 3: Update security runtime dependency**

Inject `get_enabled_skill_dirs` as a sync dependency and keep `to_thread.run_sync(_load_local_skills, enabled_dirs)` in `_build_enabled_skills()` as event-loop protection for LocalSkills construction.

- [ ] **Step 4: Run Skill boundary test**

Run:

```bash
uv run pytest api/tests/test_postgres_sql_templates.py::test_local_config_services_are_sync_first_without_blocking_event_loop_regressions -q
```

Expected: pass.

---

### Task 4: Full Verification And Cleanup

**Files:**
- Modify only files already changed by Tasks 1-3 unless verification exposes a direct issue.

**Interfaces:**
- Consumes: all sync-first APIs introduced above.
- Produces: verified implementation with no public fake-async local config wrappers.

- [ ] **Step 1: Search for removed async symbols**

Run:

```bash
rg -n "load_model_config_async|public_model_config_async|save_model_config_async|get_model_for_run_async|services_from_config_async|list_skill_infos_async|set_skill_enabled_async|get_enabled_skill_dirs_async|install_skill_archive_async" api
```

Expected: no production references. Test references may only assert absence.

- [ ] **Step 2: Run focused backend tests**

Run:

```bash
uv run pytest api/tests/test_settings_model_connectivity.py api/tests/test_postgres_sql_templates.py -q
```

Expected: pass.

- [ ] **Step 3: Run full backend tests**

Run:

```bash
uv run pytest api/tests
```

Expected: pass.

- [ ] **Step 4: Run lint and type checks**

Run:

```bash
uv run ruff check .
uv run ty check .
```

Expected: both pass.

- [ ] **Step 5: Review final diff**

Run:

```bash
git diff --stat
git diff -- api/auth/permissions.py api/routes/settings.py api/routes/mcp.py api/routes/skills.py api/mcp/config.py api/services/model_config_service.py api/services/mcp_config_service.py api/services/skill_service.py api/services/security_run_runtime.py api/tests/test_postgres_sql_templates.py api/tests/test_settings_model_connectivity.py
```

Expected: diff only implements sync-first simplification and boundary-safe blocking isolation.
