from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.config import Settings


def _secure_production_values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "environment": "production",
        "auth_jwt_secret": "jwt-secret-that-is-not-a-development-default",
        "auth_reset_password_secret": "reset-secret-that-is-not-a-development-default",
        "auth_verification_secret": "verify-secret-that-is-not-a-development-default",
        "auth_oauth_state_secret": "oauth-state-that-is-not-a-development-default",
        "cors_origins": ["https://console.example.test"],
        "trusted_hosts": ["api.example.test"],
        "auth_cookie_secure": True,
        "github_oauth_client_id": "",
        "github_oauth_client_secret": "",
        "google_oauth_client_id": "",
        "google_oauth_client_secret": "",
        "microsoft_oauth_client_id": "",
        "microsoft_oauth_client_secret": "",
    }
    values.update(overrides)
    return values


def test_development_keeps_existing_convenient_defaults() -> None:
    settings = Settings.model_validate(
        {
            "environment": "development",
            "cors_origins": ["*"],
            "auth_cookie_secure": False,
        }
    )

    assert settings.cors_origins == ["*"]
    assert settings.auth_cookie_secure is False


def test_threat_intel_source_configs_default_under_config_dir() -> None:
    """CVE / IP blacklist feed TOML defaults live under config/, not repo root."""
    settings = Settings.model_validate({"environment": "development"})
    assert settings.cve_source_config_path == "config/cve_sources.toml"
    assert settings.ip_blacklist_source_config_path == "config/ip_blacklist_sources.toml"
    assert not settings.cve_source_config_path.startswith("cve_")
    assert not settings.ip_blacklist_source_config_path.startswith("ip_")


@pytest.mark.parametrize(
    ("field_name", "insecure_value", "expected_name"),
    [
        (
            "auth_jwt_secret",
            "change-me-in-production-auth-jwt-secret-32-bytes-min",
            "AUTH_JWT_SECRET",
        ),
        (
            "auth_reset_password_secret",
            "change-me-in-production-reset-secret-32-bytes-min",
            "AUTH_RESET_PASSWORD_SECRET",
        ),
        (
            "auth_verification_secret",
            "change-me-in-production-verification-secret-32-bytes-min",
            "AUTH_VERIFICATION_SECRET",
        ),
        (
            "auth_oauth_state_secret",
            "change-me-in-production-oauth-state-secret-32-bytes-min",
            "AUTH_OAUTH_STATE_SECRET",
        ),
    ],
)
def test_production_rejects_default_auth_secrets(
    field_name: str,
    insecure_value: str,
    expected_name: str,
) -> None:
    values = _secure_production_values(**{field_name: insecure_value})

    with pytest.raises(ValidationError, match=expected_name):
        Settings.model_validate(values)


def test_production_rejects_template_secret_placeholders() -> None:
    values = _secure_production_values(
        auth_jwt_secret="replace-with-long-random-secret"
    )

    with pytest.raises(ValidationError, match="AUTH_JWT_SECRET"):
        Settings.model_validate(values)


def test_production_rejects_wildcard_cors() -> None:
    values = _secure_production_values(cors_origins=["*"])

    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings.model_validate(values)


def test_production_rejects_wildcard_trusted_hosts() -> None:
    values = _secure_production_values(trusted_hosts=["*"])

    with pytest.raises(ValidationError, match="TRUSTED_HOSTS"):
        Settings.model_validate(values)


def test_production_requires_secure_cookie_for_configured_oauth() -> None:
    values = _secure_production_values(
        auth_cookie_secure=False,
        github_oauth_client_id="github-client-id",
        github_oauth_client_secret="github-client-secret",
    )

    with pytest.raises(ValidationError, match="AUTH_COOKIE_SECURE"):
        Settings.model_validate(values)


def test_production_allows_configured_oauth_with_a_secure_cookie() -> None:
    settings = Settings.model_validate(
        _secure_production_values(
            github_oauth_client_id="github-client-id",
            github_oauth_client_secret="github-client-secret",
        )
    )

    assert settings.oauth_is_configured is True


def test_production_allows_non_cookie_bearer_only_deployment() -> None:
    settings = Settings.model_validate(
        _secure_production_values(environment="prod", auth_cookie_secure=False)
    )

    assert settings.auth_cookie_secure is False
    assert settings.oauth_is_configured is False
