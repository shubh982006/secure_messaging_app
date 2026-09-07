from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.schemas.user import UserPrivate

PHONE_PATTERN = r"^\+?[0-9]{7,15}$"


class RequestOtpIn(BaseModel):
    phone_number: str = Field(min_length=7, max_length=20)

    @field_validator("phone_number")
    @classmethod
    def _normalise(cls, value: str) -> str:
        cleaned = "".join(ch for ch in value if ch.isdigit() or ch == "+")
        if not cleaned.startswith("+"):
            cleaned = "+" + cleaned
        if len(cleaned) < 8:
            raise ValueError("phone_number must include a country code")
        return cleaned


class RequestOtpOut(BaseModel):
    request_id: str
    mocked_code: str
    expires_in: int


class VerifyOtpIn(RequestOtpIn):
    code: str = Field(min_length=4, max_length=8)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class VerifyOtpOut(TokenPair):
    is_new_user: bool
    user: UserPrivate


class RefreshIn(BaseModel):
    refresh_token: str


class LogoutIn(BaseModel):
    refresh_token: str | None = None
