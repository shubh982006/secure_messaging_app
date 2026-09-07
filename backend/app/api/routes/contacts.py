from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.contact import ContactCreate, ContactListOut, ContactOut
from app.services import contact_service, serializers

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("", response_model=ContactListOut)
async def list_contacts(db: DbSession, user: CurrentUser) -> ContactListOut:
    rows = await contact_service.list_contacts(db, user.id)
    return ContactListOut(
        contacts=[
            ContactOut(
                id=contact.id,
                user=serializers.serialize_user(peer),
                nickname=contact.nickname,
                created_at=contact.created_at,
            )
            for contact, peer in rows
        ]
    )


@router.post("", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
async def add_contact(
    payload: ContactCreate, db: DbSession, user: CurrentUser
) -> ContactOut:
    contact, peer = await contact_service.add_contact(
        db,
        owner_id=user.id,
        phone_number=payload.phone_number,
        username=payload.username,
        user_id=payload.user_id,
        nickname=payload.nickname,
    )
    return ContactOut(
        id=contact.id,
        user=serializers.serialize_user(peer),
        nickname=contact.nickname,
        created_at=contact.created_at,
    )


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: str, db: DbSession, user: CurrentUser
) -> Response:
    await contact_service.delete_contact(db, owner_id=user.id, contact_id=contact_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
