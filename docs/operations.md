# 运行说明

## 依赖安装

```bash
uv sync
cd frontend
/home/shenss/.bun/bin/bun install
```

## 开发启动

后端：

```bash
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8001
```

前端：

```bash
cd frontend
VITE_API_PROXY_TARGET=http://127.0.0.1:8001 /home/shenss/.bun/bin/bun run dev
```

访问 `http://localhost:5173`。

## 生产构建

```bash
cd frontend
/home/shenss/.bun/bin/bun run build
```

构建产物由 FastAPI 静态托管逻辑读取。部署时应设置生产级 JWT secret、数据库连接、MCP token、模型配置和 CORS。

## 常用环境变量

- `POSTGRES_*` / `POSTGRES_URL`：PostgreSQL 连接。
- `AUTH_JWT_SECRET`：认证 JWT secret，生产必须替换默认值。
- `AGNO_BOOTSTRAP_ADMIN_EMAIL` 与 `AGNO_BOOTSTRAP_ADMIN_PASSWORD`：可选 bootstrap 管理员。
- `AGNO_KNOWLEDGE_*`：Knowledge chunk、search、rerank 与 PgVector 设置。
- `VITE_API_PROXY_TARGET`：前端开发代理目标。

## 运维任务

```bash
uv run update-cve
uv run pytest api/tests
```

运行时配置、CVE 缓存和上传文件默认写入 `.config/`，日志默认写入 `.logs/`；这两个目录不纳入 Git 追踪。CVE 缓存位置可通过 `AGNO_CVE_DATA_DIR` 调整，或在 `config.toml` 中覆盖数据源的 `local_cache` / `commit_cache`。

## 审计查询

管理员登录后可从侧边栏进入 `Audit` 页面。页面调用 `GET /api/audit/logs`，支持按 User ID、邮箱、动作、资源类型、资源 ID、状态、IP 和时间范围查询，并使用分页返回结果。

API 示例：

```bash
curl -H "Authorization: Bearer <token>" \
  "http://127.0.0.1:8001/api/audit/logs?page=1&limit=25&actor_user_id=<user-id>&action=auth.login"
```

审计数据保存在 PostgreSQL `audit_logs` 表，metadata 使用 JSONB 存储，仅用于详情展示。当前版本不提供导出、实时告警、保留策略或外部 SIEM streaming。

前端 smoke：

```bash
cd frontend
/home/shenss/.bun/bin/bun run test:shell
/home/shenss/.bun/bin/bun run test:auth
/home/shenss/.bun/bin/bun run build
```
