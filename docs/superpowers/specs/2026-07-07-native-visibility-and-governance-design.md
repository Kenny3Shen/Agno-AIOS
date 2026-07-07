# Native Visibility and Governance Design

Date: 2026-07-07

## Context

Agno AIOS has recently moved RBAC semantics toward Agno AgentOS scopes while
keeping FastAPI Users as the identity system. The current codebase still has a
few compatibility paths and incomplete resource visibility behavior:

- Auth responses still expose `permissions` as a compatibility alias for
  `scopes`, and the frontend still falls back from `scopes` to `permissions`.
- MCP config reads JSON but can still migrate old TOML config.
- Trace exists in the default Operations navigation group even though it belongs
  under system governance.
- Skill, MCP, and Knowledge resources do not have a consistent private/public
  visibility model that users can set on creation and change later.

Agno AgentOS authorization guidance uses JWT `scopes`, an `agent_os:admin`
admin scope, route scope checking, and user isolation semantics. This design
continues that direction and avoids adding an app-owned permission system.

## Decision

Implement native visibility support for Skill, MCP, and Knowledge resources
using each resource's source of truth. Do not add a separate ACL table.

Use `visibility: "private" | "public"` and `owner_user_id` on each managed
resource:

- `private`: readable and mutable only by the owner or an admin, subject to the
  existing AgentOS scope requirement for the endpoint.
- `public`: readable by any authenticated user with the corresponding read
  scope. Mutation still requires owner or admin plus the corresponding write or
  delete scope.

Creation forms must let the user choose private or public. If API callers omit
the field, the backend defaults to `private`.

## Goals

- Remove remaining compatibility code that conflicts with the native scopes
  model.
- Move Trace to the first item in the default system governance navigation
  group.
- Let users set private/public visibility when creating Skill, MCP, and
  Knowledge resources.
- Let authorized owners/admins change visibility after creation.
- Keep FastAPI Users for identity and Agno AgentOS scopes for authorization.
- Prefer behavior tests over source-string tests for the changed behavior.

## Non-Goals

- Do not replace FastAPI Users.
- Do not introduce a new role, permission, or ACL framework.
- Do not broaden role scope grants in this slice.
- Do not preserve legacy MCP TOML migration behavior.
- Do not migrate historical resources through compatibility shims. Existing
  resources without visibility metadata are treated as private unless explicit
  metadata is added.

## Compatibility Cleanup

### Auth Claims

The backend should expose `scopes` only:

- Remove the `PermissionClaims.permissions` alias.
- Remove `UserRead.permissions`.
- Keep JWT and `/api/auth/me` responses aligned on `scopes`.

The frontend should consume `scopes` only:

- Remove `permissions` from auth user types.
- Remove `user?.scopes ?? user?.permissions` fallback.
- Keep role fallback only for unauthenticated or incomplete local test fixtures,
  not for real authenticated user payloads.

### MCP Config

MCP config becomes JSON-only:

- Remove TOML imports and legacy migration helpers.
- `read_mcp_config()` returns defaults when JSON is absent or invalid.
- Tests should assert JSON behavior directly, not that old TOML is migrated.

### Test Style

Where tests currently scan source text for compatibility strings, replace them
with behavior assertions:

- Permission helpers honor `scopes`.
- Missing scopes do not regain permissions through role fallback.
- MCP config ignores unknown legacy protocol keys and stores only supported JSON
  fields.
- Navigation builders place Trace first in governance defaults.

## Navigation

Trace should be the first default item in system governance:

- Operations default group: `home`, `dashboard`, `chat`, `workflow`.
- Governance default group: `trace`, `evaluation`, `approvals`, `scheduler`.

Existing stored user navigation is still honored. This change only affects the
default layout and the home sections derived from default groups.

## Resource Visibility

### Shared Rules

All three resource families use the same visibility terms:

- `private`
- `public`

The backend validates request visibility values. Empty or missing creation
values normalize to `private`; unknown values supplied by clients return a
validation error. Existing stored metadata with missing or unknown visibility is
read as `private`.

Read behavior:

- Admins with `agent_os:admin` see all resources.
- Non-admin users see public resources plus their own private resources.

Mutation behavior:

- Owner/admin checks are enforced in addition to existing endpoint scopes.
- Public visibility does not make a resource globally mutable.
- Toggle, delete, clear, or visibility-change operations must not affect another
  non-admin user's private resource.

