from api.database.cve_db import search_cves_by_id_paginated, update_cve_database
from loguru import logger
from ..utils.cve_utils import parse_cve_markdown
import os
import httpx


async def search_cves(cve_id: str, page: int, size: int) -> tuple[list[dict], int]:
    """Search CVEs by ID with pagination"""
    items, total = await search_cves_by_id_paginated(cve_id, page, size)
    return items, total


async def refresh_cve_database() -> tuple[int, int]:
    cve_md = "https://raw.githubusercontent.com/ycdxsb/PocOrExp_in_Github/refs/heads/main/PocOrExp.md"
    local_poc_path = os.path.join("./api/data", "PocOrExp.md")
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(cve_md)
            resp.raise_for_status()
            new_PocOrExp = resp.text
    except Exception as e:
        # Log the exception with stack trace
        logger.exception("Failed to fetch remote CVE markdown: {}", e)
        raise
    old_PocOrExp = ""

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
        item
        for item in new_parsed_data
        if (item["cve_id"], item["github_url"]) not in old_keys
    ]

    # 删除：在旧数据中但不在新数据中（远程已移除）
    deleted_data = [
        item
        for item in old_parsed_data
        if (item["cve_id"], item["github_url"]) not in new_keys
    ]

    # Consolidated log to avoid overly verbose output
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
            new_count, del_count = await update_cve_database(
                increment_data, deleted_data
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
