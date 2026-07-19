"""Runtime checks for the Alembic-owned control-plane schema.

Application processes deliberately never create or alter repository tables.
Deployments run ``alembic upgrade head`` as a release step; API and worker
processes only verify that the resulting revision is present before serving
traffic.  Agno-owned session/vector tables are intentionally outside this
check because their lifecycle follows the pinned Agno release.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from api.persistence.database import get_async_control_plane_engine
from api.utils.async_once import AsyncOnce


class ControlPlaneSchemaOutdatedError(RuntimeError):
    """Raised when an API/worker starts before its Alembic revision is applied."""


_schema_checked_once = AsyncOnce()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def control_plane_head_revision() -> str:
    """Return the repository's Alembic head without opening a database connection."""
    config = Config(str(_project_root() / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    head = script.get_current_head()
    if not head:
        raise RuntimeError("Alembic has no control-plane head revision")
    return str(head)


async def control_plane_current_revision() -> str | None:
    """Return the database revision, or ``None`` when Alembic has never run."""
    try:
        async with get_async_control_plane_engine().connect() as connection:
            value = await connection.scalar(text("SELECT version_num FROM alembic_version"))
    except SQLAlchemyError:
        return None
    return str(value) if value is not None else None


async def assert_control_plane_schema_current() -> None:
    """Fail closed when this process and the database schema do not match."""
    expected = control_plane_head_revision()
    current = await control_plane_current_revision()
    if current != expected:
        found = current or "none"
        raise ControlPlaneSchemaOutdatedError(
            "Control-plane schema is not at the application revision "
            f"(database={found}, expected={expected}). "
            "Run `uv run alembic upgrade head` before starting API or workers."
        )


async def ensure_control_plane_schema_current() -> None:
    """Check the migration revision at most once per process startup."""
    await _schema_checked_once.run(assert_control_plane_schema_current)


async def control_plane_schema_is_current() -> bool:
    """Readiness-friendly non-raising variant of the revision check."""
    try:
        await assert_control_plane_schema_current()
    except (ControlPlaneSchemaOutdatedError, RuntimeError):
        return False
    return True
