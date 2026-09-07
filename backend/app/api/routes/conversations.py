from __future__ import annotations

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, DbSession
from app.models import ConversationType
from app.schemas.conversation import (
    AddMembersIn,
    ConversationCreate,
    ConversationDetail,
    ConversationPage,
    ConversationUpdate,
)
from app.schemas.message import (
    MessageCreate,
    MessageOut,
    MessagePage,
    ReadMarkerIn,
    ReadMarkerOut,
)
from app.services import access, conversation_service, message_service, serializers

router = APIRouter(prefix="/conversations", tags=["conversations"])


# --------------------------------------------------------------------------- #
# list / create
# --------------------------------------------------------------------------- #
@router.get("", response_model=ConversationPage)
async def list_conversations(
    db: DbSession,
    user: CurrentUser,
    before: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
) -> ConversationPage:
    items, next_cursor = await conversation_service.list_conversations(
        db, user_id=user.id, before=before, limit=limit
    )
    return ConversationPage(conversations=items, next_cursor=next_cursor)


@router.post("", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate, db: DbSession, user: CurrentUser
) -> ConversationDetail:
    if payload.type == ConversationType.DIRECT:
        conversation, _ = await conversation_service.get_or_create_direct(
            db, user_id=user.id, peer_id=payload.user_id or ""
        )
    else:
        conversation = await conversation_service.create_group(
            db,
            creator_id=user.id,
            name=payload.name or "",
            member_ids=payload.member_ids or [],
            avatar_url=payload.avatar_url,
        )
    return await conversation_service.get_detail(
        db, conversation_id=conversation.id, user_id=user.id
    )


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str, db: DbSession, user: CurrentUser
) -> ConversationDetail:
    return await conversation_service.get_detail(
        db, conversation_id=conversation_id, user_id=user.id
    )


@router.patch("/{conversation_id}", response_model=ConversationDetail)
async def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    db: DbSession,
    user: CurrentUser,
) -> ConversationDetail:
    await conversation_service.update_conversation(
        db,
        conversation_id=conversation_id,
        user_id=user.id,
        name=payload.name,
        avatar_url=payload.avatar_url,
        muted=payload.muted,
        disappear_seconds=payload.disappear_seconds,
    )
    return await conversation_service.get_detail(
        db, conversation_id=conversation_id, user_id=user.id
    )


# --------------------------------------------------------------------------- #
# membership
# --------------------------------------------------------------------------- #
@router.post("/{conversation_id}/members", response_model=ConversationDetail)
async def add_members(
    conversation_id: str,
    payload: AddMembersIn,
    db: DbSession,
    user: CurrentUser,
) -> ConversationDetail:
    await conversation_service.add_members(
        db,
        conversation_id=conversation_id,
        actor_id=user.id,
        user_ids=payload.user_ids,
    )
    return await conversation_service.get_detail(
        db, conversation_id=conversation_id, user_id=user.id
    )


@router.delete(
    "/{conversation_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_member(
    conversation_id: str, user_id: str, db: DbSession, user: CurrentUser
) -> Response:
    await conversation_service.remove_member(
        db, conversation_id=conversation_id, actor_id=user.id, user_id=user_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def leave_conversation(
    conversation_id: str, db: DbSession, user: CurrentUser
) -> Response:
    """Leave a group. Direct conversations cannot be left, only muted."""
    await conversation_service.remove_member(
        db, conversation_id=conversation_id, actor_id=user.id, user_id=user.id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- #
# messages
# --------------------------------------------------------------------------- #
@router.get("/{conversation_id}/messages", response_model=MessagePage)
async def get_messages(
    conversation_id: str,
    db: DbSession,
    user: CurrentUser,
    before: int | None = Query(default=None, description="seq cursor, walks backwards"),
    after: int | None = Query(default=None, description="seq cursor, reconnect backfill"),
    limit: int = Query(default=50, ge=1, le=100),
) -> MessagePage:
    messages, reply_map, members, next_cursor = await message_service.get_history(
        db,
        conversation_id=conversation_id,
        user_id=user.id,
        before=before,
        after=after,
        limit=limit,
    )
    sender_ids = [m.sender_id for m in messages if m.sender_id]
    sender_ids += [m.sender_id for m in reply_map.values() if m.sender_id]
    users_by_id = await access.users_by_ids(db, sender_ids)
    return MessagePage(
        messages=[
            serializers.serialize_message(
                message,
                members,
                reply_target=reply_map.get(message.reply_to_id or ""),
                users_by_id=users_by_id,
            )
            for message in messages
        ],
        next_cursor=next_cursor,
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(
    conversation_id: str,
    payload: MessageCreate,
    db: DbSession,
    user: CurrentUser,
) -> MessageOut:
    """REST fallback for sending.

    The primary path is the WebSocket ``message.send`` event; this exists for
    clients without a live socket and shares the exact same service call, so
    behaviour (ordering, idempotency, fan-out) is identical.
    """
    message, _ = await message_service.send_message(
        db,
        conversation_id=conversation_id,
        sender_id=user.id,
        content=payload.content,
        message_type=payload.type,
        client_msg_id=payload.client_msg_id,
        reply_to_id=payload.reply_to_id,
        attachments=[a.model_dump() for a in payload.attachments or []],
    )
    members = await access.members_of(db, conversation_id)
    users_by_id = await access.users_by_ids(db, [m.user_id for m in members])
    return serializers.serialize_message(message, members, users_by_id=users_by_id)


@router.post("/{conversation_id}/read", response_model=ReadMarkerOut)
async def mark_read(
    conversation_id: str,
    payload: ReadMarkerIn,
    db: DbSession,
    user: CurrentUser,
) -> ReadMarkerOut:
    last_read_seq, unread = await conversation_service.mark_read(
        db,
        conversation_id=conversation_id,
        user_id=user.id,
        last_read_message_id=payload.last_read_message_id,
        last_read_seq=payload.last_read_seq,
    )
    return ReadMarkerOut(unread_count=unread, last_read_seq=last_read_seq)
