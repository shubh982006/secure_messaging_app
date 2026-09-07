from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ContactNotFound, Conflict, UserNotFound, ValidationError
from app.models import Contact, User


async def list_contacts(db: AsyncSession, owner_id: str) -> list[tuple[Contact, User]]:
    rows = await db.execute(
        select(Contact, User)
        .join(User, User.id == Contact.contact_user_id)
        .where(Contact.owner_id == owner_id)
        .order_by(User.display_name.asc())
    )
    return list(rows.all())


async def add_contact(
    db: AsyncSession,
    *,
    owner_id: str,
    phone_number: str | None = None,
    username: str | None = None,
    user_id: str | None = None,
    nickname: str | None = None,
) -> tuple[Contact, User]:
    if user_id:
        target = await db.get(User, user_id)
    elif phone_number:
        target = await db.scalar(select(User).where(User.phone_number == phone_number))
    else:
        target = await db.scalar(
            select(User).where(User.username == (username or "").strip().lower())
        )

    if target is None:
        raise UserNotFound("Nobody on Signal matches that")
    if target.id == owner_id:
        raise ValidationError("You cannot add yourself as a contact")

    existing = await db.scalar(
        select(Contact).where(
            Contact.owner_id == owner_id, Contact.contact_user_id == target.id
        )
    )
    if existing is not None:
        raise Conflict("Already in your contacts")

    contact = Contact(owner_id=owner_id, contact_user_id=target.id, nickname=nickname)
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact, target


async def delete_contact(db: AsyncSession, *, owner_id: str, contact_id: str) -> None:
    contact = await db.get(Contact, contact_id)
    if contact is None or contact.owner_id != owner_id:
        raise ContactNotFound()
    await db.delete(contact)
    await db.commit()
