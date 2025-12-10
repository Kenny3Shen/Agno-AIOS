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
│   ├── routes/            # API 路由
│   ├── services/          # 业务逻辑
│   ├── database/          # 数据库操作
│   ├── models/            # 数据模型
│   ├── utils/             # 工具函数
│   └── data/              # 数据文件
├── frontend/              # 前端 Vue.js 应用
├── update_cve.py          # CVE 数据更新脚本
├── update_ip_asset.py     # IP 资产数据更新脚本
└── main.py                # FastAPI 应用入口

```

## 环境要求

- Python 3.10+
- Node.js 18+ (前端开发)
- MySQL 5.7+
- uv (Python 包管理工具)

## 安装与配置

### 1. 安装依赖

```bash
# 安装 Python 依赖
uv sync

# 安装前端依赖
cd frontend
npm install  # 或 bun install
```

### 2. 配置环境变量

创建 `.env` 文件或设置以下环境变量：

```bash
# 数据库配置
export MYSQL_TEST_HOST="localhost"
export MYSQL_TEST_USER="root"
export MYSQL_TEST_PASSWORD="your_password"
export MYSQL_TEST_DATABASE="cve_db"

# ACL API 配置（用于 IP 资产更新）
export ACL_USERNAME="your_username"
export ACL_PASSWORD="your_password"

# 日志配置
export LOG_LEVEL="INFO"
export LOG_DIR="logs"
```

## 使用说明

### 启动应用

```bash
# 启动后端服务
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# 启动前端开发服务器
cd frontend
npm run dev  # 或 bun run dev
```

访问 http://localhost:5173 使用应用

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
- 未来可扩展更多数据源 (NVD, CVEDetails 等)

**更新逻辑：**
1. 从远程获取最新数据
2. 与本地缓存对比，计算增量和删除
3. 批量更新数据库
4. 更新本地缓存文件

#### 更新 IP 资产数据

从 ACL API 获取并聚合 IP 资产信息：

```bash
uv run update_ip_asset.py
```

**更新流程：**
1. 登录 ACL API 获取 token
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
# 每天凌晨 2 点更新 CVE 数据
0 2 * * * cd /path/to/fastapi && /usr/bin/env bash -c 'source .env && uv run update_cve.py' >> logs/cron_cve.log 2>&1

# 每天凌晨 3 点更新 IP 资产数据
0 3 * * * cd /path/to/fastapi && /usr/bin/env bash -c 'source .env && uv run update_ip_asset.py' >> logs/cron_asset.log 2>&1
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

### 前端开发

```bash
cd frontend
npm run dev     # 开发服务器
npm run build   # 生产构建
npm run preview # 预览构建结果
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
- **构建**: Vite

### 后端架构
- **框架**: FastAPI
- **数据库**: MySQL (使用 aiomysql 异步驱动)
- **日志**: loguru
- **HTTP 客户端**: httpx

### 数据流

```
更新脚本 (update_*.py)
    ↓
数据库 / 本地缓存
    ↓
API Services
    ↓
API Routes
    ↓
前端组件
```

## 故障排除

### 数据库连接失败
- 检查 MySQL 服务是否运行
- 验证环境变量配置是否正确
- 确认数据库和表已创建

### ACL API 连接超时
- 检查网络连接
- 验证 ACL_USERNAME 和 ACL_PASSWORD
- 确认 API 地址可访问

### 前端无法连接后端
- 确认后端服务已启动 (默认 http://localhost:8000)
- 检查前端 vite.config.ts 中的代理配置
- 查看浏览器控制台错误信息

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
