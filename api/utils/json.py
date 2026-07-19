from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter, ValidationError

JSONDecodeError = ValidationError

_ANY_JSON = TypeAdapter(Any)


def loads(data: str | bytes | bytearray) -> Any:
    return _ANY_JSON.validate_json(data)


def dumps_bytes(
    value: Any,
    *,
    indent: bool = False,
    append_newline: bool = False,
) -> bytes:
    payload = _ANY_JSON.dump_json(value, indent=2 if indent else None)
    return payload + b"\n" if append_newline else payload


def dumps(
    value: Any,
    *,
    indent: bool = False,
    append_newline: bool = False,
) -> str:
    return dumps_bytes(
        value,
        indent=indent,
        append_newline=append_newline,
    ).decode("utf-8")
