"""Membership / authorisation helpers shared by every service.

Rule enforced everywhere: a user can only read or mutate a conversation they
are a member of. Admin-only actions additionally check the member role.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConversationNotFound, Forbidden
from app.models import Conversation, ConversationMember, MemberRole, User


async def get_conversation(db: AsyncSession, conversation_id: str) -> Conversation:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise ConversationNotFound()
    return conversation


async def get_member(
    db: AsyncSession, conversation_id: str, user_id: str
) -> ConversationMember | None:
    return await db.scalar(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == user_id,
        )
    )


async def require_member(
    db: AsyncSession, conversation_id: str, user_id: str
) -> ConversationMember:
    member = await get_member(db, conversation_id, user_id)
    if member is None:
        # 404 rather than 403 so membership cannot be probed by id.
        raise ConversationNotFound()
    return member


async def require_admin(
    db: AsyncSession, conversation_id: str, user_id: str
) -> ConversationMember:
    member = await require_member(db, conversation_id, user_id)
    if member.role != MemberRole.ADMIN:
        raise Forbidden("Only a group admin can do that")
    return member


async def load_send_context(
    db: AsyncSession, conversation_id: str, user_id: str
) -> tuple[Conversation, list[ConversationMember], ConversationMember]:
    """Everything the send path needs, in a single round trip.

    The hot path used to issue three separate SELECTs (membership check,
    conversation row, member list). Under a burst that dominated latency, so
    they are collapsed into one join here and the sender's own membership is
    picked out in Python.
    """
    rows = (
        await db.execute(
            select(Conversation, ConversationMember)
            .join(
                ConversationMember,
                ConversationMember.conversation_id == Conversation.id,
            )
            .where(Conversation.id == conversation_id)
        )
    ).all()
    if not rows:
        raise ConversationNotFound()

    conversation = rows[0][0]
    members = [member for _, member in rows]
    me = next((m for m in members if m.user_id == user_id), None)
    if me is None:
        # 404 rather than 403 so membership cannot be probed by id.
        raise ConversationNotFound()
    return conversation, members, me


async def members_of(db: AsyncSession, conversation_id: str) -> list[ConversationMember]:
    result = await db.scalars(
        select(ConversationMember).where(
            ConversationMember.conversation_id == conversation_id
        )
    )
    return list(result)


async def member_ids_of(db: AsyncSession, conversation_id: str) -> list[str]:
    result = await db.scalars(
        select(ConversationMember.user_id).where(
            ConversationMember.conversation_id == conversation_id
        )
    )
    return list(result)


async def users_by_ids(db: AsyncSession, user_ids: list[str]) -> dict[str, User]:
    if not user_ids:
        return {}
    result = await db.scalars(select(User).where(User.id.in_(set(user_ids))))
    return {user.id: user for user in result}


async def peer_ids_of(db: AsyncSession, user_id: str) -> list[str]:
    """Every user who shares at least one conversation with ``user_id``.

    This is the presence broadcast audience. One query, no fan-out per
    conversation.
    """
    my_conversations = select(ConversationMember.conversation_id).where(
        ConversationMember.user_id == user_id
    )
    result = await db.scalars(
        select(ConversationMember.user_id)
        .where(
            ConversationMember.conversation_id.in_(my_conversations),
            ConversationMember.user_id != user_id,
        )
        .distinct()
    )
    return list(result)
