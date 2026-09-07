"""ConnectionManager - the single fan-out seam of the whole system.

At single-node scale this is an in-process ``dict[user_id, set[WebSocket]]``.
Going multi-node means implementing the same three methods on top of Redis
Pub/Sub (publish to ``user:{id}``, each node subscribes for the users it holds)
and swapping the singleton below. No service-layer code changes - that is the
entire point of routing every outbound event through this interface.

See SYSTEM_DESIGN.md section 9.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class BaseConnectionManager(ABC):
    @abstractmethod
    async def connect(self, user_id: str, websocket: WebSocket) -> bool:
        """Register a socket. Returns True if this is the user's first one."""

    @abstractmethod
    async def disconnect(self, user_id: str, websocket: WebSocket) -> bool:
        """Deregister a socket. Returns True if it was the user's last one."""

    @abstractmethod
    async def send_to_users(
        self, user_ids: Iterable[str], event: dict[str, Any]
    ) -> None:
        """Deliver an event to every live socket of every listed user."""

    @abstractmethod
    def is_online(self, user_id: str) -> bool: ...

    @abstractmethod
    def online_users(self) -> set[str]: ...


class InMemoryConnectionManager(BaseConnectionManager):
    """Single-process fan-out.

    A user may hold several sockets at once (multiple tabs / devices), so the
    map is user_id -> set of sockets and every one of them receives the event.
    """

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, websocket: WebSocket) -> bool:
        async with self._lock:
            sockets = self._connections.setdefault(user_id, set())
            was_empty = not sockets
            sockets.add(websocket)
            return was_empty

    async def disconnect(self, user_id: str, websocket: WebSocket) -> bool:
        async with self._lock:
            sockets = self._connections.get(user_id)
            if not sockets:
                return False
            sockets.discard(websocket)
            if not sockets:
                self._connections.pop(user_id, None)
                return True
            return False

    async def send_to_users(
        self, user_ids: Iterable[str], event: dict[str, Any]
    ) -> None:
        targets: list[tuple[str, WebSocket]] = []
        async with self._lock:
            for user_id in set(user_ids):
                for socket in self._connections.get(user_id, set()):
                    targets.append((user_id, socket))

        if not targets:
            return

        # Fan out concurrently; a single dead socket must never block the rest.
        results = await asyncio.gather(
            *(socket.send_json(event) for _, socket in targets),
            return_exceptions=True,
        )
        for (user_id, socket), result in zip(targets, results, strict=True):
            if isinstance(result, Exception):
                logger.debug("dropping dead socket for %s: %s", user_id, result)
                await self.disconnect(user_id, socket)

    def is_online(self, user_id: str) -> bool:
        return bool(self._connections.get(user_id))

    def online_users(self) -> set[str]:
        return set(self._connections.keys())

    def connection_count(self) -> int:
        return sum(len(sockets) for sockets in self._connections.values())


# The process-wide singleton. Swap this line for RedisConnectionManager() to go
# multi-node - nothing else in the codebase needs to know.
connection_manager: BaseConnectionManager = InMemoryConnectionManager()
