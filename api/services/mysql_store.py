from __future__ import annotations

from typing import Any

import aiomysql

from api.config import get_settings
from api.services.runtime_env import load_runtime_env_async


def mysql_host() -> str:
    return get_settings().mysql_test_host


def mysql_port() -> int:
    return get_settings().mysql_test_port


def mysql_user() -> str:
    return get_settings().mysql_test_user


def mysql_password() -> str:
    return get_settings().mysql_test_password.get_secret_value()


def mysql_database() -> str:
    return get_settings().mysql_test_database


async def mysql_connect_async(database: str | None = None) -> aiomysql.Connection:
    await load_runtime_env_async()
    return await aiomysql.connect(
        host=mysql_host(),
        port=mysql_port(),
        user=mysql_user(),
        password=mysql_password(),
        db=database or mysql_database(),
        charset="utf8mb4",
        autocommit=True,
        cursorclass=aiomysql.DictCursor,
    )


def coerce_json_value(value: Any) -> Any:
    import json

    current = value
    for _ in range(3):
        if not isinstance(current, str):
            return current
        try:
            current = json.loads(current)
        except Exception:
            return current
    return current
