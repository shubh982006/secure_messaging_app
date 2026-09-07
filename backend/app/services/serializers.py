"""ORM -> API payload conversion.

Every function here is pure and takes pre-loaded collections, so callers can
batch their queries and never hit an N+1 in a list endpoint.
"""

from __future__ import annotations

from typing import Any

from app.models import (
    Conversation,
    ConversationMember,
    ConversationType,
    Message,
    MessageType,
    User,
)
from app.schemas.conversation import (
    ConversationDetail,
    ConversationOut,
    LastMessagePreview,
    MemberOut,
)
from app.schemas.message import (
    AttachmentOut,
    MessageOut,
    ReactionOut,
    ReplyPreview,
)
from app.schemas.user import UserPrivate, UserPublic
from app.ws.manager import connection_manager

PREVIEW_LIMIT = 140

STATUS_SENT = "sent"
STATUS_DELIVERED = "delivered"
STATUS_READ = "read"


def preview_text(message: Message) -> str:
    if message.deleted_at is not None:
        return "This message was deleted"
    if message.type == MessageType.IMAGE:
        return "Photo"
    if message.type == MessageType.FILE:
        return "Attachment"
    return (message.content or "")[:PREVIEW_LIMIT]


def receipt_counts(
    message: Message, members: list[ConversationMember]
) -> tuple[int, int, int]:
    """``(recipients, delivered_to, read_by)`` from the high-water marks.

    A message with seq S counts as delivered to / read by member M when
    M.last_delivered_seq >= S / M.last_read_seq >= S. No per-message receipt
    rows exist at all - that is the O(1) receipt design.
    """
    recipients = [m for m in members if m.user_id != message.sender_id]
    delivered = sum(1 for m in recipients if m.last_delivered_seq >= message.seq)
    read = sum(1 for m in recipients if m.last_read_seq >= message.seq)
    return len(recipients), delivered, read


def message_status(recipients: int, delivered: int, read: int) -> str:
    if recipients == 0:
        return STATUS_SENT
    if read >= recipients:
        return STATUS_READ
    if delivered >= recipients:
        return STATUS_DELIVERED
    return STATUS_SENT


def serialize_user(user: User, *, private: bool = False) -> UserPublic:
    data = {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "about": user.about,
        "last_seen_at": user.last_seen_at,
        "is_online": connection_manager.is_online(user.id),
    }
    if private:
        return UserPrivate(
            **data, phone_number=user.phone_number, created_at=user.created_at
        )
    return UserPublic(**data)


def serialize_message(
    message: Message,
    members: list[ConversationMember],
    *,
    reply_target: Message | None = None,
    users_by_id: dict[str, User] | None = None,
) -> MessageOut:
    recipients, delivered, read = receipt_counts(message, members)
    users_by_id = users_by_id or {}

    reply_preview = None
    if reply_target is not None:
        sender = users_by_id.get(reply_target.sender_id or "")
        reply_preview = ReplyPreview(
            id=reply_target.id,
            sender_id=reply_target.sender_id,
            sender_name=sender.display_name if sender else None,
            preview=preview_text(reply_target),
            type=reply_target.type,
        )

    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        seq=message.seq,
        type=message.type,
        content=None if message.deleted_at else message.content,
        client_msg_id=message.client_msg_id,
        reply_to=reply_preview,
        reactions=[
            ReactionOut(emoji=r.emoji, user_id=r.user_id) for r in message.reactions
        ]
        if message.deleted_at is None
        else [],
        attachments=[
            AttachmentOut.model_validate(a) for a in message.attachments
        ]
        if message.deleted_at is None
        else [],
        created_at=message.created_at,
        edited_at=message.edited_at,
        deleted_at=message.deleted_at,
        expires_at=message.expires_at,
        recipients=recipients,
        delivered_to=delivered,
        read_by=read,
        status=message_status(recipients, delivered, read),
    )


def message_payload(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """JSON-ready message dict for WebSocket fan-out."""
    return serialize_message(*args, **kwargs).model_dump(mode="json")


def serialize_member(
    member: ConversationMember, user: User | None
) -> MemberOut:
    return MemberOut(
        user_id=member.user_id,
        display_name=user.display_name if user else None,
        username=user.username if user else None,
        avatar_url=user.avatar_url if user else None,
        about=user.about if user else None,
        role=member.role,
        last_read_seq=member.last_read_seq,
        last_delivered_seq=member.last_delivered_seq,
        is_online=connection_manager.is_online(member.user_id),
        last_seen_at=user.last_seen_at if user else None,
        joined_at=member.joined_at,
    )


def _direct_peer(
    conversation: Conversation,
    members: list[ConversationMember],
    viewer_id: str,
    users_by_id: dict[str, User],
) -> User | None:
    if conversation.type != ConversationType.DIRECT:
        return None
    for member in members:
        if member.user_id != viewer_id:
            return users_by_id.get(member.user_id)
    # Note-to-self style conversation (only one member).
    return users_by_id.get(viewer_id)


def serialize_conversation(
    conversation: Conversation,
    members: list[ConversationMember],
    users_by_id: dict[str, User],
    viewer_id: str,
    *,
    last_message: Message | None = None,
    detail: bool = False,
) -> ConversationOut:
    my_member = next((m for m in members if m.user_id == viewer_id), None)
    peer = _direct_peer(conversation, members, viewer_id, users_by_id)

    is_group = conversation.type == ConversationType.GROUP
    name = conversation.name if is_group else (peer.display_name if peer else None)
    avatar = conversation.avatar_url if is_group else (peer.avatar_url if peer else None)

    preview = None
    if last_message is not None:
        recipients, delivered, read = receipt_counts(last_message, members)
        sender = users_by_id.get(last_message.sender_id or "")
        preview = LastMessagePreview(
            id=last_message.id,
            sender_id=last_message.sender_id,
            sender_name=sender.display_name if sender else None,
            type=last_message.type,
            preview=preview_text(last_message),
            seq=last_message.seq,
            created_at=last_message.created_at,
            status=message_status(recipients, delivered, read),
            deleted=last_message.deleted_at is not None,
        )

    my_read_seq = my_member.last_read_seq if my_member else 0
    payload = {
        "id": conversation.id,
        "type": conversation.type,
        "name": name,
        "avatar_url": avatar,
        "members_count": len(members),
        "last_message": preview,
        # Unread is a subtraction of two integers, not a COUNT(*) over messages.
        "unread_count": max(0, conversation.last_seq - my_read_seq),
        "is_online": connection_manager.is_online(peer.id) if peer and not is_group else False,
        "last_seen_at": peer.last_seen_at if peer and not is_group else None,
        "muted": my_member.muted if my_member else False,
        "my_role": my_member.role if my_member else "member",
        "peer": serialize_user(peer) if peer and not is_group else None,
        "last_seq": conversation.last_seq,
        "my_last_read_seq": my_read_seq,
        "disappear_seconds": conversation.disappear_seconds or 0,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }

    if detail:
        return ConversationDetail(
            **payload,
            members=[
                serialize_member(m, users_by_id.get(m.user_id)) for m in members
            ],
        )
    return ConversationOut(**payload)


def conversation_payload(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return serialize_conversation(*args, **kwargs).model_dump(mode="json")
