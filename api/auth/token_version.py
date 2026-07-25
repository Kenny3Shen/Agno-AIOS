"""Immediate invalidation for JWTs bound to a user account.

FastAPI Users JWTs are stateless by design.  T.A.I.S. adds a monotonically
increasing account authorization version so role or credential changes can
invalidate every previously issued token without waiting for its expiry.
"""

from __future__ import annotations

from typing import cast
from uuid import UUID

import jwt
from fastapi import Request
from loguru import logger
from sqlalchemy import ColumnElement, select
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from api.auth.database import async_session_maker
from api.auth.models import User

AUTH_VERSION_CLAIM = "auth_version"
FASTAPI_USERS_AUDIENCE = "fastapi-users:auth"
_INVALID_TOKEN_DETAIL = "Authentication token is no longer valid"


def authorization_version(value: object) -> int:
    """Return a safe persisted authorization version for an account."""
    if isinstance(value, bool):
        return 1
    if isinstance(value, int):
        version = value
    elif isinstance(value, str):
        try:
            version = int(value)
        except ValueError:
            return 1
    else:
        return 1
    return version if version >= 1 else 1


def token_authorization_version(value: object) -> int | None:
    """Accept only canonical integer token versions, never truthy coercions."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def next_authorization_version(value: object) -> int:
    """Advance the account version after a security-relevant change."""
    return authorization_version(value) + 1


def is_fastapi_users_token(payload: dict[str, object]) -> bool:
    """Identify tokens issued by the application's FastAPI Users backend."""
    audience = payload.get("aud")
    if isinstance(audience, str):
        return audience == FASTAPI_USERS_AUDIENCE
    return isinstance(audience, list) and FASTAPI_USERS_AUDIENCE in audience


def _authorization_header_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "").strip()
    if not header:
        return None
    if header.lower().startswith("bearer "):
        header = header[7:].strip()
    return header or None


def _unverified_jwt_payload(token: str, *, algorithm: str) -> dict[str, object] | None:
    try:
        payload = jwt.decode(
            token,
            algorithms=[algorithm],
            options={"verify_signature": False, "verify_aud": False, "verify_exp": False},
        )
    except jwt.PyJWTError:
        return None
    return payload if isinstance(payload, dict) else None


async def active_account_authorization_version(user_id: UUID) -> int | None:
    """Look up an active account's current authorization version."""
    async with async_session_maker() as session:
        version = await session.scalar(
            select(User.auth_version).where(
                cast(ColumnElement[bool], User.id == user_id),
                cast(ColumnElement[bool], User.is_active).is_(True),
            )
        )
    return None if version is None else authorization_version(version)


class UserTokenVersionMiddleware(BaseHTTPMiddleware):
    """Reject stale FastAPI Users JWTs before AgentOS consumes their scopes."""

    def __init__(self, app, *, secret: str, algorithm: str = "HS256") -> None:
        super().__init__(app)
        self._secret = secret
        self._algorithm = algorithm

    async def dispatch(self, request: Request, call_next) -> Response:
        # Auth routes use ScopedJWTStrategy, which applies the identical check.
        # In particular, a stale bearer must not block a new login request.
        if request.url.path.startswith("/api/auth/"):
            return await call_next(request)

        token = _authorization_header_token(request)
        if token is None:
            return await call_next(request)
        unverified_payload = _unverified_jwt_payload(token, algorithm=self._algorithm)
        if unverified_payload is None or not is_fastapi_users_token(unverified_payload):
            return await call_next(request)

        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                audience=FASTAPI_USERS_AUDIENCE,
            )
            subject = UUID(str(payload.get("sub") or ""))
            token_version = token_authorization_version(payload.get(AUTH_VERSION_CLAIM))
        except (jwt.PyJWTError, TypeError, ValueError):
            return JSONResponse(status_code=401, content={"detail": _INVALID_TOKEN_DETAIL})

        if token_version is None:
            return JSONResponse(status_code=401, content={"detail": _INVALID_TOKEN_DETAIL})

        try:
            account_version = await active_account_authorization_version(subject)
        except SQLAlchemyError:
            logger.warning("Unable to validate the authorization version for an authenticated request")
            return JSONResponse(
                status_code=503,
                content={"detail": "Authentication is temporarily unavailable"},
            )
        if account_version != token_version:
            return JSONResponse(status_code=401, content={"detail": _INVALID_TOKEN_DETAIL})

        return await call_next(request)
