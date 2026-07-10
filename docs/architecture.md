# T.A.I.S 架构说明

T.A.I.S 是一个面向安全运营的 AI 控制面。后端提供认证、权限、运行时编排、MCP、知识库、Trace、Memory、Evaluation、Approval、Scheduler 和 CVE 能力；前端提供统一工作台。

## 前端

- React 19 + TypeScript + Vite 8/Rolldown。
- TanStack Router 管理页面路由、可分享筛选和会话定位。
- TanStack Query 管理服务端数据、缓存、刷新和 mutation 后失效。
- Ant Design v6 与 Ant Design X 承担主要 UI；UnoCSS 只处理少量特殊布局。
- Chat 使用 Ant Design X 的 `Bubble.List`、`Sender`、`Conversations`、`Welcome`、`Prompts` 和 XMarkdown，不引入 X SDK。
- 目录采用 feature-first：`frontend/src/app`、`frontend/src/features`、`frontend/src/shared`、`frontend/src/test`。

## 后端

- FastAPI 是 API 与安全边界。
- FastAPI Users 与 JWT middleware 提供登录、scope 和用户隔离。
- SQLAlchemy Async 管理控制面数据，Agno AsyncPostgresDb 管理运行时 session、memory、eval 与 trace 数据。
- Knowledge 使用 Agno Knowledge + PgVector，支持文档上传、重建、替换、metadata 更新和检索 playground。
- FastMCP 同进程挂载到 `/mcp/`，由应用 lifespan 启停。

## 数据流

1. 用户在 React 控制面完成认证。
2. 前端通过共享 API client 携带 token 请求 FastAPI。
3. 后端按 scope 和资源归属执行权限检查。
4. Chat 请求进入 `SecurityRunRuntime`，按当前模型、MCP、Skills、Knowledge 和 Memory 配置构建运行时。
5. SSE 将流式输出返回给 Chat；Trace、Memory、Knowledge metadata 等页面通过 Query 刷新读取最新状态。

## 分支约定

- `vue`：旧版 Vue + Element Plus 控制面。
- `master`：新版 React 19 + TanStack + Ant Design v6 控制面。
