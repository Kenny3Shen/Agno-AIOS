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

## P1：治理前端测试耗时

当前 Vitest 在并发运行 DOM 重型页面测试时会出现超过默认 5 秒的抖动，因此临时将 `testTimeout` 调整为 10 秒。单 worker 下测试能够稳定通过，说明主要问题是资源竞争而不是功能失败。

下一步：

- 记录每个测试文件的耗时，优先拆分 Knowledge、Audit、Approvals 等重型页面测试。
- 减少重复挂载完整 Ant Design 页面，能测试纯函数或局部组件时不启动整页。
- 评估固定 `maxWorkers`、测试分组或 CI shard，选择总耗时和稳定性的平衡点。
- 清理测试中的未匹配 MSW 请求和 React/Ant Design warning，避免真实错误被噪声淹没。

## P2：导航与治理能力补强

- 深链进入 `/trace`、`/approvals`、`/cve` 等页面时，在默认两个分组之外自动展开当前路由所属分组。
- 决定桌面导航分组状态是否需要跨刷新持久化；移动端继续保持每次打开的可预测默认值。
- 审计能力按“导出 → 规则告警 → Webhook → SIEM”顺序评估，任何外发接口都必须包含 scope、租户/owner 边界、脱敏和审计闭环。

## 推荐实施顺序

1. 先用 Knowledge 更新矩阵和 Trace 三个 Session 的数据对照，确认两个 P0 的剩余边界。
2. 将复现路径固化为后端 fixture、前端单测和 Playwright E2E，防止修复再次回归。
3. 再处理测试性能和导航深链体验，为后续治理功能提供稳定交付基线。
4. 最后设计审计外部集成，避免在核心数据一致性尚未稳定时扩大数据出口。
