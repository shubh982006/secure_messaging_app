from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.user import UserPrivate, UserPublic, UserSearchResponse, UserUpdate
from app.services import serializers, user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserPrivate)
async def get_me(user: CurrentUser) -> UserPrivate:
    return serializers.serialize_user(user, private=True)


@router.patch("/me", response_model=UserPrivate)
async def update_me(
    payload: UserUpdate, db: DbSession, user: CurrentUser
) -> UserPrivate:
    updated = await user_service.update_profile(
        db,
        user=user,
        display_name=payload.display_name,
        username=payload.username,
        avatar_url=payload.avatar_url,
        about=payload.about,
    )
    return serializers.serialize_user(updated, private=True)


@router.get("/search", response_model=UserSearchResponse)
async def search(
    db: DbSession,
    user: CurrentUser,
    q: str = Query(default="", max_length=120),
) -> UserSearchResponse:
    # Empty query -> people the user already talks to, which is what Signal's
    # "New chat" sheet shows before you type anything.
    users = (
        await user_service.search_users(db, viewer_id=user.id, query=q)
        if q.strip()
        else await user_service.known_users(db, viewer_id=user.id)
    )
    return UserSearchResponse(results=[serializers.serialize_user(u) for u in users])


@router.get("/{user_id}", response_model=UserPublic)
async def get_user(user_id: str, db: DbSession, _: CurrentUser) -> UserPublic:
    return serializers.serialize_user(await user_service.get_user(db, user_id))
