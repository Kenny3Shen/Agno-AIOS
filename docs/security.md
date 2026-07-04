# 安全模型

本文描述当前安全模型。后端是安全边界。

## 认证

API 使用 FastAPI Users 和 JWT bearer authentication。登录接口位于 `/api/auth/jwt/login`，当前用户接口位于 `/api/auth/users/me`。

当前密码校验要求至少 8 位。配置了 OAuth provider 后，会注册对应 provider routes。

可选 bootstrap admin 只有在同时配置 `AGNO_BOOTSTRAP_ADMIN_EMAIL` 和 `AGNO_BOOTSTRAP_ADMIN_PASSWORD` 时才会创建或提升。

## Roles 和 Permissions

后端识别三种 role：

| Role | 含义 |
| --- | --- |
| `admin` | 通过 wildcard permission 访问所有权限。 |
| `user` | 可读写自己的 sessions 和 knowledge，读取自己的 traces，并使用部分安全数据视图。 |
| `guest` | 可读取自己的 sessions、traces、部分 memory/metrics 数据、assets、CVE 和 knowledge。 |

当前后端权限定义在 `api/auth/permissions.py`。

| Permission | Admin | User | Guest |
| --- | --- | --- | --- |
| `session:read:own` | yes | yes | yes |
| `session:write:own` | yes | yes | no |
| `trace:read:own` | yes | yes | yes |
| `memory:read:own` | yes | yes | yes |
| `metrics:read:own` | yes | yes | yes |
| `asset:read` | yes | yes | yes |
| `collect:write` | yes | yes | no |
| `cve:read` | yes | yes | yes |
| `knowledge:read` | yes | yes | yes |
| `knowledge:write` | yes | yes | no |
| `mcp:read` | yes | yes | no |
| `skill:read` | yes | yes | no |
| `settings:read` | yes | yes | no |
| write/admin permissions | yes | no | no |

Admin-only 操作用只有 admin 能通过 wildcard 满足的 permission 表达，例如 `audit:read`、`mcp:write`、`skill:write`、`settings:write` 和 `admin:read`。

## 资源归属

对非 admin actor，用户资源必须匹配 actor 的 user ID。相关 helper 是 `assert_owned_resource()`。

重要场景：

- Chat session 读取和归档会检查存储的 session owner。
- Trace list 和 trace detail 会把非 admin 用户限制在自己的 `user_id` 下。
- Knowledge 写入会附加 owner metadata；Chat 检索在有当前用户时使用该用户作为 knowledge filter。
- Admin 用户可以跨用户查看 sessions、traces 和 audit records。

`session_id` 不是 secret，不能当作授权凭据。

## 前端检查

前端在 `frontend/src/lib/permissions.ts` 中镜像 permissions，并在 `frontend/src/App.vue` 中隐藏不可访问导航。这些检查只用于体验。用户可以直接调用 API，因此 API routes 必须继续执行后端 permission checks。

见 [ADR 0003](./adr/0003-backend-permissions-are-the-security-boundary.md)。

## 审计

Audit records 存储在 `app.audit_logs`。当前会审计的动作包括：

- 登录和登出。
- Session archive。
- CVE database update 尝试和结果。
- Knowledge document 写入、删除和 clear。
- MCP config 变更、token issue/delete、Hi-Agent 变更和 MCP upload。
- Skill toggle 和 upload。
- Model 和 settings updates。

Audit logs 包含 actor identity、role、action、resource type、resource ID、status、request IP、user agent、metadata 和 timestamp。

只有具备 `audit:read` 的 actor 能访问 `/api/audit/logs`；在当前 permission model 中这意味着 admin。

## MCP 访问

集成 MCP endpoint 挂载在 `/mcp/`。它接受两种 token 传入方式：

- `Authorization: Bearer <token>`
- `?token=<token>`

Tokens 存储在 `mcp.mcp_tokens` 表中，带 creation 和 expiration timestamps。`MCP_TOKEN` 也可以在 API 启动时 bootstrap 一个 token。

MCP tokens 和用户 JWT 分离。MCP token 授权 MCP protocol calls，不授权控制面 API calls。

## Secrets 和本地状态

不要提交 `.env`、logs、本地 config state、generated caches 或本地 databases。`data/config/` 下的 runtime config 可能包含 MCP service definitions，除非明确提升为源码，否则应视为环境状态。

任何共享部署前都应使用足够长的随机 JWT/reset/verification secrets。

## 安全不变量

- 每个受保护后端 route 都应要求 permission dependency 或 current-user dependency。
- 非 admin 访问用户资源时应检查归属，而不仅是 route permission。
- 前端隐藏导航不是充分保护。
- MCP endpoint 必须独立于用户 JWT auth 验证 MCP tokens。
- Chat fallback mode 不能声称访问了实际未使用的 tools、knowledge 或内部数据。
