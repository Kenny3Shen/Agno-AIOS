# AGENTS.md

环境为 WSL2 (Ubuntu 24.04)

Python 开发使用 `uv + ruff + ty`。完成任务后运行：

- `uv run ruff check .`
- `uv run ty check .`

使用 `playwright-cli` 测试，并修复观察到的错误。

如果环境里没有全局 `playwright-cli` 可执行文件，优先使用仓库内前端依赖提供的 Playwright 能力，例如：

- `cd frontend && /home/shenss/.bun/bin/bunx playwright --version`
- `cd frontend && /home/shenss/.bun/bin/bun -e 'import { chromium } from \"@playwright/test\"; ...'`

前端依赖在 `frontend/` 下以 Bun 管理。修改 `frontend/package.json` 时使用：

- `/home/shenss/.bun/bin/bun install`
- `/home/shenss/.bun/bin/bun add <package>`
- `/home/shenss/.bun/bin/bun remove <package>`

前端验证仍使用当前 package scripts：

- `cd frontend && /home/shenss/.bun/bin/bun run test:shell`
- `cd frontend && /home/shenss/.bun/bin/bun run test:auth`
- `cd frontend && /home/shenss/.bun/bin/bun run build`

## CodeGraph

如果仓库根目录存在 `.codegraph/`，理解或定位代码时先用 CodeGraph，再用 `rg`/`find`：

- MCP 可用时优先使用 `codegraph_explore`。
- Shell 恒可用：`codegraph explore "<symbol names or question>"`。
- 如果当前环境没有 `codegraph` 命令或对应 MCP 工具，再回退到 `rg`/`find`。

如果没有 `.codegraph/`，跳过 CodeGraph。
