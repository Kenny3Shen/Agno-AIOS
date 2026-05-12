# CVE & IP资产情报平台

基于 FastAPI 和 Vue.js 的安全情报查询平台，支持 CVE 漏洞和 IP 资产信息的查询与管理。

## 功能特性

- **CVE 查询**: 搜索和查看 CVE 漏洞信息及相关 GitHub PoC/Exp
- **资产搜索**: 基于指纹信息搜索 IP 资产
- **LLM 聊天**: 智能问答助手，辅助安全分析

## 项目结构

```
.
├── api/                    # 后端 API
│   ├── main.py            # FastAPI 应用入口
│   ├── routes/            # API 路由
│   ├── services/          # 业务逻辑
│   ├── database/          # 数据库操作
│   ├── models/            # 数据模型
│   ├── utils/             # 工具函数
│   └── data/              # 数据文件和缓存
├── frontend/              # 前端 Vue.js 应用
│   ├── src/               # 源代码
│   ├── public/            # 静态资源
│   └── dist/              # 构建输出
├── config.toml            # 配置文件
├── update_cve.py          # CVE 数据更新脚本
├── update_ip_asset.py     # IP 资产数据更新脚本
├── update_utils.py        # 数据更新工具
├── run_update_cve.sh      # CVE 更新脚本包装器
├── pyproject.toml         # Python 项目配置
├── main.py                # 占位符文件
└── README.md              # 项目说明
```

## 环境要求

- Python 3.10+
- Node.js 18+ 或 Bun (前端开发)
- MySQL 5.7+
- uv (Python 包管理工具)

## 安装与配置

### 1. 安装依赖

```bash
# 安装 Python 依赖
uv sync

# 安装前端依赖
cd frontend
bun install  # 或 npm install
```

### 2. 配置环境变量

创建 `.env` 文件或设置以下环境变量：

```bash
# 数据库配置
MYSQL_TEST_HOST=localhost
MYSQL_TEST_USER=root
MYSQL_TEST_PASSWORD=your_password
MYSQL_TEST_DATABASE=cve_db
MYSQL_TEST_PORT=3306

# ACL API 配置（用于 IP 资产更新）
ACL_USERNAME=your_username
ACL_PASSWORD=your_password

# 日志配置
LOG_LEVEL=INFO
LOG_DIR=logs
```

### 3. 数据库初始化

确保 MySQL 数据库已创建，并运行以下 SQL 创建表：

```sql
CREATE DATABASE cve_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE cve_db;

CREATE TABLE IF NOT EXISTS cves (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cve_id VARCHAR(255) NOT NULL,
    description TEXT,
    github_url VARCHAR(255) NOT NULL,
    source VARCHAR(50) NOT NULL,
    create_time DATETIME,
    UNIQUE KEY unique_cve_url (cve_id, github_url)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

## 使用说明

### 启动应用

```bash
# 启动后端服务
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# 启动前端开发服务器
cd frontend
bun run dev  # 或 npm run dev
```

访问 <http://localhost:5173> 使用应用

### 数据更新

#### 更新 CVE 数据

从 GitHub 仓库更新 CVE 漏洞信息：

```bash
# 使用默认数据源 (GitHub)
uv run update_cve.py

# 指定数据源
uv run update_cve.py --source github
```

**数据源说明：**

- `github`: 从 [ycdxsb/PocOrExp_in_Github](https://github.com/ycdxsb/PocOrExp_in_Github) 获取
- `exploit-db`: 从 Exploit Database 获取

**更新逻辑：**

1. 获取远程仓库最新 commit
2. 与本地 commit 对比，如果相同则跳过更新
3. 从远程获取最新数据
4. 与本地缓存对比，计算增量和删除
5. 批量更新数据库
6. 更新本地缓存文件和 commit 记录

**去重说明（重要）**

- 在写入数据库前，更新脚本会对来源数据进行去重（基于 `cve_id` 和 `github_url` 两字段的组合），避免插入重复记录从而触发数据库唯一性约束（`UNIQUE KEY unique_cve_url (cve_id, github_url)`）。

#### 更新 IP 资产数据

从 ACL API 获取并聚合 IP 资产信息：

```bash
uv run update_ip_asset.py
```

**更新流程：**

1. 登录 ACL API 获取 token（支持自动重试）
2. 拉取所有 IP 实体数据
3. 保存原始数据到 `api/data/raw_ip_entities.json`
4. 聚合处理数据并缓存到 `api/data/aggregated_ip_entities.json`

**注意事项：**

- 需要配置 `ACL_USERNAME` 和 `ACL_PASSWORD` 环境变量
- 数据量较大时可能需要几分钟完成

### 定时任务

建议使用 cron 或 systemd timer 定期更新数据：

```bash
# 示例 crontab 配置
# 使用脚本 `run_update_cve.sh`（推荐）
# 每天 08:00 更新 CVE 数据（请根据实际路径修改）
0 8 * * * /home/shenss/python/fastapi/run_update_cve.sh >> /home/shenss/python/fastapi/logs/cron_cve.log 2>&1

