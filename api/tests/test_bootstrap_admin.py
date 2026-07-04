from __future__ import annotations
import inspect
from api.config import Settings


def test_bootstrap_admin_is_disabled_by_default() -> None:
    settings = Settings.model_validate({})
    assert settings.bootstrap_admin_email == ""
    assert settings.bootstrap_admin_password.get_secret_value() == ""


def test_bootstrap_admin_env_aliases_are_supported() -> None:
    settings = Settings.model_validate(
        {
            "AGNO_BOOTSTRAP_ADMIN_EMAIL": "admin@example.com",
            "AGNO_BOOTSTRAP_ADMIN_PASSWORD": "AdminPass123!",
        }
    )
    assert settings.bootstrap_admin_email == "admin@example.com"
    assert settings.bootstrap_admin_password.get_secret_value() == "AdminPass123!"


def test_bootstrap_admin_upserts_superuser_admin() -> None:
    from api.auth import database

    source = inspect.getsource(database.bootstrap_admin_user)
    assert "ON CONFLICT (email) DO UPDATE" in source
    assert "is_superuser = true" in source
    assert "role = 'admin'" in source
    assert "PasswordHelper" in source
