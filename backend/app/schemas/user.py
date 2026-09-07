from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class UserPublic(ORMModel):
    """The shape every other user sees."""

    id: str
    username: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    about: str | None = None
    last_seen_at: datetime | None = None
    is_online: bool = False


class UserPrivate(UserPublic):
    """The authenticated user's own profile (adds the phone number)."""

    phone_number: str
    created_at: datetime | None = None


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    username: str | None = Field(default=None, min_length=3, max_length=64)
    avatar_url: str | None = Field(default=None, max_length=1024)
    about: str | None = Field(default=None, max_length=200)


class UserSearchResponse(BaseModel):
    results: list[UserPublic]
