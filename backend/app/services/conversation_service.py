"""ConversationService - DM get-or-create, groups, membership and the list feed."""

from __future__ import annotations

import base64
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    Conflict,
    Forbidden,
    Unprocessable,
    UserNotFound,
    ValidationError,
)
from app.db.base import utcnow
from app.models import (
    Conversation,
    ConversationMember,
    ConversationType,
    MemberRole,
    Message,
    User,
)
from app.schemas.conversation import ConversationDetail, ConversationOut
from app.services import access, message_service, serializers
from app.ws import events
from app.ws.manager import connection_manager


def format_duration(seconds: int) -> str:
    """Human label for a retention window ("1 day", "5 minutes")."""
    units = [
        (7 * 24 * 3600, "week"),
        (24 * 3600, "day"),
        (3600, "hour"),
        (60, "minute"),
        (1, "second"),
    ]
    for size, label in units:
        if seconds >= size and seconds % size == 0:
            count = seconds // size
            return f"{count} {label}{'s' if count > 1 else ''}"
    return f"{seconds} seconds"


def dm_key_for(user_a: str, user_b: str) -> str:
    """Deterministic key so A->B and B->A resolve to the same row."""
    low, high = sorted([user_a, user_b])
    return f"{low}:{high}"


def _encode_cursor(updated_at: datetime, conversation_id: str) -> str:
    raw = f"{updated_at.isoformat()}|{conversation_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        timestamp, conversation_id = raw.split("|", 1)
        return datetime.fromisoformat(timestamp), conversation_id
    except Exception as exc:
        raise ValidationError("Malformed pagination cursor") from exc


# --------------------------------------------------------------------------- #
# reads
# --------------------------------------------------------------------------- #
async def list_conversations(
    db: AsyncSession, *, user_id: str, before: str | None = None, limit: int = 30
) -> tuple[list[ConversationOut], str | None]:
    """The Signal main list.

    Three queries total no matter how many conversations are returned:
      1. the page of conversations this user belongs to, newest activity first
      2. every member row for that page (member counts, peers, receipt counts)
      3. the last message of each conversation, via ``seq == last_seq``
    """
    limit = max(1, min(limit, 100))

    stmt = (
        select(Conversation, ConversationMember)
        .join(
            ConversationMember,
            ConversationMember.conversation_id == Conversation.id,
        )
        .where(ConversationMember.user_id == user_id)
    )
    if before:
        cursor_ts, cursor_id = _decode_cursor(before)
        stmt = stmt.where(
            (Conversation.updated_at < cursor_ts)
            | and_(Conversation.updated_at == cursor_ts, Conversation.id < cursor_id)
        )

    stmt = stmt.order_by(Conversation.updated_at.desc(), Conversation.id.desc()).limit(
        limit + 1
    )

    rows = list((await db.execute(stmt)).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    if not rows:
        return [], None

    conversation_ids = [conversation.id for conversation, _ in rows]

    # (2) every member row for the whole page.
    member_rows = list(
        await db.scalars(
            select(ConversationMember).where(
                ConversationMember.conversation_id.in_(conversation_ids)
            )
        )
    )
    members_by_conversation: dict[str, list[ConversationMember]] = {}
    for member in member_rows:
        members_by_conversation.setdefault(member.conversation_id, []).append(member)

    users_by_id = await access.users_by_ids(db, [m.user_id for m in member_rows])

    # (3) last message of each conversation - the row whose seq == last_seq.
    last_messages = list(
        await db.scalars(
            select(Message).join(
                Conversation,
                and_(
                    Message.conversation_id == Conversation.id,
                    Message.seq == Conversation.last_seq,
                ),
            ).where(Message.conversation_id.in_(conversation_ids))
        )
    )
    last_by_conversation = {m.conversation_id: m for m in last_messages}

    items = [
        serializers.serialize_conversation(
            conversation,
            members_by_conversation.get(conversation.id, []),
            users_by_id,
            user_id,
            last_message=last_by_conversation.get(conversation.id),
        )
        for conversation, _ in rows
    ]

    next_cursor = None
    if has_more:
        last_conversation = rows[-1][0]
        next_cursor = _encode_cursor(
            last_conversation.updated_at, last_conversation.id
        )
    return items, next_cursor


async def get_detail(
    db: AsyncSession, *, conversation_id: str, user_id: str
) -> ConversationDetail:
    await access.require_member(db, conversation_id, user_id)
    conversation = await access.get_conversation(db, conversation_id)
    members = await access.members_of(db, conversation_id)
    users_by_id = await access.users_by_ids(db, [m.user_id for m in members])

    last_message = await db.scalar(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.seq.desc())
        .limit(1)
    )
    return serializers.serialize_conversation(
        conversation,
        members,
        users_by_id,
        user_id,
        last_message=last_message,
        detail=True,
    )


