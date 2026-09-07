"""FastAPI dependencies: DB session + the authenticated user."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.errors import Unauthenticated
from app.db.session import get_db
from app.models import User

DbSession = Annotated[AsyncSession, Depends(get_db)]


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise Unauthenticated("Authorization header must be 'Bearer <token>'")
    return authorization.split(" ", 1)[1].strip()


async def current_user(
    db: DbSession, token: Annotated[str, Depends(bearer_token)]
) -> User:
    payload = security.decode_token(token, expected_type=security.ACCESS_TOKEN)
    user = await db.get(User, payload["sub"])
    if user is None:
        raise Unauthenticated("Token subject no longer exists")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def user_from_query_token(db: AsyncSession, token: str | None) -> User:
    """WebSocket handshake auth - the token arrives as ``?token=`` because the
    browser WebSocket API cannot set headers."""
    if not token:
        raise Unauthenticated("Missing token")
    payload = security.decode_token(token, expected_type=security.ACCESS_TOKEN)
    user = await db.get(User, payload["sub"])
    if user is None:
        raise Unauthenticated("Token subject no longer exists")
    return user
