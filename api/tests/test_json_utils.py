from __future__ import annotations

from datetime import UTC, datetime


def test_json_helpers_round_trip_utf8_and_datetime() -> None:
    from api.utils.json import dumps, loads

    payload = {"message": "安全运营", "created_at": datetime(2026, 7, 7, tzinfo=UTC)}

    encoded = dumps(payload)

    assert isinstance(encoded, str)
    assert "安全运营" in encoded
    assert loads(encoded)["created_at"] == "2026-07-07T00:00:00Z"


def test_json_helpers_can_return_bytes_and_pretty_text() -> None:
    from api.utils.json import dumps, dumps_bytes

    payload = {"items": [1, 2]}

    assert dumps_bytes(payload) == b'{"items":[1,2]}'
    assert dumps(payload, indent=True).startswith("{\n  ")


def test_json_helpers_parse_typed_objects_with_pydantic() -> None:
    from api.utils.json import loads_dict

    assert loads_dict(b'{"enabled":true}') == {"enabled": True}
