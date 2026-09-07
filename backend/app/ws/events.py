"""WebSocket event envelope + the full event vocabulary.

Envelope (both directions)::

    { "type": "...", "id": "<uuid>", "ts": "<iso8601>", "payload": { ... } }
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any


# --- client -> server --------------------------------------------------------
CLIENT_MESSAGE_SEND = "message.send"
CLIENT_MESSAGE_READ = "message.read"
CLIENT_MESSAGE_DELIVERED = "message.delivered"
CLIENT_TYPING_START = "typing.start"
CLIENT_TYPING_STOP = "typing.stop"
CLIENT_PRESENCE_PING = "presence.ping"

# --- server -> client --------------------------------------------------------
SERVER_CONNECTED = "connected"
SERVER_MESSAGE_ACK = "message.ack"
SERVER_MESSAGE_NEW = "message.new"
SERVER_MESSAGE_DELIVERED = "message.delivered"
SERVER_MESSAGE_READ = "message.read"
SERVER_MESSAGE_DELETED = "message.deleted"
SERVER_MESSAGE_EXPIRED = "message.expired"
SERVER_MESSAGE_REACTION = "message.reaction"
SERVER_TYPING = "typing"
SERVER_PRESENCE_UPDATE = "presence.update"
SERVER_CONVERSATION_NEW = "conversation.new"
SERVER_CONVERSATION_UPDATED = "conversation.updated"
SERVER_MEMBER_ADDED = "member.added"
SERVER_MEMBER_REMOVED = "member.removed"
SERVER_PONG = "presence.pong"
SERVER_ERROR = "error"


def envelope(
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    event_id: str | None = None,
) -> dict[str, Any]:
    return {
        "type": event_type,
        "id": event_id or str(uuid.uuid4()),
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "payload": payload or {},
    }


def error_event(code: str, message: str, *, event_id: str | None = None) -> dict[str, Any]:
    return envelope(SERVER_ERROR, {"code": code, "message": message}, event_id=event_id)
