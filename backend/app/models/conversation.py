from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, new_uuid, utcnow


class ConversationType(StrEnum):
    DIRECT = "direct"
    GROUP = "group"


class MemberRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    type: Mapped[str] = mapped_column(String(16), default=ConversationType.DIRECT)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # min(uidA, uidB) + ":" + max(uidA, uidB) for direct chats, NULL for groups.
    # The unique index makes "start a chat with X" an idempotent get-or-create.
    dm_key: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True)

    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Monotonic per-conversation counter. Incremented in the same transaction as
    # the message insert -> gap-free ordering with no reliance on wall clocks.
    last_seq: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # Disappearing messages: seconds a new message survives after being sent.
    # 0 / NULL means the feature is off for this conversation.
    disappear_seconds: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow
    )

    members: Mapped[list["ConversationMember"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        # Conversation list is sorted by most recent activity.
        Index("idx_conversations_updated", "updated_at"),
    )


class ConversationMember(Base):
    __tablename__ = "conversation_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(16), default=MemberRole.MEMBER)

    # High-water marks. A message with seq S is read by this member iff
    # last_read_seq >= S. Marking a thread read is ONE update, not N inserts.
    last_read_seq: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    last_delivered_seq: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    muted: Mapped[bool] = mapped_column(Boolean, default=False)
    joined_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="members")

    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_member"),
        # "load every conversation for this user" - the conversation list query.
        Index("idx_members_user", "user_id"),
    )
