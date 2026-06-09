from __future__ import annotations

import os
from functools import lru_cache
from typing import Any
from urllib.parse import quote_plus

import pymysql
import pymysql.cursors
from agno.db.mysql import MySQLDb
from dotenv import load_dotenv
from pymysql.connections import Connection

load_dotenv(override=True)


def mysql_host() -> str:
    return os.getenv("MYSQL_TEST_HOST", "localhost")


def mysql_port() -> int:
    return int(os.getenv("MYSQL_TEST_PORT", "3306"))


def mysql_user() -> str:
    return os.getenv("MYSQL_TEST_USER", "root")


def mysql_password() -> str:
    return os.getenv("MYSQL_TEST_PASSWORD", "")


def mysql_database() -> str:
    return os.getenv("MYSQL_TEST_DATABASE", "cve_db")


def mysql_sqlalchemy_url() -> str:
    user = quote_plus(mysql_user())
    password = quote_plus(mysql_password())
    host = mysql_host()
    port = mysql_port()
    database = quote_plus(mysql_database())
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"


def mysql_label(table_name: str) -> str:
    return f"mysql:{mysql_database()}.{table_name}"


def mysql_connect(database: str | None = None) -> Connection:
    return pymysql.connect(
        host=mysql_host(),
        port=mysql_port(),
        user=mysql_user(),
        password=mysql_password(),
        database=database or mysql_database(),
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


@lru_cache(maxsize=1)
def get_agno_mysql_db() -> MySQLDb:
    return MySQLDb(
        db_url=mysql_sqlalchemy_url(),
        db_schema=mysql_database(),
        session_table="agno_sessions",
        memory_table="agno_memories",
        traces_table="agno_traces",
        spans_table="agno_spans",
        versions_table="agno_schema_versions",
    )


def ensure_agno_mysql_tables() -> None:
    db = get_agno_mysql_db()
    get_table = getattr(db, "_get_table")
    for table_type in ("versions", "sessions", "memories", "traces", "spans"):
        get_table(table_type=table_type, create_table_if_not_found=True)


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
