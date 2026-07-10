# 安全模型

后端是唯一安全边界。前端的菜单隐藏、按钮禁用和路由保护只用于用户体验，不能作为授权依据。

## 权限原则

- 所有受保护 API 必须在后端检查 scope。
- 涉及用户数据的资源必须检查 owner 或 admin 能力。
- 普通用户只能管理自己的 private 资源；public 资源可读但不可由非 owner 修改。
- Guest 仅允许只读安全数据能力，不允许写入 Chat、Memory、Knowledge、MCP、Settings 等状态。

## 认证与会话

- 登录后使用 FastAPI Users/JWT。
- scope 写入 JWT claims，并由后端 middleware 与 route dependency 使用。
- 401/退出会清理前端本地 token，避免继续携带失效凭证。

## 审计

配置变更、Memory mutation、Approval resolution、策略事件等关键操作应记录 actor、action、resource、metadata、IP 和 user-agent。

## 前端约束

- 不复制 Query 数据到全局状态作为授权依据。
- 不引入 Zustand；服务端状态由 TanStack Query 管理。
- Visibility 使用统一下拉组件，但最终写入权限仍以后端判断为准。
