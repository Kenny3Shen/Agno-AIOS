# 发布核对

本页定义一次可复核的发布流程。版本唯一来源是根目录
`pyproject.toml` 的 `[project].version`；API/OpenAPI 从已安装的 `T.A.I.S`
发行包元数据解析版本，前端版本须同步到 `frontend/package.json`。

## 1.0.0 范围

1.0.0 包含精简后的 `admin` / `user` RBAC、授权版本撤销、Dashboard
Overview trace 反射兼容性修复和现有 Alembic migrations。性能缓存、资产—
漏洞—告警闭环，以及 Team 的 MCP/HITL 扩展属于 1.1+。

## 代码与构建门禁

在干净工作树、锁文件无漂移的环境中执行：

```bash
uv lock --check
uv run ruff check .
uv run ty check .
uv run pytest api/tests
uv build

cd frontend
bun install --frozen-lockfile
bun run check
bun run build
```

预发环境还应启动 API，并确认 liveness/readiness：

```bash
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
curl -fsS http://127.0.0.1:8001/api/health
curl -fsS http://127.0.0.1:8001/api/ready
```

在可用预发账号、数据库与浏览器环境中补跑：

```bash
cd frontend && bun run test:e2e
```

仓库的 GitHub Actions `Quality` 工作流执行同一组后端门禁和前端检查/E2E；本地
结果不能替代受保护分支上的 CI 结果。

## 数据库与回滚

1. 先创建生产数据库的恢复点，并恢复到一个独立 PostgreSQL **克隆库**。
2. 仅对克隆库记录以下预检和应用报告；绝不对生产库运行 `--apply`：

   ```bash
   uv run rehearse-rbac-migration --database-url "$POSTGRES_URL"
   uv run rehearse-rbac-migration \
     --database-url "$POSTGRES_URL" \
     --apply \
     --backup-reference "pg_dump:<artifact>" \
     --confirm-clone I_UNDERSTAND_THIS_IS_A_CLONE
   ```

3. 保存 JSON 报告、备份引用、Alembic head、耗时和 Worker 恢复结果。确认后，
   在已批准的目标环境执行 `uv run alembic upgrade head`，再启动 API 和 Job
   Worker。
4. 若发布后出现不可接受故障，停止新写入、恢复已记录的数据库备份，并回滚到前一
   个已验证的应用工件；不要以未经演练的 Alembic downgrade 代替数据库恢复。

## 发布记录

发布提交应包含版本、`uv.lock`、文档和所有门禁结果。通过审核后才创建本地
`v1.0.0` annotated tag；推送 tag、创建 GitHub Release 或发布任何包都需要单独的
发布授权。
