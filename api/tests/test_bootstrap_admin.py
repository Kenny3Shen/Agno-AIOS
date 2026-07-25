from __future__ import annotations

import pytest
from typing import cast

from api.config import Settings


def test_bootstrap_admin_is_disabled_by_default() -> None:
    settings = Settings.model_validate({})
    assert settings.bootstrap_admin_email == ""
    assert settings.bootstrap_admin_password.get_secret_value() == ""


def test_bootstrap_admin_env_names_are_supported() -> None:
    settings = Settings.model_validate(
        {
            "TAIS_BOOTSTRAP_ADMIN_EMAIL": "admin@example.com",
            "TAIS_BOOTSTRAP_ADMIN_PASSWORD": "AdminPass123!",
        }
    )
    assert settings.bootstrap_admin_email == "admin@example.com"
    assert settings.bootstrap_admin_password.get_secret_value() == "AdminPass123!"


@pytest.mark.asyncio
async def test_bootstrap_admin_writes_normalized_email_and_hashed_password(monkeypatch) -> None:
    from api.auth import database

    captured: dict[str, object] = {}

    class FakeConnection:
        async def execute(self, statement, params):
            captured["params"] = params
            captured["statement"] = str(statement)

    class FakeBegin:
        async def __aenter__(self):
            captured["began"] = True
            return FakeConnection()

        async def __aexit__(self, _exc_type, _exc, _tb):
            return None

    class FakeEngine:
        def begin(self):
            return FakeBegin()

    class FakePasswordHelper:
        def hash(self, password: str) -> str:
            captured["raw_password"] = password
            return f"hashed:{password}"

    monkeypatch.setattr(database, "auth_engine", FakeEngine())
    monkeypatch.setattr(database, "PasswordHelper", FakePasswordHelper)

    await database.bootstrap_admin_user(
        Settings.model_validate(
            {
                "TAIS_BOOTSTRAP_ADMIN_EMAIL": " Admin@Example.COM ",
                "TAIS_BOOTSTRAP_ADMIN_PASSWORD": "AdminPass123!",
            }
        )
    )

    params = cast(dict[str, object], captured["params"])
    assert params["email"] == "admin@example.com"
    assert params["hashed_password"] == "hashed:AdminPass123!"
    assert captured["raw_password"] == "AdminPass123!"
    statement = str(captured["statement"])
    assert '"user".hashed_password IS DISTINCT FROM EXCLUDED.hashed_password' in statement
    assert '"user".auth_version + 1' in statement
