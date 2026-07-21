# 开发与验证

前端关键路径浏览器 smoke：

```bash
cd frontend && bun run test:e2e
```

前端门禁：`bun run lint`（oxlint deny-warnings）、`bun run typecheck`、`bun run test`；构建覆盖未引用本地符号检查，客户端只保留页面实际调用的 API wrapper 与类型契约。Trace 列表 root `input` 批量失败会打 exception 日志并返回 `input=null`（不 N+1）。 ERROR 列表在 page=1 用 audit 失败 run 补充时，按 `run_id` 批量查 traces（非 per-run `get_trace`）。

使用 Playwright + 页内 `/api` mock，不依赖本地后端与开发库数据；覆盖登录、侧栏分组/权限过滤、智能体清 session、深链展开与侧栏折叠；以及 Trace 深链 Session→Run→Span、Dashboard 最近失败→Trace 规范 query、Knowledge 文本后台入库完成路径、Approvals 值班列表、`approval_id` 深链与 HITL 批准 resolve、Workflow `workflow_id` 深链加载、Studio Run SSE 与 pause→Approvals resolve 闭环、Studio/Chat 停止按钮取消 run、Studio Publish、未发布启用 Webhook 守卫、运行中结构锁；Chat 模型重试退避中 Esc 亦可取消；重试横幅不再重复停止按钮，退避期间保留已生成片段直至新流开始。

前端 Ant Design 6 使用 `classNames` / `styles` 语义化 API（例如 `Popover`/`Cascader` 的 popup class），避免 `overlayClassName` / `popupClassName` 等已弃用 props；`Alert` 使用 `title` 而非已弃用 `message`。


Python：

```bash
uv run ruff check .
uv run ty check .
uv run pytest api/tests
```

后端测试与生产代码共同通过 `ruff` / `ty`；路由测试使用真实 HTTP request shape，后台任务 mock 会显式关闭未执行的 coroutine，避免静态诊断和 `RuntimeWarning` 被掩盖。

前端：

```bash
cd frontend && bun run check
# 仅 Vitest：bun run test
# 慢用例定位：bun run test:profile
```

Vitest 默认关闭 CSS 解析、限制 `maxWorkers=4`、使用 instant `user-event` 与无动画 Ant Design 主题，以降低 DOM 重型页面套件的墙钟与抖动。功能测试以业务行为、权限边界、错误处理和 API 契约为主，避免依赖源码结构、文案、CSS 类名或完整 DOM。涉及前端布局和交互时，用 Playwright 在宽屏和窄屏完成真实流程验证，截图放入 `.tmp`。

