# CVE 增量同步脚本（poc.py）

这是一个用于从远程 GitHub 仓库读取 `PocOrExp.md`（CVE 与 PoC/Exploit 列表）并将增量数据写入 MySQL 数据库的脚本。

重点目标：保持本地数据库只写入自上次同步后新增或删除的 CVE 条目（基于 cve_id + github_url 去重）。

---

## 🧭 功能概述

- 从远程 URL 下载 CVE Markdown 文件
- 解析 Markdown，提取 CVE 标题与 GitHub URL
- 与本地 `PocOrExp.md` 的历史数据比较，计算增量
- 将增量写入 MySQL（使用 `aiomysql` 连接池与事务）
- 写入成功后，将远程文件覆盖保存为本地 `PocOrExp.md`

---

## 🔧 环境与依赖

Python >= 3.12。
依赖项在 `pyproject.toml` 中定义：

- aiomysql
- loguru
- requests

推荐在虚拟环境中安装：

```fish
python -m venv .venv
source .venv/bin/activate.fish
pip install -e .
```

---

## 🔑 必要环境变量

在运行脚本前，请设置 MySQL 连接相关的环境变量（Fish shell 语法示例）：

```fish
set -x MYSQL_TEST_HOST 127.0.0.1
set -x MYSQL_TEST_USER myuser
set -x MYSQL_TEST_PASSWORD mypassword
set -x MYSQL_TEST_DATABASE mydb
set -x LOG_LEVEL INFO
set -x LOG_DIR logs
```

变量说明：

- `MYSQL_TEST_HOST`、`MYSQL_TEST_USER`、`MYSQL_TEST_PASSWORD`、`MYSQL_TEST_DATABASE`：数据库连接参数
- `LOG_LEVEL`（可选）：日志级别，默认 INFO
- `LOG_DIR`（可选）：日志输出目录，默认 `logs`，会自动创建

---

## ▶️ 运行脚本

在虚拟环境中直接运行：

```fish
python poc.py
```

脚本可能会抛出异常（网络错误或数据库错误），这些异常会通过 `loguru` 记录并回溯。
