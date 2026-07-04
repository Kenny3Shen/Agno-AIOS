from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine

from api.config import get_settings


@lru_cache(maxsize=1)
def get_control_plane_engine() -> Engine:
    return create_engine(get_settings().postgres_sqlalchemy_url, pool_pre_ping=True)


def dispose_control_plane_engine() -> None:
    get_control_plane_engine().dispose()
    get_control_plane_engine.cache_clear()
