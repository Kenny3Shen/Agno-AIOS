# 路线图

## 已完成方向

- React 19 + TanStack + Ant Design v6 新版工作台。
- feature-first 前端目录。
- Chat 使用 Ant Design X 与 XMarkdown。
- Knowledge、Trace、Memory、Skills 等页面采用 Ant Design Splitter、Tabs、Table、Tree、Descriptions、Card 等组件。
- Audit 页面提供 admin-only 操作审计查询，支持 User ID、邮箱、动作、资源、状态、IP、时间范围和分页。
- 后端测试删减为业务行为保护，不再保护源码结构和文案。

## 近期重点

- 完善真实工作流 Playwright 截图检查。
- 扩展 Knowledge 上传、更新、重建与 Retrieval playground 的端到端验证。
- 增强 Trace session/run/span 的定位、分页和归档筛选体验。
- 梳理 MCP 服务列表、可用工具展示和上传校验。
- 持续补齐 API mutation 后 Query invalidation 测试。

## 分支

- `vue` 作为旧版冻结分支。
- `master` 承载新版 React 主线与后续演进。
