from __future__ import annotations

import sys

from loguru import logger

from api.config import Settings, get_settings


def configure_logging(settings: Settings | None = None) -> None:
    active_settings = settings or get_settings()
    active_settings.log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(sys.stderr, level=active_settings.log_level)
    logger.add(
        active_settings.log_path,
        level=active_settings.log_level,
        rotation="10 MB",
        retention="10 days",
    )
