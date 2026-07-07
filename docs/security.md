# 安全模型

本文描述当前安全模型。后端是安全边界。

## 认证

API 使用 FastAPI Users 和 JWT bearer 认证。登录接口位于 `/api/auth/jwt/login`，当前用户接口位于 `/api/auth/users/me`。

当前密码校验要求至少 8 位。配置 OAuth provider 后，会注册对应 provider routes。

可选 bootstrap admin 只有在同时配置 `AGNO_BOOTSTRAP_ADMIN_EMAIL` 和 `AGNO_BOOTSTRAP_ADMIN_PASSWORD` 时才会创建或提升。

## 角色和 Scopes

后端识别三种角色：

| 角色 | 含义 |
| --- | --- |
| `admin` | 通过 AgentOS admin scope 访问所有控制面能力。 |
| `user` | 可读写自己的 sessions、knowledge 和 memories，读取自己的 traces，并使用部分安全数据视图。 |
| `guest` | 可读取自己的 sessions、traces、部分 memory/metrics 数据、CVE 和 knowledge。 |

当前后端 role 到 scope 的映射定义在 `api/auth/claims.py`，route 依赖位于 `api/auth/scopes.py`。

控制面 module scope 和 policy audit event 的复用规则集中在 `api/services/security_policy.py`。Route 仍负责声明 FastAPI dependency，但共享 policy 的判断和 audit event 形状不应重复散落在 route implementation 中。

| Scope | Admin | User | Guest |
| --- | --- | --- | --- |
| `sessions:read` | 是 | 是 | 是 |
| `sessions:write` | 是 | 是 | 否 |
| `traces:read` | 是 | 是 | 是 |
| `memories:read` | 是 | 是 | 是 |
| `memories:write` | 是 | 是 | 否 |
| `metrics:read` | 是 | 是 | 是 |
| `collect:write` | 是 | 是 | 否 |
| `cve:read` | 是 | 是 | 是 |
| `knowledge:read` | 是 | 是 | 是 |
| `knowledge:write` | 是 | 是 | 否 |
| `mcp:read` | 是 | 是 | 否 |
| `skill:read` | 是 | 是 | 否 |
| `config:read` | 是 | 是 | 否 |
| 写入和 admin-only scopes | 是 | 否 | 否 |

Admin-only 操作用只有 admin 能通过 `agent_os:admin` 满足的 scopes 表达，例如 `audit:read`、`mcp:write`、`skill:write`、`config:write`。

## 资源归属

对非 admin actor，用户资源必须匹配 actor 的 user ID。相关 helper 是 `assert_owned_resource()`。

重要场景：

- Chat session 读取和归档会检查存储的 session owner。
- Trace list 和 trace detail 会把非 admin 用户限制在自己的 `user_id` 下。
- Memory 读取、更新和删除会把非 admin 用户限制在自己的 `user_id` 下；admin 可以跨用户筛选并处理 memories。
- Knowledge 写入会附加 owner metadata；Chat 检索在有当前用户时使用该用户作为 knowledge filter。
- Admin 用户可以跨用户查看 sessions、traces 和 audit records。

`session_id` 不是 secret，不能当作授权凭据。

## 前端检查

前端在 `frontend/src/lib/scopes.ts` 中镜像 role scope fallback，并在 `frontend/src/App.vue` 中隐藏不可访问导航。这些检查只用于体验。用户可以直接调用 API，因此 API routes 必须继续执行后端 scope checks。

见 [ADR 0003](./adr/0003-backend-permissions-are-the-security-boundary.md)。

## 审计

审计记录存储在 `app.audit_logs`。当前会审计的动作包括：

- 登录和登出。
- Session archive。
- Memory update 和 delete。
- CVE database update 尝试和结果。
- Knowledge document 写入、删除和 clear。
- MCP config 变更、token issue/delete 和 MCP upload。
- Skill toggle 和 upload。
- Model 和 settings updates。

Audit logs 包含 actor identity、role、action、resource type、resource ID、status、request IP、user agent、metadata 和 timestamp。

只有具备 `audit:read` 的 actor 能访问 `/api/audit/logs`；在当前 scope model 中这意味着 admin。

## MCP 访问

集成 MCP endpoint 挂载在 `/mcp/`。它接受两种 token 传入方式：

- `Authorization: Bearer <token>`
- `?token=<token>`

Tokens 存储在 `mcp.mcp_tokens` 表中，带创建时间和过期时间。`MCP_TOKEN` 也可以在 API 启动时 bootstrap 一个 token。

MCP tokens 和用户 JWT 分离。MCP token 授权 MCP protocol calls，不授权控制面 API calls。

## Secrets 和本地状态

不要提交 `.env`、logs、本地 config state、generated caches 或本地 databases。`data/config/` 下的 runtime config 可能包含 MCP service definitions，除非明确提升为源码，否则应视为环境状态。

任何共享部署前都应使用足够长的随机 JWT/reset/verification secrets。

## 安全不变量

- 每个受保护后端 route 都应要求 scope dependency 或 current-user dependency。
- 非 admin 访问用户资源时应检查归属，而不仅是 route scope。
- 前端隐藏导航不是充分保护。
- MCP endpoint 必须独立于用户 JWT auth 验证 MCP tokens。
- Chat fallback mode 不能声称访问了实际未使用的 tools、knowledge 或内部数据。
