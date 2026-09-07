"""PresenceService - online/offline derived from live socket ownership.

Single node: "online" == this process holds at least one socket for the user.
At scale this becomes a Redis key ``presence:{user_id}`` with a short TTL that
client heartbeats refresh; a node that misses two heartbeats treats the user as
offline. The interface below does not change.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.models import User
from app.services import access
from app.ws import events
from app.ws.manager import connection_manager


def is_online(user_id: str) -> bool:
    return connection_manager.is_online(user_id)


async def _broadcast(db: AsyncSession, user: User, online: bool) -> None:
    peers = await access.peer_ids_of(db, user.id)
    if not peers:
        return
    await connection_manager.send_to_users(
        peers,
        events.envelope(
            events.SERVER_PRESENCE_UPDATE,
            {
                "user_id": user.id,
                "is_online": online,
                "last_seen_at": user.last_seen_at.isoformat().replace("+00:00", "Z")
                if user.last_seen_at
                else None,
            },
        ),
    )


async def on_connect(db: AsyncSession, user: User) -> list[str]:
    """Mark the user online, tell their peers, and report who *they* can see."""
    user.last_seen_at = utcnow()
    await db.commit()
    await _broadcast(db, user, online=True)

    peers = await access.peer_ids_of(db, user.id)
    return [peer_id for peer_id in peers if connection_manager.is_online(peer_id)]


async def on_disconnect(db: AsyncSession, user_id: str) -> None:
    user = await db.get(User, user_id)
    if user is None:  # pragma: no cover
        return
    user.last_seen_at = utcnow()
    await db.commit()
    await _broadcast(db, user, online=False)
