# 下一步工作

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

## P0：补齐 Knowledge 更新验收矩阵

实现层已支持原地替换、进度展示与失败保留旧内容。仍需用真实样例做端到端验收，关闭历史“跨类型假死/残留分块”风险。

下一步：

1. 建立 Markdown、TXT、JSON、CSV、Python/JavaScript、PDF/DOCX 的更新矩阵，覆盖同类型更新与跨类型更新。
2. 每个样例记录文档 ID、旧/新 reader profile、向量分块数量、上传文件路径和最终检索结果。
3. 对替换流程做失败注入（解析失败、向量化失败），确认旧文档仍可检索、无孤立 shadow 分块或临时上传文件。
4. 使用 Playwright 覆盖 Drawer 提交、阶段进度、失败提示、选中文档保持和更新后检索。
5. 若矩阵全部通过，关闭该 P0；若仍失败，定位到前端决策、API multipart、Agno reader 或生命周期清理中的具体一层。

## P0：诊断 Trace 历史 Run 缺失

已知 Session：

- `23cc01e7-3479-4012-ba39-a05aec614131`
- `1dbdb90c-9c0c-4673-857e-0a5d0ce7ab6a`
- `5375db29-613c-4edf-bdeb-312d3835c151`

Chat 历史来自会话存储，Trace 页面来自 tracing 数据库并通过 session、run、trace 三层映射展示，因此 Chat 有内容不代表 Trace 数据一定存在。

下一步：

1. 对三个 Session 分别导出 Chat runs、Trace session summary、trace 列表和 span detail，形成逐层对照。
2. 检查 run ID、session ID、trace ID 是否在流式事件、Agno 持久化和 tracing exporter 之间发生丢失或格式变化。
3. 区分三种结果：Trace 从未写入、Trace 已写入但查询过滤错误、Trace 存在但前端分组/根 Span 选择错误。
4. 对可恢复数据提供后端回填或读取回退；对不可恢复数据在 UI 中显示原因，而不是空白详情。
5. 将三个 Session 转换为脱敏回归 fixture，覆盖列表、分页、根 Span 和详情回退。

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
