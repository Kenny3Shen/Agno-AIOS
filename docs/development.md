# 开发工作流

## 前端目录

```text
frontend/src/
├── app/       # Provider、Router、Shell、全局样式
├── features/  # auth/chat/trace/knowledge/memory/mcp/skills/audit 等页面与领域逻辑
├── shared/    # API client、auth、i18n、types、通用 UI
└── test/      # Vitest、MSW、React Testing Library 基础设施
```

复杂 feature 使用 `api.ts`、`queries.ts`、`types.ts`、`utils.ts`、`useXxx.ts` 和职责型组件命名。feature 内部优先相对导入；跨 feature 通过公开 `index.ts`。

## 测试策略

- 前端测试关注业务行为、状态转换、API 契约和用户交互。
- 后端测试关注权限、安全边界、生命周期、副作用、错误处理和数据合并。
- Audit 测试关注 `audit:read` 管理员权限、筛选参数传递、API query 构造、分页和详情交互。
- 不测试源码字符串、import 结构、完整 DOM、CSS 类名、完整文案或内部 helper 是否存在。
- i18n 相关业务测试应使用稳定 key 或行为断言，避免中文/英文措辞变化导致失败。

## 前端工具链

- 前端使用 Oxlint 做快速 lint，Oxfmt 做格式化，TypeScript 类型检查仍由 `tsc -b` 负责。
- `bun run lint` 是当前前端 lint 门禁；配置位于 `frontend/.oxlintrc.json`，启用 React、React perf、import、jsx-a11y、Vitest 等插件，并关闭与 React 19 自动 JSX runtime 或 Ant Design render props 冲突的规则。
- `bun run format` 使用 Oxfmt，但当前仓库尚未建立全量格式化 baseline。默认只格式化本次触碰文件；全仓库 `oxfmt --write` 应作为单独的 formatting-only 变更处理。
- Ant Design 的 `message`、`notification` 和 `modal` 必须通过 `App.useApp()` 获取，不能直接调用静态 `message.*`、`notification.*` 或 `Modal.confirm`。应用根节点已经由 `XProvider` 和 Ant Design `App` 包裹。
- 工作台动效统一使用 `--motion-*` CSS token，并必须保留 `prefers-reduced-motion` 兜底。新增动效应控制在短时长状态反馈，不引入额外动画库。

## 常用命令

```bash
uv run pytest api/tests
uv run ruff check .
uv run ty check .

cd frontend
/home/shenss/.bun/bin/bun run lint
/home/shenss/.bun/bin/bun run typecheck
/home/shenss/.bun/bin/bun run test:shell
/home/shenss/.bun/bin/bun run test:auth
/home/shenss/.bun/bin/bun run build
/home/shenss/.bun/bin/bun run check
```

## 提交前检查

至少运行与改动相关的后端 pytest 或前端 Vitest。涉及前端布局、Splitter、Drawer、Tabs、Tree 或响应式行为时，用 Playwright 在宽屏和窄屏做一次真实工作流检查，并将截图保存在 `.tmp`。
