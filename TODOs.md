# 下一步工作

## 已完成：Memory 对齐 Agno 原生列表协议

- 新增 canonical 路由 `GET/PATCH/DELETE /api/memories*`，返回 Agno 风格 `data`/`meta` 分页 envelope，并过渡期双写 `items`/`total_count`。
- 保留 `GET /api/memory` 工作台大包（metrics/topics/users）与既有 scopes、user isolation、policy 审计。
- 查询兼容 `search` 与 `search_content`（优先 native 名）；item / mutate 响应同时带 `id` 与 `memory_id`。
- 前端 Memory 客户端改打 `/memories`，`normalizeMemory` 兼容新旧字段；补充 vitest 与后端权限/envelope 用例。

相关入口：

- API：`GET /api/memories`、`PATCH|DELETE /api/memories/{memory_id}`；兼容 `GET|PATCH|DELETE /api/memory*`
- 代码：`api/routes/memory.py`、`api/services/memory_service.py`、`frontend/src/features/memory/api.ts`

## 已完成：Agno 原生 HITL 与通知闭环

- 高影响工具迁入 FastMCP `hitl` namespace；仅 `hitl_*` Function 使用 Agno required approval。
- 审批、同一 session RunOutput、RunRequirement 与 `acontinue_run()` 成为唯一运行状态源；已移除 `hitl_paused_runs` 持久化与启动建表。
- 初始 Run 记录版本化运行时 metadata，审批解析后异步恢复同一 Run；启动恢复 `PAUSED` / `RUNNING` 任务，失败状态支持手动重试。
- 管理员和提交者通知通过带鉴权、游标补发的 SSE 双向推送；Chat 与 Trace 均投影同一 Run 的最终输出和状态。

## 已完成：模型并行工具调用配置

- 模型配置新增可空 `parallel_tool_calls`，数据库启动时自动补列，旧配置保持提供商默认行为。
- 设置页提供启用、禁用、留空三态；非 DeepSeek 模型的 Responses 和 Chat Completions 均可配置。
- Responses 通过 Agno `OpenAIResponses.parallel_tool_calls` 传递；Chat Completions 通过 Agno `request_params` 传递，聊天与会话摘要共用该设置。

## 已完成：Knowledge 进度与安全更新

- 创建/更新统一四阶段进度协议：`upload → parse → vectorize → cleanup`，SSE 推送短文案阶段状态。
- 前端 `DocumentDrawer` / `UpdateDocumentDrawer` 使用 Ant Design `Steps` 展示进度，处理中锁定关闭。
- 安全更新：先写入 shadow `content_id`，成功后再切换到稳定文档 ID；失败只清理 shadow，旧文档与旧向量保持可检索。
- 自动按后缀识别 Reader/Profile，支持 Markdown、TXT、JSON、CSV、代码、PDF/DOCX 同类型与跨类型替换，并保持文档 ID、可见性与选中状态。
- 成功后清理旧 managed 上传文件；后端/前端单测覆盖进度流与失败回滚路径。

相关入口：

- API：`POST /api/knowledge/documents/upload|text|file`、`/documents/{id}/update`、`/documents/{id}/update/upload`（`stream=true`）
- 代码：`api/services/knowledge_progress.py`、`knowledge_source_service.py`、`frontend/src/features/knowledge/components/UpdateProgress.tsx`

## 已完成：治理前端测试耗时

- Vitest：`css: false`、`pool: 'forks'`、`maxWorkers: 4`、`testTimeout/hookTimeout: 8s`，去掉易超时的 `timeout 90s` 外壳。
- 测试夹具：`ConfigProvider` 关闭 motion/hashed；QueryClient `retry: false` + `gcTime: 0`。
- 交互：统一 `src/test/user.ts`（`delay: null`、`pointerEventsCheck: 0`），重型页面用 `setupUser()` / 共享 `user`。
- 脚本：`bun run test`、`bun run test:profile`（verbose + 单 worker 便于定位慢用例）。
- 全量 Vitest 墙钟约 20–30s 级（此前常见 60s+ 抖动），仍可继续拆 Knowledge 等整页套件或接 Playwright E2E。

## 已完成：环境变量命名分层

- 应用配置使用 `TAIS_*` / 领域名（`POSTGRES_*`、`AUTH_*`、`MCP_*`）；`AGNO_*` 仅用于引擎耦合（如 `AGNO_DB_SCHEMA`）。
- Settings、`.env.example`、Knowledge 运行时 RAG 键、CVE skill / update lock 使用 `TAIS_*`；不保留应用侧 `AGNO_*` / `APP_*` 别名。
- 版本号仍以 `pyproject.toml` 为准；OpenAPI title / `APP_NAME` 对齐 `T.A.I.S API`；CVE 源配置文件为 `cve_sources.toml`。

## 已完成：前端 i18n 全量接入

- 按 feature 拆分命名空间：`common/auth/shell/chat/dashboard/knowledge/settings/mcp/approvals/...`（`shared/i18n/namespaces/*.json`）。
- P0：Chat、Dashboard、通用按钮/空态/Toast 文案接入 `react-i18next`。
- P1：Knowledge（含 Drawer/Progress/IngestOptions/文件校验与 Reader 说明）、Settings、MCP、Approvals。
- P1 外壳：通知中心标题/未读数/全部已读/相对时间与 `shell` 命名空间对齐。
- 通知中心：已读消息支持删除（`DELETE /api/notifications/{id}`，仅本人数据）。
- P2：Trace、Audit、CVE、Collect、Memory、Skills、Evaluations、Workflow 页面标题与主操作。
- 工程化：`formatDate`/`useFormatDate` 跟随当前 locale；测试 setup 初始化 i18n；语言切换仍由 `AppProviders` + Ant Design locale 驱动。
- 已知边界：表格列名/部分运维字段仍可保留英文；后端 `detail` 与 SSE 进度原文尚未做后端 i18n。

## P1：建立关键流程 E2E

仓库已安装 `@playwright/test`，但目前没有提交到仓库的 Playwright spec。手工 CLI 验证无法持续保护导航与跨页面流程。

建议首先覆盖：

1. 登录后 Logo 跳转 `/dashboard`，侧栏不出现“运行概览”。
2. 默认展开“工作台”和“能力与数据”，权限不足时空分组消失。
3. 点击“智能体”清除 `session` 参数；点击最近对话进入指定 Session。
4. 264px/76px 侧栏切换、最近对话持久化和移动端抽屉默认状态。
5. Knowledge 创建/更新进度流和 Trace Session → Run → Span 的主路径。

测试应通过 API mock 或独立测试数据隔离运行，避免依赖开发数据库中已有的 Session 和文档。

## P2：导航与治理能力补强

- 深链进入 `/trace`、`/approvals`、`/cve` 等页面时，在默认两个分组之外自动展开当前路由所属分组。
- 决定桌面导航分组状态是否需要跨刷新持久化；移动端继续保持每次打开的可预测默认值。
- 审计能力按“导出 → 规则告警 → Webhook → SIEM”顺序评估，任何外发接口都必须包含 scope、租户/owner 边界、脱敏和审计闭环。

## 推荐实施顺序

1. 用 Knowledge 更新矩阵与 Trace 三个 Session 做数据对照，关闭剩余 P0 边界。
2. 将复现路径固化为后端 fixture、前端单测和 Playwright E2E。
3. 再处理导航深链体验；前端 Vitest 耗时治理已落地，后续按慢用例继续拆分即可。
4. 最后设计审计外部集成，避免在核心数据一致性尚未稳定时扩大数据出口。
