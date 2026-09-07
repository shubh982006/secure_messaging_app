from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.auth import (
    LogoutIn,
    RefreshIn,
    RequestOtpIn,
    RequestOtpOut,
    TokenPair,
    VerifyOtpIn,
    VerifyOtpOut,
)
from app.schemas.user import UserPrivate
from app.services import auth_service, serializers

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/request-otp", response_model=RequestOtpOut)
async def request_otp(payload: RequestOtpIn, db: DbSession) -> RequestOtpOut:
    challenge = await auth_service.request_otp(db, payload.phone_number)
    return RequestOtpOut(
        request_id=challenge.id,
        # Returned on purpose: the brief mocks verification, so the UI can
        # prefill the code instead of asking for an SMS that never arrives.
        mocked_code=challenge.code,
        expires_in=int((challenge.expires_at - challenge.created_at).total_seconds()),
    )


@router.post("/verify-otp", response_model=VerifyOtpOut)
async def verify_otp(payload: VerifyOtpIn, db: DbSession) -> VerifyOtpOut:
    user, access_token, refresh_token, is_new_user = await auth_service.verify_otp(
        db, phone_number=payload.phone_number, code=payload.code
    )
    return VerifyOtpOut(
        access_token=access_token,
        refresh_token=refresh_token,
        is_new_user=is_new_user,
        user=serializers.serialize_user(user, private=True),
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshIn, db: DbSession) -> TokenPair:
    access_token, refresh_token = await auth_service.refresh_session(
        db, payload.refresh_token
    )
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: LogoutIn, db: DbSession, user: CurrentUser) -> Response:
    await auth_service.logout(db, user_id=user.id, refresh_token=payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserPrivate)
async def me(user: CurrentUser) -> UserPrivate:
    return serializers.serialize_user(user, private=True)
