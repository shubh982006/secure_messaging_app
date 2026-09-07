from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.conversation import ConversationType
from app.schemas.user import UserPublic


class MemberOut(BaseModel):
    user_id: str
    display_name: str | None = None
    username: str | None = None
    avatar_url: str | None = None
    about: str | None = None
    role: str
    last_read_seq: int
    last_delivered_seq: int
    is_online: bool = False
    last_seen_at: datetime | None = None
    joined_at: datetime | None = None


class LastMessagePreview(BaseModel):
    id: str
    sender_id: str | None = None
    sender_name: str | None = None
    type: str
    preview: str
    seq: int
    created_at: datetime
    status: str = "sent"
    deleted: bool = False


class ConversationOut(BaseModel):
    id: str
    type: str
    name: str | None = None
    avatar_url: str | None = None
    members_count: int = 0
    last_message: LastMessagePreview | None = None
    unread_count: int = 0
    is_online: bool = False
    last_seen_at: datetime | None = None
    muted: bool = False
    my_role: str = "member"
    peer: UserPublic | None = None
    last_seq: int = 0
    my_last_read_seq: int = 0
    # 0 = disappearing messages are off for this conversation.
    disappear_seconds: int = 0
    created_at: datetime | None = None
    updated_at: datetime


class ConversationDetail(ConversationOut):
    members: list[MemberOut] = []


class ConversationPage(BaseModel):
    conversations: list[ConversationOut]
    next_cursor: str | None = None


class ConversationCreate(BaseModel):
    type: str = ConversationType.DIRECT
    user_id: str | None = None  # direct
    name: str | None = Field(default=None, max_length=120)  # group
    member_ids: list[str] | None = None  # group
    avatar_url: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "ConversationCreate":
        if self.type == ConversationType.DIRECT and not self.user_id:
            raise ValueError("user_id is required for a direct conversation")
        if self.type == ConversationType.GROUP:
            if not self.name or not self.name.strip():
                raise ValueError("name is required for a group conversation")
            if not self.member_ids:
                raise ValueError("member_ids is required for a group conversation")
        return self


class ConversationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    avatar_url: str | None = None
    muted: bool | None = None
    # Retention window for new messages, in seconds. 0 turns the feature off.
    disappear_seconds: int | None = Field(default=None, ge=0, le=60 * 60 * 24 * 28)


class AddMembersIn(BaseModel):
    user_ids: list[str] = Field(min_length=1)
