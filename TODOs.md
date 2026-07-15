# 下一步工作

## 已完成：Workflow PR1（线性 Step + Save/Run SSE）

- `app.workflows` 表 + CRUD（`{data,meta}`）；定义 DSL 仅 `type=step` + 内置 agent ref。
- `workflow_compiler` → Agno `Workflow`/`Step`；`POST /api/workflows/{id}/runs` SSE（`workflow.*` / `step.*`）。
- 前端：库加载、保存、运行日志、导出参考代码、Trace session 深链；菜单 scope 改为 `sessions:write`。
- README 新增「工作流编排技术架构」路线图（PR2–PR4）。

相关入口：

- `api/persistence/workflows.py`、`api/services/workflow_*.py`、`api/routes/workflows.py`
- `frontend/src/features/workflow/*`

## 已完成：Chat / Markdown LaTeX 公式渲染

- 抽出共享 `Markdown` 组件，启用 `@ant-design/x-markdown/plugins/Latex`（KaTeX）。
- Chat、Approvals、Knowledge、Collect、Skills、PayloadViewer、FormattedContentCard 统一使用。
- 支持 `$...$`、`$$...$$`、`\(...\)`、`\[...\]`；流式与最终消息均可渲染。

相关入口：

- `frontend/src/shared/ui/Markdown.tsx`
- `frontend/src/features/chat/ChatPage.tsx`

## 已完成：Chat 模型重试 UI + Dashboard Trace 深链

- Chat：`security_run_runtime` 包装 Agno `_ainvoke_stream_with_retry`，流式重试时发 SSE `run.retrying`；前端清空 partial content/tools，状态 `retrying` 并展示「第 n/m 次重试」。
- Dashboard「最近失败」跳转使用 Trace 规范 query：`session_id` / `run_id` / `selected_session` / `trace`（不再写 `session`/`run` legacy 别名）。

相关入口：

- `api/services/security_run_runtime.py`、`api/services/chat_run_events.py`
- `frontend/src/features/chat/*`、`frontend/src/features/dashboard/DashboardPage.tsx`

## 已完成：模型重试参数（Chat Completions + Responses）

- `build_agno_model` 对 DeepSeek / OpenAI Chat / OpenAI Responses / OpenAILike 统一注入 Agno `retries` / `delay_between_retries` / `exponential_backoff`，可选 SDK `max_retries`（配置键 `http_max_retries`）。
- 模型设置表单与 `model_configs` 表持久化上述字段；默认 retries=4、delay=1、exponential_backoff=true。
- 503/429 等可恢复错误由 Agno `_ainvoke_with_retry` 重试；400 等 non-retryable 不重试。

相关入口：

- `api/services/model_factory.py`、`model_config_service.py`、`api/persistence/model_configs.py`
- `frontend/src/features/settings/SettingsPage.tsx`

## 已完成：性能热路径收紧

- Chat sessions：DB 级 `page`/`limit` + SQL 归档过滤（`metadata @> agno_aios_archived`），去掉 500 窗后内存分页。
- Overview：traces 最多 5 页 ×1000（5000）采样，超出打 warning，避免 7d 全量加载。
- Trace status 过滤：扫描上限 2000 条；list root input batch 失败不再 per-trace `get_spans`（input=null）。
- Approvals submissions：`GET /api/approvals/submissions` 改为 `{data,meta}` + page/limit；前端按 offset 切片合并 HITL。
- Memory list：本已透传 Agno `page`/`limit`；stats 查询单独有界。

相关入口：

- `api/services/chat_session_service.py`、`overview_service.py`、`tracing_service.py`
- `api/persistence/upload_approvals.py`、`api/routes/approvals.py`、`frontend/src/features/approvals/api.ts`

## 已完成：可靠性 / 可观测性收紧

- overview snapshots 各子块异常改为 `logger.exception`（不再静默 `pass`），缺键仍表示该能力不可用。
- 进程 lifespan 安装 asyncio exception handler，捕获 Agno `amake_memories` 等 fire-and-forget Task 失败（含 Grok metadata 类错误）写入结构化日志。
- HITL resume：approval 缺失 / 失败后无法加载记录时增加 error 日志；既有 submitter+admin 通知路径不变。
- Knowledge SSE 入库/更新/上传增加 15 分钟 `wait_for` 超时，超时发 `progress.failed`（code 504）；阶段失败与前端 toast 路径保持。