### Skill

Skill visibility is stored in `SKILL.md` front matter.

Fields:

- `visibility`
- `owner_user_id`

Skill upload accepts `visibility` as a form field. The installer writes or
updates the front matter after extracting the archive. Listing filters skills by
public/owner/admin visibility. Toggle and visibility update routes require the
actor to be owner/admin.

Expected API additions:

- `POST /api/skills/upload` accepts `visibility`.
- `PUT /api/skills/{skill_name}/visibility` updates visibility.
- `GET /api/skills` returns `visibility`, `owner_user_id`, and an
  actor-specific `can_manage` flag.

### MCP

Custom MCP visibility is stored in `mcp_config.json` inside each
`mcp_servers[]` entry.

Fields:

- `visibility`
- `owner_user_id`

MCP upload accepts `visibility`. Config responses should include visible custom
servers so the frontend can show and manage uploaded MCP entries, not just
built-in service flags and tokens. Visibility updates target the named custom
server.

Expected API changes:

- `POST /api/mcp/upload` accepts `visibility`.
- `GET /api/mcp/config` returns visible `mcp_servers`.
- `PUT /api/mcp/servers/{server_name}/visibility` updates visibility.

Built-in MCP services remain system-level toggles. Their service enable/disable
behavior is not converted to per-user visibility in this slice.

### Knowledge

Knowledge visibility is stored in Agno content/vector metadata.

Fields:

- `visibility`
- `user_id` as the existing owner metadata key.

Text, file, and browser uploads accept `visibility`. List and search return
public documents plus the actor's private documents for non-admin users. Admins
can list and search across all documents.

Search implementation should use metadata filters where Agno supports them. If
the current search API cannot express `public OR owner` in one call, the service
should use two filtered searches, merge by document/chunk identity, sort by
score, and trim to the requested limit. A broad unfiltered search with
post-filtering is only acceptable as a last resort and should over-fetch to
avoid obviously sparse results.

Expected API changes:

- `POST /api/knowledge/documents/text` accepts `visibility`.
- `POST /api/knowledge/documents/file` accepts `visibility`.
- Browser upload routes, if present, pass visibility into the same service.
- `PUT /api/knowledge/documents/{doc_id}/visibility` updates visibility.
- List/search responses include visibility in document metadata and top-level
  document payloads where useful for the UI.

## Frontend

Each creation flow gets a compact Private/Public control:

- Skill upload form.
- MCP upload form.
- Knowledge text import, file upload, and path import forms.

Each list row/card shows the current visibility and exposes a visibility toggle
only when `can_manage` is true.

Frontend authorization checks use scopes only. UI hiding is not security; the
backend still enforces read/mutation rules.

## Error Handling

- Invalid visibility returns 422 or 400 with a concise message.
- Attempting to update another user's private resource returns 404 to avoid
  disclosing private resource existence.
- Attempting to mutate a visible public resource without owner/admin ownership
  returns 403.
- Duplicate Skill or MCP names keep their existing 409 behavior.
- Knowledge search failures still return controlled 400 responses for invalid
  search parameters.

## Testing Strategy

### Backend

- Auth schema responses include `scopes` and no `permissions` field.
- Permission checks do not use a permissions alias.
- MCP config is JSON-only and no longer migrates TOML.
- MCP upload persists visibility and owner metadata.
- Skill upload/list/toggle/visibility update enforce public/owner/admin rules.
- Knowledge list/search returns public plus owner-private resources for
  non-admin users and all resources for admins.
- Knowledge visibility updates are owner/admin only.

### Frontend

- Navigation tests assert Trace is first under governance by default.
- Auth permission tests assert scopes-only behavior.
- Skill, MCP, and Knowledge API payload tests include visibility.
- UI shell tests assert creation controls and visibility badges/actions exist
  without relying on source-string compatibility checks.

### Verification Commands

Run focused checks during implementation:

- `uv run ruff check <changed-python-files>`
- `uv run ty check <changed-python-files>`
- `pytest`
- `cd frontend && bun run test:shell`
- `cd frontend && bun run test:auth`
- `cd frontend && bun run build`

After tests pass, start the preflight server with:

```bash
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
```

Use the configured test admin account for smoke testing:

```bash
AGNO_BOOTSTRAP_ADMIN_EMAIL=admin@example.com
AGNO_BOOTSTRAP_ADMIN_PASSWORD=AdminPass123!
```
