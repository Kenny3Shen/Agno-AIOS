from fastapi import Request, HTTPException
import aiomysql


def get_pool(request: Request) -> aiomysql.Pool:
    """Return the aiomysql pool stored on app.state.

    This is placed in a separate module to avoid circular imports between
    `api.main` and route modules that depend on it.
    """
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(503, "数据库连接未初始化，请稍后重试。")
    return pool
