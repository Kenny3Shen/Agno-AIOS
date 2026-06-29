# Backend Configuration And Auth

## Configuration

Runtime configuration is centralized in `api/config.py` with `pydantic-settings`.
Values are loaded from environment variables and `.env`, then exposed through the
cached `get_settings()` function. FastAPI stores the active settings object on
`app.state.settings` during lifespan startup so routes can receive it through
`get_app_settings`.

## Logging

`api/core/logging.py` configures loguru once from `LOG_LEVEL`, `LOG_DIR`, and
`LOG_FILE`. The FastAPI lifespan logs application startup and shutdown, while
route and service modules can continue using `from loguru import logger`.

## Auth Endpoints

- `POST /api/auth/register`: email/password registration.
- `POST /api/auth/jwt/login`: JWT login using FastAPI Users OAuth2 password flow.
- `POST /api/auth/jwt/logout`: logout endpoint for the JWT backend.
- `GET /api/auth/users/me`: current user.
- `GET /api/auth/oauth/providers`: configured OAuth providers.
- `GET /api/auth/{provider}/authorize`: start OAuth flow.
- `GET /api/auth/{provider}/callback`: OAuth callback.

## OAuth Providers

GitHub, Google, and Microsoft OAuth routers are mounted only when both client ID
and client secret are configured. Provider callback URLs are generated from the
incoming request by default; set `*_OAUTH_REDIRECT_URL` when running behind a
proxy or when the OAuth app requires an exact redirect URI.

## Database

Auth uses FastAPI Users with `fastapi-users-db-sqlalchemy` and SQLAlchemy async.
The same PostgreSQL connection settings as the main app are used. On startup,
the app creates the FastAPI Users `user` and `oauth_account` tables if missing.

## Dependency Injection Review

- `get_app_settings` provides typed Settings access instead of ad-hoc `.env`
  parsing inside route handlers.
- `get_pool` keeps PostgreSQL pool access centralized.
- `get_asset_client` and `get_asset_lock` keep the external ACL client and token
  refresh lock in lifespan-managed app state.
- `get_user_db` and `get_user_manager` provide FastAPI Users' async persistence
  and user manager through dependencies.
