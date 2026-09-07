from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.config import settings
from app.models.message import MessageType
from app.schemas.common import ORMModel


class ReactionOut(ORMModel):
    emoji: str
    user_id: str


class AttachmentOut(ORMModel):
    id: str
    url: str
    name: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    width: int | None = None
    height: int | None = None


class AttachmentIn(BaseModel):
    """What the client attaches to a message after uploading the file."""

    url: str = Field(max_length=1024)
    name: str | None = Field(default=None, max_length=200)
    mime_type: str | None = Field(default=None, max_length=120)
    size_bytes: int | None = None
    width: int | None = None
    height: int | None = None


class UploadedAttachment(AttachmentIn):
    kind: str = "file"  # image | file


class ReplyPreview(BaseModel):
    id: str
    sender_id: str | None = None
    sender_name: str | None = None
    preview: str
    type: str = MessageType.TEXT


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    sender_id: str | None = None
    seq: int
    type: str
    content: str | None = None
    client_msg_id: str | None = None
    reply_to: ReplyPreview | None = None
    reactions: list[ReactionOut] = []
    attachments: list[AttachmentOut] = []
    created_at: datetime
    edited_at: datetime | None = None
    deleted_at: datetime | None = None
    # Disappearing messages: when this message stops being delivered at all.
    expires_at: datetime | None = None
    # Group receipt counters (how many recipients, excluding the sender).
    delivered_to: int = 0
    read_by: int = 0
    recipients: int = 0
    status: str = "sent"  # sent | delivered | read


class MessageCreate(BaseModel):
    type: str = MessageType.TEXT
    content: str | None = Field(default=None, max_length=settings.max_message_length)
    client_msg_id: str | None = Field(default=None, max_length=64)
    reply_to_id: str | None = None
    attachments: list[AttachmentIn] | None = None


class MessagePage(BaseModel):
    messages: list[MessageOut]
    next_cursor: str | None = None


class ReactionIn(BaseModel):
    emoji: str = Field(min_length=1, max_length=16)


class ReadMarkerIn(BaseModel):
    last_read_message_id: str | None = None
    last_read_seq: int | None = None


class ReadMarkerOut(BaseModel):
    unread_count: int
    last_read_seq: int


class MessageSearchHit(BaseModel):
    """One search result, with just enough context to render a result row."""

    message: MessageOut
    conversation_id: str
    conversation_name: str | None = None
    conversation_type: str
    snippet: str


class MessageSearchResponse(BaseModel):
    results: list[MessageSearchHit]
    query: str