相关入口：

- `api/services/overview_service.py`、`api/main.py`、`api/services/security_run_runtime.py`、`api/routes/knowledge.py`

## 已完成：代码卫生清理（分页 helper / 注释 / 兼容）

- 抽取共用 `api/utils/pagination.py::pagination_meta`，memory/approvals/chat/trace/evals list 去掉重复实现。
- Memory `_memory_text` 注释与「只读 `memory` 字段」实现对齐。
- 前端 `getApprovals` 去掉 `string` 状态别名兼容（仅对象参数）。
- Trace status reconcile 文档标明已是 audit `IN (...)` 批量查询（无需再改实现）。

相关入口：

- 代码：`api/utils/pagination.py`、各 `*_service.py`、`frontend/src/features/approvals/api.ts`

## 已完成：Chat sessions 列表对齐 data/meta

- `GET /api/chat/sessions` 返回 `{ data, meta }`（`page`/`limit`/`total_pages`/`total_count`/`search_time_ms`），不再直接返回数组。
- 支持可选 `page`/`limit`（默认 1/500）；归档过滤后内存分页，meta 反映过滤后总数。
- 前端 `listSessions` 解析 envelope 后仍返回 `ChatSession[]`（React Query cache 形状不变）。

相关入口：

- API：`GET /api/chat/sessions`
- 代码：`api/services/chat_session_service.py`、`api/routes/chat.py`、`frontend/src/features/chat/api.ts`

## 已完成：Trace list root input 批量加载

- `_root_inputs_for_trace_ids` 改为 spans 表 `trace_id IN (...)` 单次查询（优先 root / `parent_span_id IS NULL`），替换 list 页 per-trace `get_spans` N+1。
- 批量失败时回退到原 per-trace `get_spans`；input 仍 best-effort（可空）。
- 响应契约不变：`{data,meta}`、`duration`、可选 `input`。

相关入口：

- 代码：`api/services/tracing_service.py`（`_batch_root_spans_by_trace_ids`）
- 测试：`api/tests/test_trace_permissions.py`

## 已完成：Approvals 列表真分页

- 前端 `getApprovals({ status, page, limit })` 读 HITL `data`/`meta`，不再 `limit=100` 客户端切页。
- 表格受控分页；上传 submissions 仍全量拉取，与 HITL 按「submissions 优先」合并后分页。
- 深链 `approval_id` 不在当前页时 `GET /api/approvals/{id}` 拉详情。

相关入口：

- 代码：`frontend/src/features/approvals/api.ts`、`ApprovalsPage.tsx`

## 已完成：Approvals email/拒绝理由字段收窄

- HITL list/detail 不再输出 `submitted_by_email` / `resolved_by_email`，只 enrich `submitted_by` / `resolved_by` 对象。
- resolve 拒绝时仅写 `resolution_data.note`（不再 dual-write `rejection_reason` 键）；读路径优先 `note`，历史行仍可读旧键。
- 请求体 `rejection_reason` 与 submissions 顶层 `rejection_reason` 保留（产品表单 / 上传审批）。

相关入口：

- 代码：`api/services/approvals_service.py`、`api/routes/approvals.py`、`frontend/src/features/approvals/*`

## 已完成：Memory 字段收窄 + Trace URL 去 legacy

- Memory list 投影只认 `memory_id` / `memory` / `topics`；缺 `memory_id` 的行丢弃，不再用 `id`/`content`/`topic` 兜底。
- Trace `parseTraceSearch` 只读 `session_id`/`run_id`，忽略旧别名 `session`/`run`。

相关入口：

- 代码：`api/services/memory_service.py`、`frontend/src/features/trace/utils.ts`

## 已完成：去掉 overview pending_approvals 别名

- Dashboard / overview 仅使用 `snapshots.approvals.{pending,approved,rejected}`。
- 导航 badge 继续走 `GET /api/approvals/count`，不依赖 overview 别名。

## 已完成：Dashboard 待审批 / 已审批快照

- overview `snapshots.approvals = { pending, approved, rejected }`（不保留 `pending_approvals` 别名）。
- Dashboard 治理卡片展示 `待审批 / 已审批`，hint 含已拒绝数。
- 计数：pending 走 Agno `get_pending_approval_count`，approved/rejected 走 list total（limit=1）。

