from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, model_validator

from app.schemas.user import UserPublic


class ContactOut(BaseModel):
    id: str
    user: UserPublic
    nickname: str | None = None
    created_at: datetime


class ContactListOut(BaseModel):
    contacts: list[ContactOut]


class ContactCreate(BaseModel):
    phone_number: str | None = None
    username: str | None = None
    user_id: str | None = None
    nickname: str | None = None

    @model_validator(mode="after")
    def _one_identifier(self) -> "ContactCreate":
        if not any([self.phone_number, self.username, self.user_id]):
            raise ValueError("one of phone_number, username or user_id is required")
        return self
