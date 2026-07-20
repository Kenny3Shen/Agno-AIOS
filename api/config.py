from __future__ import annotations

from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from urllib.parse import quote_plus

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Single source: pyproject.toml [project].version (via importlib.metadata after install/uv sync).
_PACKAGE_NAME = "agno-aios"

_PRODUCTION_ENVIRONMENTS = frozenset({"prod", "production"})
_DEFAULT_AUTH_SECRETS = {
    "AUTH_JWT_SECRET": "change-me-in-production-auth-jwt-secret-32-bytes-min",
    "AUTH_RESET_PASSWORD_SECRET": "change-me-in-production-reset-secret-32-bytes-min",
    "AUTH_VERIFICATION_SECRET": "change-me-in-production-verification-secret-32-bytes-min",
    "AUTH_OAUTH_STATE_SECRET": "change-me-in-production-oauth-state-secret-32-bytes-min",
}
_INSECURE_SECRET_PLACEHOLDERS = frozenset({"", "replace-with-long-random-secret"})


def is_production_environment(environment: str) -> bool:
    """Return whether *environment* enables production safety guards."""
    return environment.strip().casefold() in _PRODUCTION_ENVIRONMENTS


def _default_app_version() -> str:
    try:
        return package_version(_PACKAGE_NAME)
    except PackageNotFoundError:
        return "0.0.0-dev"


