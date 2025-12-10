import os
import sys
import aiomysql
import asyncio
from datetime import datetime
import re
import httpx
from loguru import logger


LOCAL_DB_CONDFIG = {
    "host": os.getenv("MYSQL_TEST_HOST"),
    "user": os.getenv("MYSQL_TEST_USER"),
    "password": os.getenv("MYSQL_TEST_PASSWORD"),
    "db": os.getenv("MYSQL_TEST_DATABASE"),
    "port": 3306,
    "charset": "utf8mb4",
}


# Configure logger
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)
log_dir = os.getenv("LOG_DIR", "logs")
os.makedirs(log_dir, exist_ok=True)
logger.add(
    os.path.join(log_dir, "poc.log"),
    level=LOG_LEVEL,
    rotation="10 MB",
    retention="10 days",
)


def parse_cve_markdown(text: str) -> list[dict[str, str]]:
    """
    解析 Markdown 文本，提取 CVE 信息。
    返回一个列表，每个元素是一个字典：
    {
        'cve_id': str,
        'description': str,
        'github_url': str
    }
    """
    if not text:
        logger.warning("parse_cve_markdown called with empty text")
        return []

    lines = text.strip().split("\n")
    cve_data = []
    current_cve = None
    current_desc = []

    # 正则表达式
    cve_pattern = re.compile(r"^##\s*(CVE-\d{4}-\d+)")
    url_pattern = re.compile(r"-\s*\[(https://github\.com/[^\]]+)\]")

    for line in lines:
        line = line.strip()

        # 匹配 CVE 标题
        cve_match = cve_pattern.match(line)
        if cve_match:
            if current_cve and not any(d["cve_id"] == current_cve for d in cve_data):
                cve_data.append(
                    {
                        "cve_id": current_cve,
                        "description": "\n".join(current_desc).strip(),
                        "github_url": "",
                    }
                )

            current_cve = cve_match.group(1)
            current_desc = []
            continue

        # 匹配 GitHub URL
        url_match = url_pattern.match(line)
        if url_match:
            if current_cve:
                url = url_match.group(1)
                cve_data.append(
                    {
                        "cve_id": current_cve,
                        "description": "\n".join(current_desc).strip(),
                        "github_url": url,
                    }
                )
            continue

        if (
            current_cve
            and not line.startswith("##")
            and not line.startswith("![")
            and line
        ):
            current_desc.append(line)

    if current_cve and not any(d["cve_id"] == current_cve for d in cve_data):
        cve_data.append(
            {
                "cve_id": current_cve,
                "description": "\n".join(current_desc).strip(),
                "github_url": "",
            }
        )

    return cve_data


async def update_database(
    increment_data: list[dict[str, str]],
    deleted_data: list[dict[str, str]],
    config: dict,
) -> tuple[int, int]:
    """
    异步同步 MySQL 数据库：
    - 插入新增数据（INSERT IGNORE）
    - 删除远程已移除的数据（DELETE）
    返回 (新增条数, 删除条数)
    """

    # 检查数据库配置
    if not config or not config.get("host"):
        logger.error(
            "DATABASE CONFIG is missing or invalid. ENV variables may be unset."
        )
        raise ValueError("Invalid DB config")

    logger.info(
        "创建数据库连接池，准备新增 {} 条、删除 {} 条记录",
        len(increment_data),
        len(deleted_data),
    )
    # 创建连接池
    pool = await aiomysql.create_pool(**config)

    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                # 1. 创建表
                await cursor.execute("""
                CREATE TABLE IF NOT EXISTS cves (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    cve_id VARCHAR(255) NOT NULL,
                    description TEXT,
                    github_url VARCHAR(255),
                    create_time DATETIME,
                    UNIQUE KEY unique_cve_url (cve_id, github_url)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
                """)

                new_count = 0
                del_count = 0

                # 开启事务
                await conn.begin()

                try:
                    # 2. 插入新增数据
                    for item in increment_data:
                        create_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        await cursor.execute(
                            """
                            INSERT IGNORE INTO cves (cve_id, description, github_url, create_time)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (
                                item["cve_id"],
                                item["description"],
                                item["github_url"],
                                create_time,
                            ),
                        )
                        if cursor.rowcount > 0:
                            new_count += 1

                    # 3. 删除远程已移除的数据
                    for item in deleted_data:
                        await cursor.execute(
                            """
                            DELETE FROM cves WHERE cve_id = %s AND github_url = %s
                            """,
                            (item["cve_id"], item["github_url"]),
                        )
                        if cursor.rowcount > 0:
                            del_count += 1

                    await conn.commit()
                except Exception as e:
                    await conn.rollback()
                    logger.exception("同步过程中出错，已回滚: {}", e)
                    raise

                await cursor.execute("SELECT count(*) FROM cves")
                result = await cursor.fetchone()
                total_count = result[0]

                logger.info(
                    "同步完成。新增: {} 条，删除: {} 条，数据库总记录: {} 条。",
                    new_count,
                    del_count,
                    total_count,
                )
                return new_count, del_count
    finally:
        pool.close()
        await pool.wait_closed()


# --- 主逻辑 ---
async def main() -> tuple[int, int]:
    cve_md = "https://raw.githubusercontent.com/ycdxsb/PocOrExp_in_Github/refs/heads/main/PocOrExp.md"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(cve_md)
            resp.raise_for_status()
            new_PocOrExp = resp.text
    except Exception as e:
        logger.exception("Failed to fetch remote CVE markdown: {}", e)
        raise
    old_PocOrExp = ""

    local_poc_path = local_poc_path = os.path.join("./api/data", "PocOrExp.md")
    if os.path.exists(local_poc_path):
        with open(local_poc_path, "r", encoding="utf-8") as f:
            old_PocOrExp = f.read()
    else:
        logger.info("本地不存在 PocOrExp.md，将视为全量更新。")

    # 1. 解析数据
    new_parsed_data = parse_cve_markdown(new_PocOrExp)
    old_parsed_data = parse_cve_markdown(old_PocOrExp)

    # 2. 计算增量与删除 (根据 cve_id 和 github_url 去重)
    old_keys = {(item["cve_id"], item["github_url"]) for item in old_parsed_data}
    new_keys = {(item["cve_id"], item["github_url"]) for item in new_parsed_data}

    # 新增：在新数据中但不在旧数据中
    increment_data = [
        item for item in new_parsed_data
        if (item["cve_id"], item["github_url"]) not in old_keys
    ]

    # 删除：在旧数据中但不在新数据中（远程已移除）
    deleted_data = [
        item for item in old_parsed_data
        if (item["cve_id"], item["github_url"]) not in new_keys
    ]

    logger.info(
        "解析完成：本地旧数据 {}, 远程新数据 {}, 增量 {}, 待删除 {}",
        len(old_parsed_data),
        len(new_parsed_data),
        len(increment_data),
        len(deleted_data),
    )

    # 3. 如果有增量或删除，更新数据库并保存本地文件
    if increment_data or deleted_data:
        try:
            new_count, del_count = await update_database(
                increment_data, deleted_data, LOCAL_DB_CONDFIG
            )
            with open(local_poc_path, "w", encoding="utf-8") as f:
                f.write(new_PocOrExp)
            logger.info("本地文件 PocOrExp.md 已更新。")
            return new_count, del_count
        except Exception as e:
            logger.exception("同步处理失败: {}", e)
            raise

    else:
        logger.info("没有新的 CVE 数据，无需更新。")
        return 0, 0


if __name__ == "__main__":
    asyncio.run(main())
