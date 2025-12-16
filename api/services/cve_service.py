import aiomysql


async def search_cves_by_id(
    pool: aiomysql.Pool,
    cve_id_query: str,
    page: int = 1,
    size: int = 10,
    source: str | None = None,
) -> tuple[list[dict], int]:
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            count_sql = "SELECT COUNT(*) as count FROM cves WHERE cve_id LIKE %s"
            sql = "SELECT * FROM cves WHERE cve_id LIKE %s"
            params = [f"%{cve_id_query}%"]

            if source is not None:
                count_sql += " AND source = %s"
                sql += " AND source = %s"
                params.append(source)

            sql += " ORDER BY id DESC LIMIT %s OFFSET %s"
            params.extend([size, (page - 1) * size])

            await cursor.execute(count_sql, params[:-2])
            count_result = await cursor.fetchone()
            total = count_result["count"] if count_result else 0

            await cursor.execute(sql, params)
            result = await cursor.fetchall()
            return result, total


async def search_cves_by_description(
    pool: aiomysql.Pool,
    keyword_query: str,
    page: int = 1,
    size: int = 10,
    source: str | None = None,
) -> tuple[list[dict], int]:
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            count_sql = "SELECT COUNT(*) as count FROM cves WHERE description LIKE %s"
            sql = "SELECT * FROM cves WHERE description LIKE %s"
            params = [f"%{keyword_query}%"]

            if source is not None:
                count_sql += " AND source = %s"
                sql += " AND source = %s"
                params.append(source)

            sql += " ORDER BY id DESC LIMIT %s OFFSET %s"
            params.extend([size, (page - 1) * size])

            await cursor.execute(count_sql, params[:-2])
            count_result = await cursor.fetchone()
            total = count_result["count"] if count_result else 0

            await cursor.execute(sql, params)
            result = await cursor.fetchall()
            return result, total
