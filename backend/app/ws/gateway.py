"""WebSocket gateway.

A thin transport: authenticate the handshake, register the socket, then loop
over typed event envelopes and hand each one to the service layer. No domain
logic lives here - REST and WebSocket both call the same services, so the two
paths can never drift apart.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.core.errors import AppError, Unauthenticated
from app.db.session import SessionFactory
from app.models import User
from app.services import access, message_service, presence_service
from app.services.rate_limit import message_limiter
from app.services.serializers import serialize_message
from app.ws import events
from app.ws.manager import connection_manager

logger = logging.getLogger(__name__)

WS_UNAUTHORIZED = 4401
WS_INTERNAL = 4500


async def _authenticate(token: str | None) -> User:
    from app.api.deps import user_from_query_token

    async with SessionFactory() as db:
        user = await user_from_query_token(db, token)
        db.expunge(user)
        return user


async def websocket_endpoint(websocket: WebSocket, token: str | None = None) -> None:
    try:
        user = await _authenticate(token)
    except Unauthenticated:
        # Accept-then-close so browsers surface a real close code instead of a
        # generic handshake failure.
        await websocket.accept()
        await websocket.close(code=WS_UNAUTHORIZED, reason="Invalid or expired token")
        return

    await websocket.accept()
    await connection_manager.connect(user.id, websocket)

    async with SessionFactory() as db:
        online_peers = await presence_service.on_connect(db, await db.merge(user))

    await websocket.send_json(
        events.envelope(
            events.SERVER_CONNECTED,
            {"user_id": user.id, "online_user_ids": online_peers},
        )
    )

    try:
        while True:
            raw = await websocket.receive_json()
            await _dispatch(websocket, user.id, raw)
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - defensive
        logger.exception("websocket loop failed for user %s", user.id)
    finally:
        was_last = await connection_manager.disconnect(user.id, websocket)
        if was_last:
            async with SessionFactory() as db:
                await presence_service.on_disconnect(db, user.id)


async def _dispatch(websocket: WebSocket, user_id: str, raw: Any) -> None:
    if not isinstance(raw, dict):
        await websocket.send_json(
            events.error_event("VALIDATION_ERROR", "Event must be a JSON object")
        )
        return

    event_type = raw.get("type")
    event_id = raw.get("id")
    payload = raw.get("payload") or {}

    handler = _HANDLERS.get(event_type)
    if handler is None:
        await websocket.send_json(
            events.error_event(
                "UNKNOWN_EVENT", f"Unsupported event type: {event_type}", event_id=event_id
            )
        )
        return

    try:
        # One short-lived session per event keeps write transactions tiny, which
        # is what makes SQLite's single writer a non-issue at this scale.
        async with SessionFactory() as db:
            await handler(db, websocket, user_id, payload, event_id)
    except AppError as exc:
        await websocket.send_json(
            events.error_event(exc.code, exc.message, event_id=event_id)
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception("handler %s failed for user %s", event_type, user_id)
        await websocket.send_json(
            events.error_event("INTERNAL_ERROR", "Something went wrong", event_id=event_id)
        )


# --------------------------------------------------------------------------- #
# handlers
# --------------------------------------------------------------------------- #
async def _handle_send(db, websocket, user_id, payload, event_id):
    if not message_limiter.allow(user_id):
        await websocket.send_json(
            events.error_event(
                "RATE_LIMITED", "You are sending messages too quickly", event_id=event_id
            )
        )
        return

    conversation_id = payload.get("conversation_id")
    message, _duplicate = await message_service.send_message(
        db,
        conversation_id=conversation_id,
        sender_id=user_id,
        content=payload.get("content"),
        message_type=payload.get("type", "text"),
        client_msg_id=payload.get("client_msg_id"),
        reply_to_id=payload.get("reply_to_id"),
        attachments=payload.get("attachments"),
    )

    members = await access.members_of(db, message.conversation_id)
    serialized = serialize_message(message, members)
    await websocket.send_json(
        events.envelope(
            events.SERVER_MESSAGE_ACK,
            {
                "client_msg_id": message.client_msg_id,
                "message_id": message.id,
                "conversation_id": message.conversation_id,
                "seq": message.seq,
                "created_at": serialized.created_at.isoformat().replace("+00:00", "Z"),
                "status": serialized.status,
            },
            event_id=event_id,
        )
    )


async def _handle_read(db, websocket, user_id, payload, event_id):
    last_read_seq, unread = await message_service.mark_read(
        db,
        conversation_id=payload.get("conversation_id"),
        user_id=user_id,
        message_id=payload.get("last_read_message_id"),
        seq=payload.get("last_read_seq"),
    )
    await websocket.send_json(
        events.envelope(
            events.SERVER_MESSAGE_READ,
            {
                "conversation_id": payload.get("conversation_id"),
                "user_id": user_id,
                "last_read_seq": last_read_seq,
                "unread_count": unread,
                "self": True,
            },
            event_id=event_id,
        )
    )


async def _handle_delivered(db, websocket, user_id, payload, event_id):
    await message_service.mark_delivered(
        db,
        conversation_id=payload.get("conversation_id"),
        user_id=user_id,
        message_id=payload.get("message_id"),
        seq=payload.get("last_delivered_seq"),
    )


async def _handle_typing_start(db, websocket, user_id, payload, event_id):
    await message_service.relay_typing(
        db,
        conversation_id=payload.get("conversation_id"),
        user_id=user_id,
        is_typing=True,
    )


async def _handle_typing_stop(db, websocket, user_id, payload, event_id):
    await message_service.relay_typing(
        db,
        conversation_id=payload.get("conversation_id"),
        user_id=user_id,
        is_typing=False,
    )


async def _handle_ping(db, websocket, user_id, payload, event_id):
    await websocket.send_json(events.envelope(events.SERVER_PONG, {}, event_id=event_id))


_HANDLERS = {
    events.CLIENT_MESSAGE_SEND: _handle_send,
    events.CLIENT_MESSAGE_READ: _handle_read,
    events.CLIENT_MESSAGE_DELIVERED: _handle_delivered,
    events.CLIENT_TYPING_START: _handle_typing_start,
    events.CLIENT_TYPING_STOP: _handle_typing_stop,
    events.CLIENT_PRESENCE_PING: _handle_ping,
}
