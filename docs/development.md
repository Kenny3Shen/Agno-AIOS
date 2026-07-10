# 开发工作流

## 前端目录

```text
frontend/src/
├── app/       # Provider、Router、Shell、全局样式
├── features/  # auth/chat/trace/knowledge/memory/mcp/skills 等页面与领域逻辑
├── shared/    # API client、auth、i18n、types、通用 UI
└── test/      # Vitest、MSW、React Testing Library 基础设施
```

复杂 feature 使用 `api.ts`、`queries.ts`、`types.ts`、`utils.ts`、`useXxx.ts` 和职责型组件命名。feature 内部优先相对导入；跨 feature 通过公开 `index.ts`。

## 测试策略

- 前端测试关注业务行为、状态转换、API 契约和用户交互。
- 后端测试关注权限、安全边界、生命周期、副作用、错误处理和数据合并。
- 不测试源码字符串、import 结构、完整 DOM、CSS 类名、完整文案或内部 helper 是否存在。
- i18n 相关业务测试应使用稳定 key 或行为断言，避免中文/英文措辞变化导致失败。

## 常用命令

```bash
uv run pytest api/tests
uv run ruff check .
uv run ty check .

cd frontend
/home/shenss/.bun/bin/bun run test:shell
/home/shenss/.bun/bin/bun run test:auth
/home/shenss/.bun/bin/bun run build
```

## 提交前检查

至少运行与改动相关的后端 pytest 或前端 Vitest。涉及前端布局、Splitter、Drawer、Tabs、Tree 或响应式行为时，用 Playwright 在宽屏和窄屏做一次真实工作流检查，并将截图保存在 `.tmp`。
