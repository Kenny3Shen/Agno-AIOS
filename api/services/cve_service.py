import aiomysql


async def search_cves(
    pool: aiomysql.Pool,
    query: str,
    source: str | None = None,
    page: int = 1,
    size: int = 10,
) -> tuple[list[dict], int]:
    """统一的 CVE 搜索函数：按 cve_id 或 description 匹配查询词"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            conditions = ["(cve_id LIKE %s OR description LIKE %s)"]
            params = [f"%{query}%", f"%{query}%"]

            if source:
                conditions.append("source = %s")
                params.append(source)

            where_clause = " AND ".join(conditions)

            count_sql = f"SELECT COUNT(*) as count FROM cves WHERE {where_clause}"
            await cursor.execute(count_sql, params)
            count_result = await cursor.fetchone()
            total = count_result["count"] if count_result else 0

            sql = f"SELECT * FROM cves WHERE {where_clause} ORDER BY id DESC LIMIT %s OFFSET %s"
            params.extend([size, (page - 1) * size])
            await cursor.execute(sql, params)
            result = await cursor.fetchall()

            return result, total