class Settings(BaseSettings):
    """Runtime settings.

    Env naming:
    - TAIS_* / domain names (POSTGRES_*, AUTH_*, MCP_*): application config
    - AGNO_*: Agno engine coupling only (e.g. AGNO_DB_SCHEMA)
    """

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "T.A.I.S API"
    app_version: str = Field(default_factory=_default_app_version)
    environment: str = "development"

    log_level: str = "INFO"
    log_dir: Path = Path(".logs")
    log_file: str = "poc.log"

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    trusted_hosts: list[str] = Field(default_factory=lambda: ["*"])

    postgres_host: str = Field(default="localhost", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, validation_alias="POSTGRES_PORT")
    postgres_user: str = Field(default="agno_aios", validation_alias="POSTGRES_USER")
    postgres_password: SecretStr = Field(
        default=SecretStr("agno_aios"),
        validation_alias="POSTGRES_PASSWORD",
    )
    postgres_db: str = Field(default="agno_aios", validation_alias="POSTGRES_DB")
    postgres_url: str | None = Field(default=None, validation_alias="POSTGRES_URL")
    postgres_sqlalchemy_url_override: str | None = Field(
        default=None,
        validation_alias="TAIS_POSTGRES_SQLALCHEMY_URL",
    )

    # App control-plane schema (business tables).
    agno_app_schema: str = Field(default="app", validation_alias="TAIS_APP_SCHEMA")
    # Agno engine persistence schema.
    agno_db_schema: str = Field(default="agno", validation_alias="AGNO_DB_SCHEMA")
    agno_mcp_schema: str = Field(default="mcp", validation_alias="TAIS_MCP_SCHEMA")
    agno_knowledge_schema: str = Field(
        default="knowledge",
        validation_alias="TAIS_KNOWLEDGE_SCHEMA",
    )
    agno_postgres_knowledge_table: str = Field(
        default="agno_knowledge",
        validation_alias="TAIS_POSTGRES_KNOWLEDGE_TABLE",
    )

    agno_knowledge_name: str = Field(
        default="security_knowledge",
        validation_alias="TAIS_KNOWLEDGE_NAME",
    )
    agno_knowledge_pgvector_table: str = Field(
        default="security_knowledge_vectors",
        validation_alias="TAIS_KNOWLEDGE_PGVECTOR_TABLE",
    )
    agno_knowledge_upload_dir: Path = Field(
        default=Path(".config/knowledge_uploads"),
        validation_alias="TAIS_KNOWLEDGE_UPLOAD_DIR",
    )
    agno_knowledge_embedding_model: str = Field(
        default="BAAI/bge-small-zh-v1.5",
        validation_alias="TAIS_KNOWLEDGE_EMBEDDING_MODEL",
    )
    agno_knowledge_embedding_dimensions: int = Field(
        default=512,
        validation_alias="TAIS_KNOWLEDGE_EMBEDDING_DIMENSIONS",
    )
    agno_knowledge_rerank_model: str = Field(
        default="BAAI/bge-reranker-base",
        validation_alias="TAIS_KNOWLEDGE_RERANK_MODEL",
    )
    agno_knowledge_query_prompt: str = Field(
        default="为这个句子生成表示以用于检索相关文章：",
        validation_alias="TAIS_KNOWLEDGE_QUERY_PROMPT",
    )
    agno_knowledge_top_k: int = Field(default=5, validation_alias="TAIS_KNOWLEDGE_TOP_K")
    agno_knowledge_chunk_size: int = Field(
        default=1200,
        validation_alias="TAIS_KNOWLEDGE_CHUNK_SIZE",
    )
    agno_knowledge_chunk_overlap: int = Field(
        default=160,
        validation_alias="TAIS_KNOWLEDGE_CHUNK_OVERLAP",
    )
    agno_knowledge_code_chunk_size: int = Field(
        default=1800,
        validation_alias="TAIS_KNOWLEDGE_CODE_CHUNK_SIZE",
    )
    agno_knowledge_semantic_threshold: float = Field(
        default=0.52,
        validation_alias="TAIS_KNOWLEDGE_SEMANTIC_THRESHOLD",
    )
    agno_knowledge_vector_score_weight: float = Field(
        default=0.55,
        validation_alias="TAIS_KNOWLEDGE_VECTOR_SCORE_WEIGHT",
    )
    agno_knowledge_similarity_threshold: float | None = Field(
        default=0.35,
        validation_alias="TAIS_KNOWLEDGE_SIMILARITY_THRESHOLD",
        description=(
            "Minimum similarity / hybrid score (0.0-1.0) for retrieval. "
            "None or 0 disables score filtering; low-score chunks are dropped "
            "and empty results are allowed."
        ),
    )
    agno_knowledge_content_language: str = Field(
        default="english",
        validation_alias="TAIS_KNOWLEDGE_CONTENT_LANGUAGE",
    )
    agno_knowledge_prefix_match: bool = Field(
        default=False,
        validation_alias="TAIS_KNOWLEDGE_PREFIX_MATCH",
    )
    agno_knowledge_rerank_enabled: bool = Field(
        default=True,
        validation_alias="TAIS_KNOWLEDGE_RERANK_ENABLED",
    )
    agno_knowledge_rerank_candidate_multiplier: int = Field(
        default=3,
        validation_alias="TAIS_KNOWLEDGE_RERANK_CANDIDATE_MULTIPLIER",
    )
    agno_knowledge_rerank_min_candidates: int = Field(
        default=10,
        validation_alias="TAIS_KNOWLEDGE_RERANK_MIN_CANDIDATES",
    )
    agno_knowledge_search_type: str = Field(
        default="hybrid",
        validation_alias="TAIS_KNOWLEDGE_SEARCH_TYPE",
    )
    agno_skills_dir: str | None = Field(default=None, validation_alias="TAIS_SKILLS_DIR")
    agno_skills_config_file: str | None = Field(
        default=None,
        validation_alias="TAIS_SKILLS_CONFIG_FILE",
    )
    agno_upload_approval_dir: Path = Field(
        default=Path(".config/upload_approvals"),
        validation_alias="TAIS_UPLOAD_APPROVAL_DIR",
    )

    cve_source_config_path: str = Field(
        default="cve_sources.toml",
        validation_alias="TAIS_CVE_SOURCE_CONFIG_PATH",
    )
    cve_data_dir: Path = Field(
        default=Path(".config/cve"),
        validation_alias="TAIS_CVE_DATA_DIR",
    )
    cve_update_lock_path: Path = Field(
        default=Path("tmp/run_update_cve.lock"),
        validation_alias="TAIS_CVE_UPDATE_LOCK_PATH",
    )
    ip_blacklist_source_config_path: str = Field(
        default="ip_blacklist_sources.toml",
        validation_alias="TAIS_IP_BLACKLIST_SOURCE_CONFIG_PATH",
    )
    ip_blacklist_data_dir: Path = Field(
        default=Path(".config/ip_blacklist"),
        validation_alias="TAIS_IP_BLACKLIST_DATA_DIR",
    )
    ip_blacklist_update_lock_path: Path = Field(
        default=Path("tmp/run_update_ip_blacklist.lock"),
        validation_alias="TAIS_IP_BLACKLIST_UPDATE_LOCK_PATH",
    )
    github_token: SecretStr = Field(default=SecretStr(""), validation_alias="GITHUB_TOKEN")

    mcp_server_url: str = "http://127.0.0.1:8000/mcp/"
    mcp_token: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="MCP_TOKEN",
    )
    feishu_webhook_url: SecretStr = SecretStr("")

    auth_jwt_secret: SecretStr = SecretStr(_DEFAULT_AUTH_SECRETS["AUTH_JWT_SECRET"])
    auth_reset_password_secret: SecretStr = SecretStr(
        _DEFAULT_AUTH_SECRETS["AUTH_RESET_PASSWORD_SECRET"]
    )
    auth_verification_secret: SecretStr = SecretStr(
        _DEFAULT_AUTH_SECRETS["AUTH_VERIFICATION_SECRET"]
    )
    auth_oauth_state_secret: SecretStr = SecretStr(
        _DEFAULT_AUTH_SECRETS["AUTH_OAUTH_STATE_SECRET"]
    )
    auth_token_lifetime_seconds: int = 3600
    auth_cookie_secure: bool = False
    bootstrap_admin_email: str = Field(
        default="",
        validation_alias="TAIS_BOOTSTRAP_ADMIN_EMAIL",
    )
    bootstrap_admin_password: SecretStr = Field(
        default=SecretStr(""),
        validation_alias="TAIS_BOOTSTRAP_ADMIN_PASSWORD",
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

    @field_validator("cors_origins", "trusted_hosts", mode="before")
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
    def oauth_is_configured(self) -> bool:
        """Whether any OAuth provider will register its cookie-backed flow."""
        providers = (
            (self.github_oauth_client_id, self.github_oauth_client_secret),
            (self.google_oauth_client_id, self.google_oauth_client_secret),
            (self.microsoft_oauth_client_id, self.microsoft_oauth_client_secret),
        )
        return any(
            client_id.strip() and client_secret.get_secret_value().strip()
            for client_id, client_secret in providers
        )

    @model_validator(mode="after")
    def validate_production_security(self) -> Settings:
        """Fail closed when a production process is configured insecurely.

        Development intentionally retains convenient defaults.  Production must not
        start with credential defaults or an origin wildcard; OAuth additionally
        requires its CSRF cookie to be marked secure.
        """
        if not is_production_environment(self.environment):
            return self

        configured_secrets = {
            "AUTH_JWT_SECRET": self.auth_jwt_secret.get_secret_value(),
            "AUTH_RESET_PASSWORD_SECRET": self.auth_reset_password_secret.get_secret_value(),
            "AUTH_VERIFICATION_SECRET": self.auth_verification_secret.get_secret_value(),
            "AUTH_OAUTH_STATE_SECRET": self.auth_oauth_state_secret.get_secret_value(),
        }
        unsafe_secrets = [
            name
            for name, configured_value in configured_secrets.items()
            if configured_value.strip() in _INSECURE_SECRET_PLACEHOLDERS
            or configured_value.strip() == _DEFAULT_AUTH_SECRETS[name]
        ]

        errors: list[str] = []
        if unsafe_secrets:
            errors.append(f"replace insecure secrets: {', '.join(unsafe_secrets)}")
        if "*" in self.cors_origins:
            errors.append("CORS_ORIGINS must not contain '*' in production")
        if "*" in self.trusted_hosts:
            errors.append("TRUSTED_HOSTS must not contain '*' in production")
        if self.oauth_is_configured and not self.auth_cookie_secure:
            errors.append("AUTH_COOKIE_SECURE must be true when OAuth is configured")
        if errors:
            raise ValueError("Production settings are unsafe: " + "; ".join(errors))
        return self

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

    @property
    def postgres_async_sqlalchemy_url(self) -> str:
        url = self.postgres_sqlalchemy_url
        if url.startswith("postgresql+psycopg_async://"):
            return url
        if url.startswith("postgresql+psycopg://"):
            return url.replace("postgresql+psycopg://", "postgresql+psycopg_async://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg_async://", 1)
        return url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
