# AGENTS.md

环境为 WSL2 (Ubuntu 24.04)。

Python 开发使用 `uv + ruff + ty`。完成任务后运行：

- `uv run ruff check .`
- `uv run ty check .`

前后端修改后使用 `playwright-cli` 测试，并修复观察到的错误。

## CodeGraph

如果仓库根目录存在 `.codegraph/`，理解或定位代码时先用 CodeGraph，再用 `rg`/`find`：

- MCP 可用时优先使用 `codegraph_explore`。
- Shell 恒可用：`codegraph explore "<symbol names or question>"`。

如果没有 `.codegraph/`，跳过 CodeGraph。