# 或者直接使用 uv（不使用 wrapper 脚本）
0 8 * * * cd /home/shenss/python/fastapi && /usr/bin/env bash -lc 'set -a; [ -f /home/shenss/python/fastapi/.env ] && source /home/shenss/python/fastapi/.env; set +a; /home/shenss/python/fastapi/.venv/bin/uv run update_cve.py' >> /home/shenss/python/fastapi/logs/cron_cve.log 2>&1

# 每天 03:00 更新 IP 资产数据
0 3 * * * cd /home/shenss/python/fastapi && /usr/bin/env bash -lc 'set -a; [ -f /home/shenss/python/fastapi/.env ] && source /home/shenss/python/fastapi/.env; set +a; /home/shenss/python/fastapi/.venv/bin/uv run update_ip_asset.py' >> /home/shenss/python/fastapi/logs/cron_asset.log 2>&1
```

## API 接口

### CVE 相关

- `POST /api/cve/search` - 搜索 CVE

  ```json
  {
    "cve_id": "CVE-2024-1234",
    "page": 1,
    "size": 10
  }
  ```

### 资产相关

- `POST /api/asset/search` - 搜索资产

  ```json
  {
    "fingerprint": "Vue.js"
  }
  ```

### LLM 聊天

- `POST /api/chat` - 发送聊天消息

  ```json
  {
    "message": "查询 CVE-2024-1234"
  }
  ```

## 开发说明

### 代码质量

项目已完成全面的代码审计和优化：

- **中文化**: 所有日志记录、注释和文档字符串已转换为中文
- **错误处理**: 移除了无效的 try-except 包装，简化了错误处理逻辑
- **代码清理**: 删除了冗余代码，提高了代码可读性和维护性

### 前端开发

```bash
cd frontend
bun run dev     # 开发服务器
bun run build   # 生产构建
bun run preview # 预览构建结果
```

### 后端开发

```bash
# 运行测试
uv run pytest

# 代码格式化
uv run ruff format .

# 代码检查
uv run ruff check .
```

## 架构说明

### 前端架构

- **框架**: Vue 3 + TypeScript
- **UI 库**: Element Plus
- **样式**: Tailwind CSS
- **构建工具**: Vite + Bun
- **HTTP 客户端**: Axios

### 后端架构

- **框架**: FastAPI (异步)
- **数据库**: MySQL (aiomysql 异步驱动)
- **配置**: TOML 配置文件 + python-dotenv
- **日志**: loguru (支持轮转和保留)
- **HTTP 客户端**: httpx (异步)
- **数据处理**: Polars (高效 DataFrame 操作)

### 数据流

```
配置 (config.toml)
    ↓
更新脚本 (update_*.py)
    ↓
数据库 (MySQL) + 本地缓存 (api/data/)
    ↓
API Services (业务逻辑)
    ↓
API Routes (路由处理)
    ↓
前端组件 (Vue.js)
```

### 配置管理

项目使用 `config.toml` 进行数据源配置，支持：

- GitHub 数据源配置 (远程 URL、本地缓存路径、API 端点等)
- Exploit-DB 数据源配置
- 灵活的配置管理，便于部署和维护

## 故障排除

### 数据库连接失败

- 检查 MySQL 服务是否运行：`sudo systemctl status mysql`
- 验证环境变量配置是否正确
- 确认数据库和表已创建
- 检查用户权限：`GRANT ALL PRIVILEGES ON cve_db.* TO 'user'@'localhost';`

### ACL API 连接问题

- 检查网络连接和 ACL API 地址可访问性
- 验证 `ACL_USERNAME` 和 `ACL_PASSWORD` 环境变量
- 查看日志中的 token 获取和 API 调用错误
- 确认 ACL API 支持当前使用的端点和参数

### 前端无法连接后端

- 确认后端服务已启动：`uv run uvicorn api.main:app --host 0.0.0.0 --port 8000`
- 检查前端 `vite.config.ts` 中的代理配置
- 查看浏览器控制台和后端日志的 CORS 错误
- 确认防火墙设置允许相应端口

### 数据更新失败

- 检查网络连接和数据源可访问性
- 验证配置文件 `config.toml` 中的 URL 和路径
- 查看日志中的 commit 比较和数据获取错误
- 确认本地缓存目录权限：`chmod 755 api/data/`

### 性能问题

- CVE 数据量大时，首次更新可能较慢
- 考虑调整数据库索引和查询优化
- 定期清理日志文件：`find logs/ -name "*.log" -mtime +30 -delete`

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

---

**最后更新**: 2025年12月11日
