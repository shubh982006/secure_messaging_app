"""MessageService - persistence, ordering, receipts and fan-out.

The whole hot path lives here. Transport (REST router or WebSocket gateway) is
deliberately thin: both call the exact same functions, so a message sent over
REST behaves identically to one sent over the socket.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import Forbidden, MessageNotFound, Unprocessable, ValidationError
from app.db.base import utcnow
from app.models import (
    Attachment,
    Conversation,
    ConversationMember,
    Message,
    MessageReaction,
    MessageType,
)
from app.services import access, serializers
from app.ws import events
from app.ws.manager import connection_manager

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# sequencing
# --------------------------------------------------------------------------- #
async def allocate_seq(db: AsyncSession, conversation_id: str) -> int:
    """Atomically bump and return ``conversations.last_seq``.

    A single statement, so two concurrent senders can never be handed the same
    sequence number - on SQLite the write lock serialises them, on Postgres the
    row lock does. No application-level locking, no clock dependency.
    """
    result = await db.execute(
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(last_seq=Conversation.last_seq + 1, updated_at=utcnow())
        .returning(Conversation.last_seq)
    )
    seq = result.scalar_one_or_none()
    if seq is None:
        raise Unprocessable("Conversation could not be sequenced")
    return int(seq)


# --------------------------------------------------------------------------- #
# reading
# --------------------------------------------------------------------------- #
async def _load_reply_targets(
    db: AsyncSession, messages: list[Message]
) -> dict[str, Message]:
    """One batched query for every quoted message on the page (never N+1)."""
    ids = {m.reply_to_id for m in messages if m.reply_to_id}
    if not ids:
        return {}
    result = await db.scalars(select(Message).where(Message.id.in_(ids)))
    return {m.id: m for m in result}


async def get_history(
    db: AsyncSession,
    *,
    conversation_id: str,
    user_id: str,
    before: int | None = None,
    after: int | None = None,
    limit: int = 50,
) -> tuple[list[Message], dict[str, Message], list[ConversationMember], str | None]:
    """Cursor paginated thread history.

    ``before`` walks backwards for infinite scroll; ``after`` walks forwards and
    is what a reconnecting client uses to backfill everything it missed while
    the socket was down (the DB is the source of truth, the socket is the fast
    path).
    """
    await access.require_member(db, conversation_id, user_id)
    limit = max(1, min(limit, 100))

    stmt = select(Message).where(
        Message.conversation_id == conversation_id, _not_expired()
    )
    if after is not None:
        stmt = stmt.where(Message.seq > after).order_by(Message.seq.asc())
    else:
        if before is not None:
            stmt = stmt.where(Message.seq < before)
        stmt = stmt.order_by(Message.seq.desc())

    rows = list(await db.scalars(stmt.limit(limit + 1)))
    has_more = len(rows) > limit
    rows = rows[:limit]

    next_cursor = None
    if has_more and rows:
        # Descending page -> lowest seq seen; ascending page -> highest seq seen.
        next_cursor = f"seq:{rows[-1].seq}"

    # Always hand the client ascending order - it renders top to bottom.
    rows.sort(key=lambda m: m.seq)

    reply_map = await _load_reply_targets(db, rows)
    members = await access.members_of(db, conversation_id)
    return rows, reply_map, members, next_cursor


# --------------------------------------------------------------------------- #
# sending
# --------------------------------------------------------------------------- #
async def send_message(
    db: AsyncSession,
    *,
    conversation_id: str,
    sender_id: str,
    content: str | None,
    message_type: str = MessageType.TEXT,
    client_msg_id: str | None = None,
    reply_to_id: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> tuple[Message, bool]:
    """Persist a message and fan it out. Returns ``(message, was_duplicate)``."""
    member = await access.require_member(db, conversation_id, sender_id)

    if message_type == MessageType.TEXT:
        content = (content or "").strip()
        if not content:
            raise ValidationError("Message content cannot be empty")
        if len(content) > settings.max_message_length:
            raise ValidationError(
                f"Message exceeds {settings.max_message_length} characters"
            )

    # Idempotency fast path: a retried send returns the original message rather
    # than creating a duplicate. This is what makes the optimistic bubble safe.
    if client_msg_id:
        existing = await db.scalar(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.sender_id == sender_id,
                Message.client_msg_id == client_msg_id,
            )
        )
        if existing is not None:
            return existing, True

    if reply_to_id:
        target = await db.get(Message, reply_to_id)
        if target is None or target.conversation_id != conversation_id:
            raise ValidationError("reply_to_id does not belong to this conversation")

    conversation = await access.get_conversation(db, conversation_id)
    seq = await allocate_seq(db, conversation_id)
    message = Message(
        conversation_id=conversation_id,
        sender_id=sender_id,
        seq=seq,
        type=message_type,
        content=content,
        client_msg_id=client_msg_id,
        reply_to_id=reply_to_id,
        # Disappearing messages: the clock starts when the server accepts it.
        expires_at=(
            utcnow() + timedelta(seconds=conversation.disappear_seconds)
            if conversation.disappear_seconds
            else None
        ),
    )
    db.add(message)
    if attachments:
        # message.id is assigned on flush; attachments reference it.
        await db.flush()

    for attachment in attachments or []:
        db.add(
            Attachment(
                message_id=message.id,
                url=attachment["url"],
                name=attachment.get("name"),
                mime_type=attachment.get("mime_type"),
                size_bytes=attachment.get("size_bytes"),
                width=attachment.get("width"),
                height=attachment.get("height"),
            )
        )

    # The sender has, by definition, seen their own message.
    member.last_read_seq = max(member.last_read_seq, seq)
    member.last_delivered_seq = max(member.last_delivered_seq, seq)

    try:
        await db.commit()
    except IntegrityError:
        # Lost an idempotency race with a concurrent retry of the same send.
        await db.rollback()
        existing = await db.scalar(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.sender_id == sender_id,
                Message.client_msg_id == client_msg_id,
            )
        )
        if existing is None:  # pragma: no cover - genuinely unexpected
            raise
        return existing, True

    await db.refresh(message)
    await fan_out_new_message(db, message)
    return message, False


async def fan_out_new_message(db: AsyncSession, message: Message) -> None:
    members = await access.members_of(db, message.conversation_id)
    reply_map = await _load_reply_targets(db, [message])
    user_ids = [m.user_id for m in members]
    user_ids += [m.sender_id for m in reply_map.values() if m.sender_id]
    users = await access.users_by_ids(db, user_ids)
    payload = serializers.message_payload(
        message,
        members,
        reply_target=reply_map.get(message.reply_to_id or ""),
        users_by_id=users,
    )
    # Delivered to every member including the sender's other devices; clients
    # dedupe on message id / client_msg_id, which the optimistic UI needs anyway.
    await connection_manager.send_to_users(
        [m.user_id for m in members],
        events.envelope(events.SERVER_MESSAGE_NEW, {"message": payload}),
    )


async def create_system_message(
    db: AsyncSession,
    *,
    conversation_id: str,
    actor_id: str | None,
    text: str,
    commit: bool = True,
) -> Message:
    """A ``type=system`` message ("Alice added Bob"), rendered centred like Signal."""
    seq = await allocate_seq(db, conversation_id)
    message = Message(
        conversation_id=conversation_id,
        sender_id=actor_id,
        seq=seq,
        type=MessageType.SYSTEM,
        content=text,
    )
    db.add(message)

    if actor_id:
        member = await access.get_member(db, conversation_id, actor_id)
        if member is not None:
            member.last_read_seq = max(member.last_read_seq, seq)
            member.last_delivered_seq = max(member.last_delivered_seq, seq)

    if commit:
        await db.commit()
        await db.refresh(message)
    return message


# --------------------------------------------------------------------------- #
# receipts
# --------------------------------------------------------------------------- #
async def mark_delivered(
    db: AsyncSession,
    *,
    conversation_id: str,
    user_id: str,
    message_id: str | None = None,
    seq: int | None = None,
) -> int | None:
    """Advance the delivered high-water mark and tell the senders about it."""
    member = await access.require_member(db, conversation_id, user_id)

    if seq is None and message_id:
        target = await db.get(Message, message_id)
        if target is None or target.conversation_id != conversation_id:
            raise MessageNotFound()
        seq = target.seq
    if seq is None:
        conversation = await access.get_conversation(db, conversation_id)
        seq = conversation.last_seq

    if seq <= member.last_delivered_seq:
        return None  # Already at or past this point - nothing to broadcast.

    member.last_delivered_seq = seq
    await db.commit()

    members = await access.members_of(db, conversation_id)
    delivered_to = sum(
        1 for m in members if m.user_id != user_id and m.last_delivered_seq >= seq
    )
    await connection_manager.send_to_users(
        [m.user_id for m in members if m.user_id != user_id],
        events.envelope(
            events.SERVER_MESSAGE_DELIVERED,
            {
                "conversation_id": conversation_id,
                "message_id": message_id,
                "user_id": user_id,
                "last_delivered_seq": seq,
                "delivered_to": delivered_to,
            },
        ),
    )
    return seq


async def mark_read(
    db: AsyncSession,
    *,
    conversation_id: str,
    user_id: str,
    message_id: str | None = None,
    seq: int | None = None,
) -> tuple[int, int]:
    """Advance the read high-water mark. Returns ``(last_read_seq, unread)``.

    Marking an entire thread read is ONE UPDATE regardless of how many messages
    or members are involved - see SYSTEM_DESIGN.md section 8.
    """
    member = await access.require_member(db, conversation_id, user_id)
    conversation = await access.get_conversation(db, conversation_id)

    if seq is None and message_id:
        target = await db.get(Message, message_id)
        if target is None or target.conversation_id != conversation_id:
            raise MessageNotFound()
        seq = target.seq
    if seq is None:
        seq = conversation.last_seq

    seq = min(seq, conversation.last_seq)
    if seq <= member.last_read_seq:
        return member.last_read_seq, max(
            0, conversation.last_seq - member.last_read_seq
        )

    member.last_read_seq = seq
    # Reading implies delivery.
    member.last_delivered_seq = max(member.last_delivered_seq, seq)
    await db.commit()

    members = await access.members_of(db, conversation_id)
    read_by = sum(1 for m in members if m.user_id != user_id and m.last_read_seq >= seq)
    await connection_manager.send_to_users(
        [m.user_id for m in members if m.user_id != user_id],
        events.envelope(
            events.SERVER_MESSAGE_READ,
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "last_read_seq": seq,
                "read_by": read_by,
            },
        ),
    )
    return seq, max(0, conversation.last_seq - seq)


# --------------------------------------------------------------------------- #
# mutations
# --------------------------------------------------------------------------- #
async def delete_message(db: AsyncSession, *, message_id: str, user_id: str) -> Message:
    message = await db.get(Message, message_id)
    if message is None:
        raise MessageNotFound()
    await access.require_member(db, message.conversation_id, user_id)
    if message.sender_id != user_id:
        raise Forbidden("You can only delete your own messages")

    if message.deleted_at is None:
        message.deleted_at = utcnow()
        message.content = None
        await db.commit()

    member_ids = await access.member_ids_of(db, message.conversation_id)
    await connection_manager.send_to_users(
        member_ids,
        events.envelope(
            events.SERVER_MESSAGE_DELETED,
            {"conversation_id": message.conversation_id, "message_id": message.id},
        ),
    )
    return message


async def toggle_reaction(
    db: AsyncSession, *, message_id: str, user_id: str, emoji: str, add: bool
) -> Message:
    message = await db.get(Message, message_id)
    if message is None or message.deleted_at is not None:
        raise MessageNotFound()
    await access.require_member(db, message.conversation_id, user_id)

    existing = await db.scalar(
        select(MessageReaction).where(
            MessageReaction.message_id == message_id,
            MessageReaction.user_id == user_id,
            MessageReaction.emoji == emoji,
        )
    )
    if add and existing is None:
        db.add(MessageReaction(message_id=message_id, user_id=user_id, emoji=emoji))
    elif not add and existing is not None:
        await db.delete(existing)
    await db.commit()
    await db.refresh(message)

    member_ids = await access.member_ids_of(db, message.conversation_id)
    await connection_manager.send_to_users(
        member_ids,
        events.envelope(
            events.SERVER_MESSAGE_REACTION,
            {
                "conversation_id": message.conversation_id,
                "message_id": message.id,
                "reactions": [
                    {"emoji": r.emoji, "user_id": r.user_id} for r in message.reactions
                ],
            },
        ),
    )
    return message


async def relay_typing(
    db: AsyncSession, *, conversation_id: str, user_id: str, is_typing: bool
) -> None:
    """Typing is ephemeral - relayed, never persisted. Zero DB writes."""
    await access.require_member(db, conversation_id, user_id)
    member_ids = await access.member_ids_of(db, conversation_id)
    await connection_manager.send_to_users(
        [uid for uid in member_ids if uid != user_id],
        events.envelope(
            events.SERVER_TYPING,
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "is_typing": is_typing,
            },
        ),
    )


# --------------------------------------------------------------------------- #
# disappearing messages
# --------------------------------------------------------------------------- #
def _not_expired():
    """Rows past their expiry are invisible immediately, before the sweeper runs."""
    return or_(Message.expires_at.is_(None), Message.expires_at > utcnow())


async def purge_expired_messages(db: AsyncSession) -> int:
    """Hard-delete expired messages and tell every member to drop them.

    Expiry is enforced at query time as well, so a late sweep can never leak a
    message - the sweeper is about reclaiming rows, not about correctness.
    """
    expired = list(
        await db.scalars(
            select(Message).where(
                Message.expires_at.is_not(None), Message.expires_at <= utcnow()
            )
        )
    )
    if not expired:
        return 0

    by_conversation: dict[str, list[str]] = {}
    for message in expired:
        by_conversation.setdefault(message.conversation_id, []).append(message.id)

    await db.execute(
        delete(Message).where(Message.id.in_([m.id for m in expired]))
    )
    await db.commit()

    for conversation_id, message_ids in by_conversation.items():
        member_ids = await access.member_ids_of(db, conversation_id)
        if not member_ids:
            continue
        await connection_manager.send_to_users(
            member_ids,
            events.envelope(
                events.SERVER_MESSAGE_EXPIRED,
                {"conversation_id": conversation_id, "message_ids": message_ids},
            ),
        )
    return len(expired)


async def run_expiry_sweeper(interval_seconds: int) -> None:
    """Background loop started with the app; cancelled on shutdown."""
    from app.db.session import SessionFactory

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            async with SessionFactory() as db:
                removed = await purge_expired_messages(db)
            if removed:
                logger.info("swept %d expired message(s)", removed)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - the loop must never die
            logger.exception("expiry sweeper iteration failed")
