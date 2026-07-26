from collections.abc import Callable
from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import cast

from sqlalchemy import Column, MetaData, String, Table, Text, create_engine, insert, select
from sqlalchemy.sql.dml import Update


@lru_cache(maxsize=1)
def _xai_canonicalization_revision() -> ModuleType:
    revision_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20260720_0002_canonicalize_xai_model_configs.py"
    )
    spec = spec_from_file_location("xai_canonicalization_revision", revision_path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonicalization_statement(table: Table) -> Update:
    statement = getattr(
        _xai_canonicalization_revision(),
        "_xai_model_config_canonicalization_statement",
    )
    return cast(Callable[[Table], Update], statement)(table)


@lru_cache(maxsize=1)
def _remove_builtin_model_seeds_revision() -> ModuleType:
    revision_path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20260726_0032_remove_builtin_model_seeds.py"
    )
    spec = spec_from_file_location("remove_builtin_model_seeds_revision", revision_path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _delete_unconfigured_local_models_statement(table: Table):
    statement = getattr(
        _remove_builtin_model_seeds_revision(),
        "_delete_unconfigured_local_models_statement",
    )
    return statement(table)


def _row(
    row_id: str,
    *,
    provider: str,
    model_id: str,
    api_protocol: str,
    default_reasoning_effort: str | None,
    base_url: str = "https://api.example.com/v1",
) -> dict[str, object]:
    return {
        "id": row_id,
        "model_id": model_id,
        "provider": provider,
        "api_protocol": api_protocol,
        "default_reasoning_effort": default_reasoning_effort,
        "base_url": base_url,
    }


def test_xai_alembic_migration_updates_only_legacy_rows() -> None:
    metadata = MetaData()
    table = Table(
        "model_configs",
        metadata,
        Column("id", String, primary_key=True),
        Column("provider", String),
        Column("model_id", Text),
        Column("api_protocol", String),
        Column("default_reasoning_effort", String),
        Column("base_url", Text),
    )
    engine = create_engine("sqlite://")
    try:
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(
                insert(table),
                [
                    _row(
                        "legacy-grok",
                        provider="openai-compatible",
                        model_id="grok-4.5",
                        api_protocol="responses",
                        default_reasoning_effort="high",
                        base_url="https://api.x.ai/v1",
                    ),
                    _row(
                        "stale-xai",
                        provider="XAI",
                        model_id="grok-4.5",
                        api_protocol="responses",
                        default_reasoning_effort="high",
                    ),
                    _row(
                        "stale-xai-reasoning",
                        provider="xai",
                        model_id="grok-4.5",
                        api_protocol="chat-completions",
                        default_reasoning_effort="high",
                    ),
                    _row(
                        "compatible",
                        provider="openai-compatible",
                        model_id="custom-model",
                        api_protocol="responses",
                        default_reasoning_effort="high",
                    ),
                ],
            )
            result = connection.execute(
                _canonicalization_statement(table)
            )
            rows = {
                str(row["id"]): dict(row)
                for row in connection.execute(select(table)).mappings()
            }
    finally:
        engine.dispose()

    assert result.rowcount == 3
    for row_id in ("legacy-grok", "stale-xai", "stale-xai-reasoning"):
        assert rows[row_id]["provider"] == "xai"
        assert rows[row_id]["api_protocol"] == "chat-completions"
        assert rows[row_id]["default_reasoning_effort"] is None
    assert rows["compatible"]["provider"] == "openai-compatible"
    assert rows["compatible"]["api_protocol"] == "responses"
    assert rows["compatible"]["default_reasoning_effort"] == "high"


def test_local_model_seed_migration_deletes_only_blank_legacy_entries() -> None:
    metadata = MetaData()
    table = Table(
        "model_configs",
        metadata,
        Column("id", String, primary_key=True),
        Column("api_key", Text),
    )
    engine = create_engine("sqlite://")
    try:
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(
                insert(table),
                [
                    {"id": "deepseek-v4-flash", "api_key": "real-secret"},
                    {"id": "deepseek-v4-pro", "api_key": "   "},
                    {"id": "xai-grok-4.5", "api_key": None},
                    {"id": "deepseek-v4-flash-configured", "api_key": ""},
                ],
            )
            connection.execute(_delete_unconfigured_local_models_statement(table))
            rows = {
                str(row["id"]): dict(row)
                for row in connection.execute(select(table)).mappings()
            }
    finally:
        engine.dispose()

    assert rows == {
        "deepseek-v4-flash": {"id": "deepseek-v4-flash", "api_key": "real-secret"},
        "deepseek-v4-flash-configured": {
            "id": "deepseek-v4-flash-configured",
            "api_key": "",
        },
    }