async def _broadcast_detail(
    db: AsyncSession, conversation_id: str, event_type: str, extra: dict | None = None
) -> None:
    """Push a fresh conversation object to every member, rendered per viewer."""
    conversation = await access.get_conversation(db, conversation_id)
    members = await access.members_of(db, conversation_id)
    users_by_id = await access.users_by_ids(db, [m.user_id for m in members])
    last_message = await db.scalar(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.seq.desc())
        .limit(1)
    )
    for member in members:
        payload = serializers.conversation_payload(
            conversation,
            members,
            users_by_id,
            member.user_id,
            last_message=last_message,
            detail=True,
        )
        await connection_manager.send_to_users(
            [member.user_id],
            events.envelope(event_type, {"conversation": payload, **(extra or {})}),
        )


# --------------------------------------------------------------------------- #
# creation
# --------------------------------------------------------------------------- #
async def get_or_create_direct(
    db: AsyncSession, *, user_id: str, peer_id: str
) -> tuple[Conversation, bool]:
    """Idempotent "start a chat" - the unique ``dm_key`` guarantees one DM."""
    if user_id == peer_id:
        raise ValidationError("Cannot start a direct conversation with yourself")

    peer = await db.get(User, peer_id)
    if peer is None:
        raise UserNotFound()

    key = dm_key_for(user_id, peer_id)
    existing = await db.scalar(select(Conversation).where(Conversation.dm_key == key))
    if existing is not None:
        return existing, False

    conversation = Conversation(
        type=ConversationType.DIRECT, dm_key=key, created_by=user_id
    )
    db.add(conversation)
    # Primary keys are generated on flush, so the id has to exist before it can
    # be used as a foreign key.
    await db.flush()
    db.add(
        ConversationMember(
            conversation_id=conversation.id, user_id=user_id, role=MemberRole.MEMBER
        )
    )
    db.add(
        ConversationMember(
            conversation_id=conversation.id, user_id=peer_id, role=MemberRole.MEMBER
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        # Both users tapped "message" at the same instant - the unique index did
        # its job; return the winner.
        await db.rollback()
        existing = await db.scalar(
            select(Conversation).where(Conversation.dm_key == key)
        )
        if existing is None:  # pragma: no cover
            raise
        return existing, False

    await db.refresh(conversation)
    await _broadcast_detail(db, conversation.id, events.SERVER_CONVERSATION_NEW)
    return conversation, True


async def create_group(
    db: AsyncSession,
    *,
    creator_id: str,
    name: str,
    member_ids: list[str],
    avatar_url: str | None = None,
) -> Conversation:
    unique_ids = {uid for uid in member_ids if uid != creator_id}
    if not unique_ids:
        raise ValidationError("A group needs at least one other member")

    found = await access.users_by_ids(db, list(unique_ids))
    missing = unique_ids - set(found)
    if missing:
        raise UserNotFound(f"Unknown user id(s): {', '.join(sorted(missing))}")

    conversation = Conversation(
        type=ConversationType.GROUP,
        name=name.strip(),
        avatar_url=avatar_url,
        created_by=creator_id,
    )
    db.add(conversation)
    await db.flush()
    db.add(
        ConversationMember(
            conversation_id=conversation.id,
            user_id=creator_id,
            role=MemberRole.ADMIN,
        )
    )
    for uid in sorted(unique_ids):
        db.add(
            ConversationMember(
                conversation_id=conversation.id, user_id=uid, role=MemberRole.MEMBER
            )
        )
    await db.commit()

    creator = await db.get(User, creator_id)
    creator_name = (creator.display_name if creator else None) or "Someone"
    await message_service.create_system_message(
        db,
        conversation_id=conversation.id,
        actor_id=creator_id,
        text=f"{creator_name} created the group",
    )

    await db.refresh(conversation)
    await _broadcast_detail(db, conversation.id, events.SERVER_CONVERSATION_NEW)
    return conversation


# --------------------------------------------------------------------------- #
# membership + settings
# --------------------------------------------------------------------------- #
async def update_conversation(
    db: AsyncSession,
    *,
    conversation_id: str,
    user_id: str,
    name: str | None = None,
    avatar_url: str | None = None,
    muted: bool | None = None,
    disappear_seconds: int | None = None,
) -> Conversation:
    member = await access.require_member(db, conversation_id, user_id)
    conversation = await access.get_conversation(db, conversation_id)

    # Mute is a per-member preference, not a group setting - no admin needed.
    if muted is not None:
        member.muted = muted

    # Disappearing messages are a conversation-wide setting any member can
    # change (as in Signal), and the change is announced in the thread.
    retention_changed = (
        disappear_seconds is not None
        and disappear_seconds != conversation.disappear_seconds
    )
    if retention_changed:
        conversation.disappear_seconds = disappear_seconds or 0

    renamed = False
    if name is not None or avatar_url is not None:
        if conversation.type != ConversationType.GROUP:
            raise Unprocessable("Only group conversations can be renamed")
        if member.role != MemberRole.ADMIN:
            raise Forbidden("Only a group admin can do that")
        if name is not None and name.strip() and name.strip() != conversation.name:
            conversation.name = name.strip()
            renamed = True
        if avatar_url is not None:
            conversation.avatar_url = avatar_url
            renamed = True

    await db.commit()

    announcements: list[str] = []
    if renamed:
        announcements.append("changed the group details")
    if retention_changed:
        announcements.append(
            f"set disappearing messages to {format_duration(conversation.disappear_seconds)}"
            if conversation.disappear_seconds
            else "turned off disappearing messages"
        )

    if announcements:
        actor = await db.get(User, user_id)
        actor_name = (actor.display_name if actor else None) or "Someone"
        for announcement in announcements:
            system = await message_service.create_system_message(
                db,
                conversation_id=conversation_id,
                actor_id=user_id,
                text=f"{actor_name} {announcement}",
            )
            await message_service.fan_out_new_message(db, system)

    await db.refresh(conversation)
    await _broadcast_detail(db, conversation_id, events.SERVER_CONVERSATION_UPDATED)
    return conversation


async def add_members(
    db: AsyncSession, *, conversation_id: str, actor_id: str, user_ids: list[str]
) -> Conversation:
    await access.require_admin(db, conversation_id, actor_id)
    conversation = await access.get_conversation(db, conversation_id)
    if conversation.type != ConversationType.GROUP:
        raise Unprocessable("Members can only be added to a group")

    existing_ids = set(await access.member_ids_of(db, conversation_id))
    to_add = {uid for uid in user_ids} - existing_ids
    if not to_add:
        raise Conflict("Those users are already members")

    users = await access.users_by_ids(db, list(to_add))
    missing = to_add - set(users)
    if missing:
        raise UserNotFound(f"Unknown user id(s): {', '.join(sorted(missing))}")

    for uid in sorted(to_add):
        db.add(
            ConversationMember(
                conversation_id=conversation_id,
                user_id=uid,
                role=MemberRole.MEMBER,
                # Joining members start with a clean slate rather than inheriting
                # the entire backlog as unread.
                last_read_seq=conversation.last_seq,
                last_delivered_seq=conversation.last_seq,
            )
        )
    await db.commit()

    actor = await db.get(User, actor_id)
    actor_name = (actor.display_name if actor else None) or "Someone"
    added_names = ", ".join(
        (users[uid].display_name or "Someone") for uid in sorted(to_add)
    )
    system = await message_service.create_system_message(
        db,
        conversation_id=conversation_id,
        actor_id=actor_id,
        text=f"{actor_name} added {added_names}",
    )
    await message_service.fan_out_new_message(db, system)

    await connection_manager.send_to_users(
        await access.member_ids_of(db, conversation_id),
        events.envelope(
            events.SERVER_MEMBER_ADDED,
            {
                "conversation_id": conversation_id,
                "user_ids": sorted(to_add),
                "by_user_id": actor_id,
            },
        ),
    )
    await _broadcast_detail(db, conversation_id, events.SERVER_CONVERSATION_UPDATED)
    await db.refresh(conversation)
    return conversation


async def remove_member(
    db: AsyncSession, *, conversation_id: str, actor_id: str, user_id: str
) -> None:
    """Admin removes someone, or a member leaves (``actor_id == user_id``)."""
    conversation = await access.get_conversation(db, conversation_id)
    if conversation.type != ConversationType.GROUP:
        raise Unprocessable("Members can only be removed from a group")

    is_self_leave = actor_id == user_id
    if is_self_leave:
        await access.require_member(db, conversation_id, actor_id)
    else:
        await access.require_admin(db, conversation_id, actor_id)

    target = await access.get_member(db, conversation_id, user_id)
    if target is None:
        raise UserNotFound("That user is not a member of this group")

    remaining = [
        m for m in await access.members_of(db, conversation_id) if m.user_id != user_id
    ]
    was_admin = target.role == MemberRole.ADMIN
    await db.delete(target)

    # Never leave a group without an admin.
    if was_admin and remaining and not any(m.role == MemberRole.ADMIN for m in remaining):
        remaining[0].role = MemberRole.ADMIN
    await db.commit()

    actor = await db.get(User, actor_id)
    removed = await db.get(User, user_id)
    actor_name = (actor.display_name if actor else None) or "Someone"
    removed_name = (removed.display_name if removed else None) or "Someone"
    text = (
        f"{removed_name} left the group"
        if is_self_leave
        else f"{actor_name} removed {removed_name}"
    )

    if remaining:
        system = await message_service.create_system_message(
            db, conversation_id=conversation_id, actor_id=actor_id, text=text
        )
        await message_service.fan_out_new_message(db, system)

    # The removed user is told directly - they are no longer in the member list.
    audience = [m.user_id for m in remaining] + [user_id]
    await connection_manager.send_to_users(
        audience,
        events.envelope(
            events.SERVER_MEMBER_REMOVED,
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "by_user_id": actor_id,
            },
        ),
    )
    if remaining:
        await _broadcast_detail(db, conversation_id, events.SERVER_CONVERSATION_UPDATED)


async def mark_read(
    db: AsyncSession,
    *,
    conversation_id: str,
    user_id: str,
    last_read_message_id: str | None = None,
    last_read_seq: int | None = None,
) -> tuple[int, int]:
    return await message_service.mark_read(
        db,
        conversation_id=conversation_id,
        user_id=user_id,
        message_id=last_read_message_id,
        seq=last_read_seq,
    )
