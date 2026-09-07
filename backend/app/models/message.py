from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, new_uuid, utcnow


class MessageType(StrEnum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    SYSTEM = "system"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE")
    )
    sender_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Per-conversation monotonic order. Assigned from conversations.last_seq.
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)

    type: Mapped[str] = mapped_column(String(16), default=MessageType.TEXT)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Client generated UUID. Makes retries idempotent, which is what makes the
    # optimistic bubble in the UI safe.
    client_msg_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    reply_to_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    edited_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # Soft delete -> Signal style "This message was deleted" tombstone.
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    # Disappearing messages. Stamped at insert from the conversation's retention
    # window; NULL means the message never expires. Rows are filtered out as
    # soon as they pass this instant and hard-deleted by a background sweeper.
    expires_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True, index=True
    )

    # Deliberately NOT eager loaded: a self-referential selectin would chase
    # reply chains recursively. The service batch-loads reply targets for a
    # whole page in one query instead.
    reply_to: Mapped["Message | None"] = relationship(
        remote_side="Message.id", lazy="noload"
    )
    reactions: Mapped[list["MessageReaction"]] = relationship(
        back_populates="message", cascade="all, delete-orphan", lazy="selectin"
    )
    attachments: Mapped[list["Attachment"]] = relationship(  # noqa: F821
        back_populates="message", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        # The single most important index: ordered pagination AND the
        # seq comparisons that drive read/delivered receipts.
        Index("idx_messages_conv_seq", "conversation_id", "seq"),
        UniqueConstraint(
            "conversation_id",
            "sender_id",
            "client_msg_id",
            name="uq_message_idempotency",
        ),
    )


class MessageReaction(Base):
    __tablename__ = "message_reactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    message_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE")
    )
    emoji: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    message: Mapped[Message] = relationship(back_populates="reactions")

    __table_args__ = (
        UniqueConstraint("message_id", "user_id", "emoji", name="uq_reaction"),
    )
