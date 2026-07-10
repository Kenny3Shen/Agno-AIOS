# ADR 0001：React 主线

## 决策

`master` 切换到 React 19 + TanStack Router/Query + Ant Design v6 + Vite 8。旧版 Vue + Element Plus 保留在 `vue` 分支。

## 约束

- 不引入 Zustand；服务端状态由 TanStack Query 管理，路由状态由 TanStack Router 管理。
- Ant Design 优先承担通用 UI，UnoCSS 仅用于少量特殊布局。
- Chat 使用 Ant Design X 与 XMarkdown，不使用 X SDK。
- 测试保护业务行为，不保护源码结构、文案、CSS 类名或完整字段枚举。

## 影响

- 前端采用 feature-first 目录，页面和测试靠近对应 feature。
- 后端继续作为认证、授权和资源归属的安全边界。
- 后续功能优先在 React 主线开发；Vue 分支只用于追溯旧版。
