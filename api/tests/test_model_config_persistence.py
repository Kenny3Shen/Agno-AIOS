from sqlalchemy import MetaData, create_engine, insert, select

from api.persistence import model_configs


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
        "name": row_id,
        "model_id": model_id,
        "provider": provider,
        "api_protocol": api_protocol,
        "structured_output_mode": "json",
        "default_reasoning_effort": default_reasoning_effort,
        "parallel_tool_calls": None,
        "live_search_enabled": False,
        "retries": 4,
        "delay_between_retries": 1,
        "exponential_backoff": True,
        "http_max_retries": None,
        "base_url": base_url,
        "api_key": "secret",
        "description": "",
        "enabled": True,
        "builtin": False,
        "active": False,
        "sort_order": 0,
        "created_at": 1,
        "updated_at": 1,
    }


def test_xai_model_config_migration_updates_only_legacy_rows() -> None:
    metadata = MetaData()
    table = model_configs.model_configs_table(metadata)
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
                        "compatible",
                        provider="openai-compatible",
                        model_id="custom-model",
                        api_protocol="responses",
                        default_reasoning_effort="high",
                    ),
                ],
            )
            result = connection.execute(
                model_configs._xai_model_config_migration_statement(table)
            )
            rows = {
                str(row["id"]): dict(row)
                for row in connection.execute(select(table)).mappings()
            }
    finally:
        engine.dispose()

    assert result.rowcount == 2
    for row_id in ("legacy-grok", "stale-xai"):
        assert rows[row_id]["provider"] == "xai"
        assert rows[row_id]["api_protocol"] == "chat-completions"
        assert rows[row_id]["default_reasoning_effort"] is None
    assert rows["compatible"]["provider"] == "openai-compatible"
    assert rows["compatible"]["api_protocol"] == "responses"
    assert rows["compatible"]["default_reasoning_effort"] == "high"
