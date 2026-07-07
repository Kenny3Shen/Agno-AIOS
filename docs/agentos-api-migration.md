# AgentOS API 迁移记录

本文记录 AIOS 自定义 API 与 Agno AgentOS native API 的迁移边界。原则是：能直接使用 AgentOS API 的路径直接替换，不保留兼容 wrapper；暂时不能迁移的路径必须记录原因和下一步。

## 已迁移

### Scheduler

前端 Scheduler 视图已从 `/api/os/scheduler*` 迁移到 AgentOS native routes：

- `GET /schedules?limit=100&page=1`
- `POST /schedules`
- `PATCH /schedules/{id}`
- `POST /schedules/{id}/enable`
- `POST /schedules/{id}/disable`
- `POST /schedules/{id}/trigger`
- `DELETE /schedules/{id}`
- `GET /schedules/{id}/runs?limit=100&page=1`

旧后端 `api.services.scheduler_service` 和 `/api/os/scheduler*` routes 已删除。前端只保留 `frontend/src/modules/schedulerAgentOsApi.ts` 这一层适配，把 UI 的 `target_type` / `target_id` 映射为 Agno endpoint，并把 Agno paginated response 转成现有 Vue 组件数据结构。

Scheduler 导航权限使用 AgentOS scope `schedules:read`，不再依赖 AIOS 的 `admin:read` facade 权限。

## 暂缓迁移

### AgentOS Authorization / RBAC

Agno 文档支持 AgentOS scope/RBAC authorization，JWT claims 使用 `scopes`，例如 `schedules:read`、`schedules:write`、`schedules:delete`，管理员使用 `agent_os:admin`。AIOS 当前已经把 AgentOS 注册到现有 FastAPI base app，但 AgentOS native authorization 尚未整体启用。

当前暂缓原因：

- 本项目现有 `/api/auth/*`、前端静态资源、MCP endpoint 和 AIOS APIs 与 AgentOS routes 运行在同一个 FastAPI app 上。
- 直接在现有 base app 上整体启用 AgentOS authorization 会影响 `/api/auth/*`、静态资源和 AIOS 自定义 APIs；需要先设计 route 排除、sub-app 隔离或统一 JWT middleware。
- 当前 FastAPI Users token 还没有按 AgentOS `scopes` / `agent_os:admin` 设计签发和验证契约。

下一步：

- 选择一种结构：把 AgentOS 挂载到独立 sub-app 并只对 AgentOS routes 启用 Agno authorization，或调整 token 签发后整体启用 AgentOS JWT middleware。
- 统一 JWT claims：`sub` 使用用户 ID，`scopes` 使用 AgentOS scopes，admin 映射到 `agent_os:admin`。
- 用行为测试覆盖未认证访问 `/schedules` 返回 401、缺少 `schedules:read` 返回 403、admin token 可访问。

### Approvals

保留 `/api/os/approvals`。当前 AIOS route 增加了 pending count、filter normalization、resolver identity 和 audit event。迁移前需要确认 AgentOS approvals API 是否能覆盖这些 UI projection 和审计要求。

### Memory

保留 `/api/os/memory`。当前 AIOS route 做了 user ownership scoping、growth signals、topic/user filters、update/delete audit，并把 Agno memory records 转成运营视图。可迁移项是只读列表和 detail；mutation 迁移需要先确认 AgentOS authorization 的 user isolation。

### Chat Sessions

保留 `/api/chat/sessions` 和 archive route。AIOS 使用 Agno session metadata 实现 soft archive，这不是 AgentOS hard delete 语义。迁移前需要产品确认是否改为 AgentOS session delete/rename/update 语义。

### Trace

保留 `/api/traces`。当前 UI 需要 span tree、session/run 关联、owner checks 和错误态整理。AgentOS trace API 可作为数据源候选，但不能直接替代当前展示 payload。

### Knowledge

保留 `/api/knowledge`。当前 AIOS 提供 browser text ingestion、owner/visibility metadata、document lifecycle、visibility mutation、rebuild、vector-row delete/clear 和 search result hydration。迁移前需要明确 AgentOS Knowledge API 对 ownership、public/private visibility、文件上传、metadata patch、rebuild 和删除语义的覆盖范围。

### Agent Evals

保留 `/api/agent-evals`。当前实现包含 suite、case、case run 和 trend/failure views，不只是 Agno eval run records。后续只能把真实 eval runs 部分迁到 Agno eval APIs，不能把 AIOS-specific planning records 硬塞进 AgentOS。

## 验证要求

每次迁移一个模块时至少覆盖：

- 前端行为测试：请求路径、请求体、response normalization。
- 后端删除测试：旧 `/api/os/<module>*` facade 不再注册。
- 权限测试：导航和 API 使用 AgentOS scopes，而不是旧 AIOS wrapper 权限。
- 预发 smoke：使用 `admin@example.com` / `AdminPass123!` 登录后验证 UI 工作流。
