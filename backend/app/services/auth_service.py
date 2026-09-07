"""Mocked OTP onboarding + JWT session lifecycle.

The OTP is fake (fixed code) but the *flow* is real: a challenge row is created,
it expires, and it is single use. Replacing the mock with Twilio is a one
function change inside ``request_otp``.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.core.errors import Unauthenticated, ValidationError
from app.db.base import utcnow
from app.models import OtpRequest, RefreshToken, User


async def request_otp(db: AsyncSession, phone_number: str) -> OtpRequest:
    challenge = OtpRequest(
        phone_number=phone_number,
        code=settings.mock_otp_code,
        expires_at=utcnow() + timedelta(seconds=settings.otp_expire_seconds),
    )
    db.add(challenge)
    await db.commit()
    await db.refresh(challenge)
    # <- a real deployment would hand `challenge` to an SMS provider here.
    return challenge


async def _issue_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    access_token = security.create_access_token(user.id)
    refresh_token, jti, expires_at = security.create_refresh_token(user.id)
    db.add(RefreshToken(jti=jti, user_id=user.id, expires_at=expires_at))
    await db.commit()
    return access_token, refresh_token


async def verify_otp(
    db: AsyncSession, *, phone_number: str, code: str
) -> tuple[User, str, str, bool]:
    challenge = await db.scalar(
        select(OtpRequest)
        .where(
            OtpRequest.phone_number == phone_number,
            OtpRequest.consumed.is_(False),
        )
        .order_by(OtpRequest.created_at.desc())
        .limit(1)
    )
    if challenge is None:
        raise ValidationError("Request a code first", code="OTP_NOT_REQUESTED")
    if challenge.expires_at < utcnow():
        raise ValidationError("That code has expired", code="OTP_EXPIRED")
    if code != challenge.code:
        raise ValidationError("That code is not correct", code="OTP_INVALID")

    challenge.consumed = True

    user = await db.scalar(select(User).where(User.phone_number == phone_number))
    is_new_user = user is None
    if user is None:
        user = User(phone_number=phone_number)
        db.add(user)
    user.last_seen_at = utcnow()
    await db.commit()
    await db.refresh(user)

    access_token, refresh_token = await _issue_tokens(db, user)
    return user, access_token, refresh_token, is_new_user


async def refresh_session(db: AsyncSession, refresh_token: str) -> tuple[str, str]:
    """Rotate a refresh token: the presented one is revoked, a new pair issued."""
    payload = security.decode_token(refresh_token, expected_type=security.REFRESH_TOKEN)
    stored = await db.scalar(
        select(RefreshToken).where(RefreshToken.jti == payload["jti"])
    )
    if stored is None or stored.revoked:
        raise Unauthenticated("Refresh token has been revoked")
    if stored.expires_at < utcnow():
        raise Unauthenticated("Refresh token has expired")

    user = await db.get(User, payload["sub"])
    if user is None:
        raise Unauthenticated("Unknown user")

    stored.revoked = True
    return await _issue_tokens(db, user)


async def logout(db: AsyncSession, *, user_id: str, refresh_token: str | None) -> None:
    if refresh_token:
        try:
            payload = security.decode_token(
                refresh_token, expected_type=security.REFRESH_TOKEN
            )
        except Unauthenticated:
            return
        stored = await db.scalar(
            select(RefreshToken).where(RefreshToken.jti == payload["jti"])
        )
        if stored is not None and stored.user_id == user_id:
            stored.revoked = True
            await db.commit()
        return

    # No token supplied - end every session for this user.
    tokens = await db.scalars(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False)
        )
    )
    for token in tokens:
        token.revoked = True
    await db.commit()
