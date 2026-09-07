from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict, UserNotFound
from app.models import ConversationMember, User


async def get_user(db: AsyncSession, user_id: str) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise UserNotFound()
    return user


async def update_profile(
    db: AsyncSession,
    *,
    user: User,
    display_name: str | None = None,
    username: str | None = None,
    avatar_url: str | None = None,
    about: str | None = None,
) -> User:
    if username is not None:
        normalised = username.strip().lower()
        clash = await db.scalar(
            select(User).where(User.username == normalised, User.id != user.id)
        )
        if clash is not None:
            raise Conflict("That username is taken", code="USERNAME_TAKEN")
        user.username = normalised
    if display_name is not None:
        user.display_name = display_name.strip()
    if avatar_url is not None:
        user.avatar_url = avatar_url or None
    if about is not None:
        user.about = about

    await db.commit()
    await db.refresh(user)
    return user


async def search_users(
    db: AsyncSession, *, viewer_id: str, query: str, limit: int = 20
) -> list[User]:
    """Search by display name / username / phone, for New chat and Add member."""
    term = query.strip()
    if not term:
        return []
    pattern = f"%{term.lower()}%"
    result = await db.scalars(
        select(User)
        .where(
            User.id != viewer_id,
            or_(
                User.display_name.ilike(pattern),
                User.username.ilike(pattern),
                User.phone_number.ilike(pattern),
            ),
        )
        .order_by(User.display_name.asc())
        .limit(limit)
    )
    return list(result)


async def known_users(db: AsyncSession, *, viewer_id: str, limit: int = 50) -> list[User]:
    """Everyone the viewer already shares a conversation with (the default list
    behind the New chat sheet before anything is typed)."""
    my_conversations = select(ConversationMember.conversation_id).where(
        ConversationMember.user_id == viewer_id
    )
    peer_ids = select(ConversationMember.user_id).where(
        ConversationMember.conversation_id.in_(my_conversations),
        ConversationMember.user_id != viewer_id,
    )
    result = await db.scalars(
        select(User)
        .where(User.id.in_(peer_ids))
        .order_by(User.display_name.asc())
        .limit(limit)
    )
    return list(result)
