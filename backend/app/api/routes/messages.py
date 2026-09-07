from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.message import MessageOut, ReactionIn
from app.services import access, message_service, serializers

router = APIRouter(prefix="/messages", tags=["messages"])


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: str, db: DbSession, user: CurrentUser
) -> Response:
    await message_service.delete_message(db, message_id=message_id, user_id=user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{message_id}/reactions", response_model=MessageOut)
async def add_reaction(
    message_id: str, payload: ReactionIn, db: DbSession, user: CurrentUser
) -> MessageOut:
    message = await message_service.toggle_reaction(
        db, message_id=message_id, user_id=user.id, emoji=payload.emoji, add=True
    )
    members = await access.members_of(db, message.conversation_id)
    return serializers.serialize_message(message, members)


@router.delete("/{message_id}/reactions/{emoji}", response_model=MessageOut)
async def remove_reaction(
    message_id: str, emoji: str, db: DbSession, user: CurrentUser
) -> MessageOut:
    message = await message_service.toggle_reaction(
        db, message_id=message_id, user_id=user.id, emoji=emoji, add=False
    )
    members = await access.members_of(db, message.conversation_id)
    return serializers.serialize_message(message, members)
