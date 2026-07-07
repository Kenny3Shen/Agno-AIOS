# 开发工作流

本文描述当前仓库的开发流程。

## 工具链

Python 使用 `uv`、`ruff` 和 `ty`。

```bash
uv run python <file.py>
uv run ruff check .
uv run ty check .
```

前端使用 Bun 和 `frontend/package.json` 中的 scripts。

```bash
cd frontend
/home/shenss/.bun/bin/bun run test:shell
/home/shenss/.bun/bin/bun run test:auth
/home/shenss/.bun/bin/bun run build
```

不要用 npm 修改本仓库前端依赖。使用：

```bash
cd frontend
/home/shenss/.bun/bin/bun install
/home/shenss/.bun/bin/bun add <package>
/home/shenss/.bun/bin/bun remove <package>
```

## CodeGraph

本仓库存在 `.codegraph/` 目录。定位代码或理解行为时，先用 CodeGraph，再做大范围 grep/find：

```bash
codegraph explore "chat route agent service session ownership"
```

明确相关区域后，再用 `rg` 做直接文本搜索。

## 后端开发

后端 package 是 `api`。主入口：

```bash
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

重要边界：

- Routes 放在 `api/routes/`。
- 业务逻辑放在 `api/services/`。跨 route 复用的 Run runtime、Knowledge lifecycle、MCP config mutation 和 security policy 应放在这里，route 只保留 HTTP 边界和依赖注入。
- 认证和 scope 规则放在 `api/auth/`。
- 集成 MCP runtime 代码放在 `api/mcp/`。
- 运维脚本放在 `api/tasks/`。

新增受保护 route 时，在 route 边界定义 scope check；涉及用户资源时增加 ownership check。新增安全相关 mutation 时记录 audit event。若同一类 scope、ownership 或 audit policy 被多个 route 复用，应优先通过 `api/services/security_policy.py` 集中表达。

## 前端开发

前端是 `frontend/` 下的 Vue 3 应用。

重要边界：

- `frontend/src/App.vue` 负责 shell navigation 和 module mounting。
- `frontend/src/components/` 负责用户可见 views。
- `frontend/src/stores/` 负责 Pinia state。
- `frontend/src/composables/` 和 `frontend/src/lib/` 负责 API 和 utility helpers。
- `frontend/src/i18n/` 负责展示文案。
- `frontend/src/styles/` 负责 design tokens。

前端 scope checks 只用于可见性。任何新的受保护能力都必须单独更新后端 scope checks。

## 测试与检查

阶段性工作后运行：

```bash
uv run ruff check .
uv run ty check .
uv run pytest api/tests

cd frontend
/home/shenss/.bun/bin/bun run test:shell
/home/shenss/.bun/bin/bun run test:auth
/home/shenss/.bun/bin/bun run build
```

浏览器 smoke test：启动 API 后用 Playwright 检查托管页面。

```bash
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000
playwright-cli open http://127.0.0.1:8000
playwright-cli console
playwright-cli snapshot
playwright-cli close
```

## 文档规则

- `README.md` 是入口和快速启动索引。
- `CONTEXT.md` 只放领域词汇表，不放实现细节。
- `docs/architecture.md`、`docs/operations.md`、`docs/security.md` 和本文只描述当前代码事实。
- `docs/roadmap.md` 是 docs 中唯一放未来工作或未提交计划的文件。
- `docs/adr/` 中的 ADR 应该少而精，只记录难以反转且有真实取舍的决策。
