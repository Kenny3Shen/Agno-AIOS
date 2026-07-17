开发环境为 WSL2 (Ubuntu 24.04)
Python 开发使用 `uv + ruff + ty`：

- `uv run python` 执行 Python 文件

Agent 框架为 Agno，文档通过 agno-docs mcp 查询
MCP 框架为 FastMCP, 文档通过 fastmcp-docs mcp 查询
前端UI 框架为 Ant Design，文档通过 antd mcp 查询
完成阶段性任务后：

- `uv run ruff check <file_name>` 检查格式
- `uv run ty check <file_name>` 静态代码分析
- `uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001` 启动预发环境
- `uv run pytest` 测试后端; `playwright-cli` 测试前端

修改 `frontend/package.json` 时使用：

- `bun install/add/ remove <package>`

测试使用 package scripts：

`cd frontend && bun run check`

修改完毕后：

`bun run build` 若编译失败则修复

提交commit时，需要更新 TODOS.md 和 README.md
<scripts></scripts>

测试账号

```bash
TAIS_BOOTSTRAP_ADMIN_EMAIL=admin@example.com
TAIS_BOOTSTRAP_ADMIN_PASSWORD=AdminPass123!
```