相关入口：

- API：`GET /api/overview` snapshots；`GET /api/approvals/count` 仍仅 pending（badge）
- 代码：`api/services/approvals_service.py`、`frontend/src/features/dashboard/*`

## 已完成：Approvals pending count 端点

- 新增 `GET /api/approvals/count` → Agno 风格 `{ count }`，scopes + user isolation 与列表一致。
- overview `snapshots.approvals` 复用 status counts service；侧栏 Approvals 导航用 `/api/approvals/count` badge。

相关入口：

- API：`GET /api/approvals/count`
- 代码：`api/services/approvals_service.py`、`frontend/src/features/approvals/api.ts`、`frontend/src/app/shell/AppFrame.tsx`

## 已完成：模型 structured output 标记与 API metadata 解耦

- `build_agno_model` 使用私有属性 `_tais_structured_output_mode`，不再写入 `model.metadata`。
- 避免 Grok/xAI 等 OpenAI-compatible Responses 网关因 `metadata` 参数 400；`get_request_params()` 不再携带该字段。
- 新增工厂单测：Responses/Chat 请求参数不含 `metadata`。

相关入口：

- 代码：`api/services/model_factory.py`、`api/tests/test_model_factory.py`

## 已完成：Evals 读路径对齐 Agno 分页 envelope

- `GET /api/agent-evals/agno-runs` 返回 `{ data, meta }`，行主键 `id`、载荷 `eval_data`（Agno EvalSchema 命名），去掉 list 内嵌 `items`/`trends`/`total`。
- `/trends` 仍为工作台聚合；`/failures` 仍为失败过滤 + case_run replay 关联；suites/cases/run/replay 自研不变。
- overview 快照与前端 `listRuns` 改读 `data`/`meta`；`normalizeEvalRun` 接受 `eval_data`。

相关入口：

- API：`GET /api/agent-evals/agno-runs`、`/failures`、`/trends`；suites/cases 不变
- 代码：`api/services/agent_eval_result_service.py`、`frontend/src/features/evaluations/api.ts`

## 已完成：Approvals 列表对齐 Agno 分页 envelope

- `GET /api/approvals` 返回 `{ data, meta }`（`page` / `limit` / `total_pages` / `total_count` / `search_time_ms`），去掉 workbench `module`/`metrics`/`records`/`approval_meta` 大包。
- 保留 scopes、user isolation、actor email enrich；resolve / resume / submissions 不变。
- 前端 `getApprovals` 从 `data` 读取 HITL 列表，`normalizeApproval` 统一行形状；submissions 仍走 `/api/approvals/submissions`。

相关入口：

- API：`GET /api/approvals`、`GET|POST /api/approvals/{id}`、`POST .../resolve|resume`、`/submissions*`
- 代码：`api/services/approvals_service.py`、`frontend/src/features/approvals/api.ts`

## 已完成：Trace 列表/会话对齐 Agno 分页 envelope

- `GET /api/traces` 与 `GET /api/traces/sessions` 返回 `{ data, meta }`，继续走 status reconcile。
- list/detail 对外只暴露 Agno 风格 `duration`（存储仍为 Agno `duration_ms`，API 层投影），list best-effort 附带 root `input`。
- sessions 经 `data/meta` 归一化；detail tree/spans 仍为工作台自研节点形状，但 duration 字段与 Agno 一致。

相关入口：

- API：`GET /api/traces`、`GET /api/traces/sessions`
- 代码：`api/services/tracing_service.py`、`frontend/src/features/trace/api.ts`

## 已完成：Memory 对齐 Agno 原生列表协议

- 唯一 REST 前缀：`GET/PATCH/DELETE /api/memories*`，Agno 风格 `data`/`meta` 分页 envelope。
- 已移除 `/api/memory` 工作台大包与 list dual-write；响应主键仅 `memory_id`。
- 列表查询使用 `search_content`；保留 scopes、user isolation、policy 审计。
- 前端 `normalizeMemory` 仅接受 `memory_id`，UI 内将 `id` 镜像为 `memory_id`。

相关入口：

- API：`GET /api/memories`、`PATCH|DELETE /api/memories/{memory_id}`
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
