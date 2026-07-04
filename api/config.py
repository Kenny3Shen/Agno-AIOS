from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Agno AIOS Security Platform API"
    app_version: str = "0.5.0"
    environment: str = "development"

    log_level: str = "INFO"
    log_dir: Path = Path("logs")
    log_file: str = "poc.log"

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    postgres_host: str = Field(
        default="localhost", validation_alias=AliasChoices("POSTGRES_HOST", "AGNO_POSTGRES_HOST")
    )
    postgres_port: int = Field(
        default=5432, validation_alias=AliasChoices("POSTGRES_PORT", "AGNO_POSTGRES_PORT")
    )
    postgres_user: str = Field(
        default="agno_aios", validation_alias=AliasChoices("POSTGRES_USER", "AGNO_POSTGRES_USER")
    )
    postgres_password: SecretStr = Field(
        default=SecretStr("agno_aios"),
        validation_alias=AliasChoices("POSTGRES_PASSWORD", "AGNO_POSTGRES_PASSWORD"),
    )
    postgres_db: str = Field(
        default="agno_aios", validation_alias=AliasChoices("POSTGRES_DB", "AGNO_POSTGRES_DB")
    )
    postgres_url: str | None = Field(
        default=None, validation_alias=AliasChoices("AGNO_POSTGRES_URL", "POSTGRES_URL")
    )
    postgres_sqlalchemy_url_override: str | None = Field(
        default=None, validation_alias="AGNO_POSTGRES_SQLALCHEMY_URL"
    )

    agno_app_schema: str = "app"
    agno_db_schema: str = "agno"
    agno_mcp_schema: str = "mcp"
    agno_knowledge_schema: str = "knowledge"
    agno_postgres_knowledge_table: str = "agno_knowledge"

    mcp_server_url: str = "http://127.0.0.1:8000/mcp/"
    mcp_token: SecretStr = Field(
        default=SecretStr(""), validation_alias=AliasChoices("MCP_TOKEN", "MCP_Token")
    )
    feishu_webhook_url: SecretStr = SecretStr("")

    celery_broker_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("CELERY_BROKER_URL", "AGNO_CELERY_BROKER_URL"),
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("CELERY_RESULT_BACKEND", "AGNO_CELERY_RESULT_BACKEND"),
    )
    scheduler_enabled: bool = Field(default=True, validation_alias="AGNO_SCHEDULER_ENABLED")
    scheduler_poll_interval_seconds: int = Field(default=15, validation_alias="AGNO_SCHEDULER_POLL_INTERVAL_SECONDS")
    scheduler_base_url: str = Field(default="http://127.0.0.1:8000", validation_alias="AGNO_SCHEDULER_BASE_URL")
    scheduler_internal_service_token: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="AGNO_SCHEDULER_INTERNAL_SERVICE_TOKEN",
    )

    acl_username: str = ""
    acl_password: SecretStr = SecretStr("")
    acl_token: SecretStr = Field(default=SecretStr(""), validation_alias="TOKEN")

    auth_jwt_secret: SecretStr = SecretStr(
        "change-me-in-production-auth-jwt-secret-32-bytes-min"
    )
    auth_reset_password_secret: SecretStr = SecretStr(
        "change-me-in-production-reset-secret-32-bytes-min"
    )
    auth_verification_secret: SecretStr = SecretStr(
        "change-me-in-production-verification-secret-32-bytes-min"
    )
    auth_oauth_state_secret: SecretStr = SecretStr(
        "change-me-in-production-oauth-state-secret-32-bytes-min"
    )
    auth_token_lifetime_seconds: int = 3600
    auth_cookie_secure: bool = False
    bootstrap_admin_email: str = Field(
        default="",
        validation_alias=AliasChoices("AGNO_BOOTSTRAP_ADMIN_EMAIL", "BOOTSTRAP_ADMIN_EMAIL"),
    )
    bootstrap_admin_password: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices(
            "AGNO_BOOTSTRAP_ADMIN_PASSWORD",
            "BOOTSTRAP_ADMIN_PASSWORD",
        ),
    )

    oauth_associate_by_email: bool = True
    oauth_is_verified_by_default: bool = True

    github_oauth_client_id: str = ""
    github_oauth_client_secret: SecretStr = SecretStr("")
    github_oauth_redirect_url: str | None = None

    google_oauth_client_id: str = ""
    google_oauth_client_secret: SecretStr = SecretStr("")
    google_oauth_redirect_url: str | None = None

    microsoft_oauth_client_id: str = ""
    microsoft_oauth_client_secret: SecretStr = SecretStr("")
    microsoft_oauth_tenant: str = "common"
    microsoft_oauth_redirect_url: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return value
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @property
    def log_path(self) -> Path:
        return self.log_dir / self.log_file

    @property
    def postgres_dsn(self) -> str:
        if self.postgres_url:
            return self.postgres_url
        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql://{quote_plus(self.postgres_user)}:{quote_plus(password)}"
            f"@{self.postgres_host}:{self.postgres_port}/{quote_plus(self.postgres_db)}"
        )

    @property
    def postgres_sqlalchemy_url(self) -> str:
        if self.postgres_sqlalchemy_url_override:
            return self.postgres_sqlalchemy_url_override
        return self.postgres_dsn.replace("postgresql://", "postgresql+psycopg://", 1)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
