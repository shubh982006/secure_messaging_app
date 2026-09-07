"""Idempotent demo seed.

Creates a handful of users with a believable message history so the hosted demo
is immediately usable, and so the conversation list has something to sort. Run
directly with ``python -m app.seed`` or automatically on first boot.

Every seeded account logs in with phone number + OTP 123456.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from app.db.base import utcnow
from app.db.session import SessionFactory, engine
from app.models import (
    Contact,
    Conversation,
    ConversationMember,
    ConversationType,
    MemberRole,
    Message,
    MessageType,
    User,
)
from app.services.conversation_service import dm_key_for

logger = logging.getLogger(__name__)

SEED_USERS = [
    {
        "phone_number": "+919999900001",
        "username": "alice",
        "display_name": "Alice Chen",
        "about": "Ping me before you call ☎️",
    },
    {
        "phone_number": "+919999900002",
        "username": "bob",
        "display_name": "Bob Martinez",
        "about": "Building things 🔨",
    },
    {
        "phone_number": "+919999900003",
        "username": "carol",
        "display_name": "Carol Nair",
        "about": "Speak freely.",
    },
    {
        "phone_number": "+919999900004",
        "username": "dave",
        "display_name": "Dave Okafor",
        "about": "On Signal",
    },
    {
        "phone_number": "+919999900005",
        "username": "erin",
        "display_name": "Erin Walsh",
        "about": "Coffee first ☕",
    },
]

# (sender_username, text, minutes_before_now)
DIRECT_THREADS = [
    (
        ("alice", "bob"),
        [
            ("bob", "Hey! Did the deploy go through?", 240),
            ("alice", "Yeah, went out about an hour ago 🚀", 236),
            ("bob", "Nice. Any errors in the logs?", 234),
            ("alice", "Clean so far. I'll keep watching it tonight.", 231),
            ("bob", "Appreciate it. Want to sync at 6?", 90),
            ("alice", "6 works. I'll send the link.", 88),
            ("bob", "See you at 6", 12),
        ],
    ),
    (
        ("alice", "carol"),
        [
            ("carol", "Are we still on for Saturday?", 1500),
            ("alice", "Definitely. Should I bring anything?", 1490),
            ("carol", "Just yourself 😄", 1488),
            ("carol", "Oh and the speaker if you don't mind", 300),
        ],
    ),
    (
        ("bob", "carol"),
        [
            ("bob", "Sent you the draft, let me know what you think", 2880),
            ("carol", "Reading it now", 2870),
        ],
    ),
    (
        ("alice", "dave"),
        [
            ("dave", "Welcome aboard! 🎉", 4300),
            ("alice", "Thanks Dave, excited to get started.", 4290),
        ],
    ),
]

GROUP_THREADS = [
    {
        "name": "Weekend Trip",
        "admin": "alice",
        "members": ["bob", "carol", "dave"],
        "messages": [
            ("alice", "Okay, who's actually coming this time 😂", 700),
            ("bob", "I'm in. Driving up Friday night.", 695),
            ("carol", "Same, I can take two people.", 690),
            ("dave", "Count me in. What's the budget looking like?", 400),
            ("alice", "Roughly 4k each including the cabin.", 395),
            ("carol", "That works. Sending my share tonight.", 30),
        ],
    },
    {
        "name": "Design Team",
        "admin": "carol",
        "members": ["alice", "erin"],
        "messages": [
            ("carol", "New mocks are up in the shared folder.", 1200),
            ("erin", "Looking now 👀", 1190),
            ("erin", "The spacing on the list view is much better.", 1185),
            ("alice", "Agreed. Ship it.", 1180),
        ],
    },
]


async def seed_database() -> None:
    async with SessionFactory() as db:
        existing = await db.scalar(select(User).limit(1))
        if existing is not None:
            logger.info("seed: skipped, users already exist")
            return

        now = utcnow()
        users: dict[str, User] = {}
        for spec in SEED_USERS:
            user = User(
                phone_number=spec["phone_number"],
                username=spec["username"],
                display_name=spec["display_name"],
                about=spec["about"],
                last_seen_at=now - timedelta(minutes=7),
            )
            db.add(user)
            users[spec["username"]] = user
        await db.flush()

        # Everyone knows everyone, so search and "new chat" have content.
        for owner in users.values():
            for peer in users.values():
                if owner.id != peer.id:
                    db.add(Contact(owner_id=owner.id, contact_user_id=peer.id))

        for (a_name, b_name), thread in DIRECT_THREADS:
            user_a, user_b = users[a_name], users[b_name]
            conversation = Conversation(
                type=ConversationType.DIRECT,
                dm_key=dm_key_for(user_a.id, user_b.id),
                created_by=user_a.id,
            )
            db.add(conversation)
            await db.flush()
            members = {
                name: ConversationMember(
                    conversation_id=conversation.id,
                    user_id=users[name].id,
                    role=MemberRole.MEMBER,
                )
                for name in (a_name, b_name)
            }
            for member in members.values():
                db.add(member)
            _write_thread(db, conversation, members, users, thread, now)

        for spec in GROUP_THREADS:
            admin = users[spec["admin"]]
            conversation = Conversation(
                type=ConversationType.GROUP,
                name=spec["name"],
                created_by=admin.id,
            )
            db.add(conversation)
            await db.flush()
            members = {
                spec["admin"]: ConversationMember(
                    conversation_id=conversation.id,
                    user_id=admin.id,
                    role=MemberRole.ADMIN,
                )
            }
            for name in spec["members"]:
                members[name] = ConversationMember(
                    conversation_id=conversation.id,
                    user_id=users[name].id,
                    role=MemberRole.MEMBER,
                )
            for member in members.values():
                db.add(member)

            conversation.last_seq += 1
            db.add(
                Message(
                    conversation_id=conversation.id,
                    sender_id=admin.id,
                    seq=conversation.last_seq,
                    type=MessageType.SYSTEM,
                    content=f"{admin.display_name} created the group",
                    created_at=now - timedelta(minutes=spec["messages"][0][2] + 5),
                )
            )
            _write_thread(db, conversation, members, users, spec["messages"], now)

        await db.commit()

    logger.info("seed: created %d demo users with conversations", len(SEED_USERS))


def _write_thread(db, conversation, members, users, thread, now) -> None:
    """Insert a scripted thread and set realistic read/delivered high-water marks."""
    last_created = conversation.created_at or now
    for sender_name, text, minutes_ago in thread:
        conversation.last_seq += 1
        created_at = now - timedelta(minutes=minutes_ago)
        last_created = created_at
        db.add(
            Message(
                conversation_id=conversation.id,
                sender_id=users[sender_name].id,
                seq=conversation.last_seq,
                type=MessageType.TEXT,
                content=text,
                created_at=created_at,
            )
        )

    conversation.updated_at = last_created
    last_seq = conversation.last_seq
    last_sender = thread[-1][0]

    for name, member in members.items():
        if name == last_sender:
            # The sender has obviously seen their own last message.
            member.last_read_seq = last_seq
            member.last_delivered_seq = last_seq
        else:
            # Everything arrived; everything except the final message is read,
            # which is what produces a "1 unread" badge on the demo list.
            member.last_delivered_seq = last_seq
            member.last_read_seq = max(0, last_seq - 1)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    from app.db.bootstrap import create_schema

    await create_schema()
    await seed_database()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
