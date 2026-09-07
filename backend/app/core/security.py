"""JWT issuing / verification.

Stateless access tokens (any node can validate any request -> horizontal scale)
plus refresh tokens that carry a ``jti`` so they can be rotated and revoked.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import settings
from app.core.errors import Unauthenticated

ACCESS_TOKEN = "access"
REFRESH_TOKEN = "refresh"


def _now() -> datetime:
    return datetime.now(UTC)


def _encode(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str) -> str:
    now = _now()
    return _encode(
        {
            "sub": user_id,
            "type": ACCESS_TOKEN,
            # Unique per issue: two tokens minted in the same second are still
            # distinguishable, which keeps rotation observable in logs.
            "jti": str(uuid.uuid4()),
            "iat": int(now.timestamp()),
            "exp": int(
                (now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()
            ),
        }
    )


def create_refresh_token(user_id: str) -> tuple[str, str, datetime]:
    """Return ``(token, jti, expires_at)`` - the jti is stored so it can be revoked."""
    now = _now()
    jti = str(uuid.uuid4())
    expires_at = now + timedelta(days=settings.refresh_token_expire_days)
    token = _encode(
        {
            "sub": user_id,
            "type": REFRESH_TOKEN,
            "jti": jti,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
    )
    return token, jti, expires_at


def decode_token(token: str, *, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.ExpiredSignatureError as exc:  # pragma: no cover - trivial branch
        raise Unauthenticated("Token has expired") from exc
    except jwt.PyJWTError as exc:
        raise Unauthenticated("Token is invalid") from exc

    if payload.get("type") != expected_type:
        raise Unauthenticated(f"Expected a {expected_type} token")
    if not payload.get("sub"):
        raise Unauthenticated("Token is missing a subject")
    return payload
