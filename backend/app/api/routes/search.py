from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.models import ConversationType
from app.schemas.message import MessageSearchHit, MessageSearchResponse
from app.services import access, search_service, serializers

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/messages", response_model=MessageSearchResponse)
async def search_messages(
    db: DbSession,
    user: CurrentUser,
    q: str = Query(min_length=0, max_length=200),
    limit: int = Query(default=40, ge=1, le=100),
    conversation_id: str | None = Query(default=None),
) -> MessageSearchResponse:
    """Full-text search across every conversation the caller belongs to.

    Backed by SQLite FTS5 or a Postgres GIN index depending on the engine, and
    scoped to the caller's memberships inside the query itself - so a result can
    never come from a conversation they cannot open.
    """
    hits = await search_service.search_messages(
        db, user_id=user.id, query=q, limit=limit, conversation_id=conversation_id
    )
    if not hits:
        return MessageSearchResponse(results=[], query=q)

    # Batch the lookups the result rows need: members (for receipt counts and
    # for naming a direct conversation) and the users behind them.
    conversation_ids = {hit.conversation.id for hit in hits}
    members_by_conversation: dict[str, list] = {}
    for conversation_id_ in conversation_ids:
        members_by_conversation[conversation_id_] = await access.members_of(
            db, conversation_id_
        )
    user_ids = [
        member.user_id
        for members in members_by_conversation.values()
        for member in members
    ]
    users_by_id = await access.users_by_ids(db, user_ids)

    results = []
    for hit in hits:
        members = members_by_conversation.get(hit.conversation.id, [])
        if hit.conversation.type == ConversationType.GROUP:
            name = hit.conversation.name
        else:
            peer = next(
                (users_by_id.get(m.user_id) for m in members if m.user_id != user.id),
                None,
            )
            name = peer.display_name if peer else None

        results.append(
            MessageSearchHit(
                message=serializers.serialize_message(hit.message, members),
                conversation_id=hit.conversation.id,
                conversation_name=name,
                conversation_type=hit.conversation.type,
                snippet=search_service.snippet(hit.message.content, q),
            )
        )

    return MessageSearchResponse(results=results, query=q)
