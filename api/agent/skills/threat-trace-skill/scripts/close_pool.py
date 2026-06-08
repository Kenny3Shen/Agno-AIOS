#!/home/shenss/python/fastapi/.venv/bin/python3
"""释放威胁情报数据库连接池"""

import asyncio

from base import _close_pool


async def _main_async() -> int:
    await _close_pool()
    return 0


def main() -> int:
    return asyncio.run(_main_async())


if __name__ == "__main__":
    raise SystemExit(main())
