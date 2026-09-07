"""RedisConnectionManager - the multi-node implementation of the fan-out seam.

SYSTEM_DESIGN.md section 9 describes this as the one thing standing between a
single node and N nodes. This is that thing, built.

Two problems have to be solved to run more than one API node:

1. **Delivery.** User A holds a socket on node 1, user B on node 2. Node 1 has
   no socket for B, so it PUBLISHes to ``ws:user:{B}`` and whichever node owns
   B's socket receives it and pushes it down the wire.

2. **Presence.** ``is_online()`` is called synchronously all over the
   serializers, so it cannot become an ``await`` without rewriting the render
   path. Instead every node keeps an in-memory *mirror* of the global online
   set, kept fresh two ways: pub/sub deltas for immediacy, and a periodic
   reconciliation against Redis for correctness (which is also what reaps users
   stranded by a node that died without cleaning up).

The public interface is identical to InMemoryConnectionManager, so no service
code changes - which was the entire point of routing every outbound event
through this class.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
import uuid
from collections.abc import Iterable
from typing import Any

import redis.asyncio as redis
from fastapi import WebSocket

from app.ws.manager import BaseConnectionManager

logger = logging.getLogger(__name__)

# Channel a node subscribes to for each user whose socket it currently holds.
USER_CHANNEL = "ws:user:{user_id}"
# Fan-out channel for presence deltas (every node subscribes).
PRESENCE_CHANNEL = "ws:presence"
# Per-node set of the users it is holding, with a TTL so a dead node's users
# stop being reported as online once its heartbeat stops.
NODE_USERS_KEY = "presence:node:{node_id}"
NODE_REGISTRY_KEY = "presence:nodes"

# Failover budget. A node that dies gracefully publishes offline deltas and is
# reflected instantly; a node that is SIGKILLed (crash, OOM, `kill -9`) can only
# be detected by its heartbeat going stale, so these set that detection window:
# worst case NODE_TTL + RECONCILE seconds. Tighter values detect faster at the
# cost of more Redis chatter.
NODE_TTL_SECONDS = 15
HEARTBEAT_SECONDS = 5
RECONCILE_SECONDS = 5


def _default_node_id() -> str:
    """Stable-ish per-process id, so logs and Redis keys are traceable."""
    return os.environ.get("NODE_ID") or f"{socket.gethostname()}-{os.getpid()}"


class RedisConnectionManager(BaseConnectionManager):
    def __init__(self, url: str, node_id: str | None = None) -> None:
        self.node_id = node_id or _default_node_id()
        self._url = url
        self._redis: redis.Redis | None = None
        self._pubsub: redis.client.PubSub | None = None

        # Sockets this node actually holds.
        self._local: dict[str, set[WebSocket]] = {}
        # Mirror of who is online cluster-wide: user_id -> set of node ids.
        self._online: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()
        # redis-py's PubSub multiplexes one connection and is NOT safe to use
        # from two tasks at once. subscribe()/unsubscribe() run on the request
        # path while the listener polls get_message(), so every touch of the
        # PubSub object goes through this lock. Without it, a subscribe racing a
        # poll silently drops presence deltas.
        self._pubsub_lock = asyncio.Lock()
        self._tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    async def start(self) -> None:
        self._redis = redis.from_url(self._url, decode_responses=True)
        await self._redis.ping()
        self._pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        async with self._pubsub_lock:
            await self._pubsub.subscribe(PRESENCE_CHANNEL)

        # Register BEFORE the first reconcile. Registration used to happen only
        # on the first heartbeat (10s in), which meant an early reconcile saw an
        # empty node registry and wiped every peer's users out of the mirror.
        await self._register()
        await self._reconcile()
        self._tasks = [
            asyncio.create_task(self._listen(), name="redis-ws-listen"),
            asyncio.create_task(self._heartbeat(), name="redis-ws-heartbeat"),
            asyncio.create_task(self._reconcile_loop(), name="redis-ws-reconcile"),
        ]
        logger.info("redis fan-out active (node=%s)", self.node_id)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks = []

        if self._redis is not None:
            # Leave cleanly so peers stop reporting this node's users as online
            # immediately, rather than waiting for the TTL to lapse.
            try:
                await self._redis.delete(NODE_USERS_KEY.format(node_id=self.node_id))
                await self._redis.hdel(NODE_REGISTRY_KEY, self.node_id)
                for user_id in list(self._local):
                    await self._publish_presence(user_id, online=False)
            except Exception:  # pragma: no cover - best effort on shutdown
                logger.debug("redis shutdown cleanup failed", exc_info=True)

        if self._pubsub is not None:
            await self._pubsub.aclose()
        if self._redis is not None:
            await self._redis.aclose()

    # ------------------------------------------------------------------ #
    # BaseConnectionManager
    # ------------------------------------------------------------------ #
    async def connect(self, user_id: str, websocket: WebSocket) -> bool:
        async with self._lock:
            sockets = self._local.setdefault(user_id, set())
            first_here = not sockets
            sockets.add(websocket)

        if first_here:
            # Start listening for events addressed to this user from other nodes.
            assert self._pubsub is not None
            async with self._pubsub_lock:
                await self._pubsub.subscribe(USER_CHANNEL.format(user_id=user_id))
            assert self._redis is not None
            await self._redis.sadd(NODE_USERS_KEY.format(node_id=self.node_id), user_id)
            await self._register()
            self._mark_online(user_id, self.node_id)
            await self._publish_presence(user_id, online=True)

        return first_here

    async def disconnect(self, user_id: str, websocket: WebSocket) -> bool:
        async with self._lock:
            sockets = self._local.get(user_id)
            if not sockets:
                return False
            sockets.discard(websocket)
            if sockets:
                return False
            self._local.pop(user_id, None)

        assert self._pubsub is not None and self._redis is not None
        try:
            async with self._pubsub_lock:
                await self._pubsub.unsubscribe(USER_CHANNEL.format(user_id=user_id))
            await self._redis.srem(NODE_USERS_KEY.format(node_id=self.node_id), user_id)
        except Exception:  # pragma: no cover
            logger.debug("redis unsubscribe failed for %s", user_id, exc_info=True)

        self._mark_offline(user_id, self.node_id)
        await self._publish_presence(user_id, online=False)
        return True

    async def send_to_users(
        self, user_ids: Iterable[str], event: dict[str, Any]
    ) -> None:
        targets = set(user_ids)
        if not targets:
            return

        # Local sockets first - no network hop for same-node recipients, which
        # is the common case under sticky routing.
        remote: set[str] = set()
        async with self._lock:
            local_pairs = [
                (user_id, socket)
                for user_id in targets
                for socket in self._local.get(user_id, set())
            ]
            for user_id in targets:
                if not self._local.get(user_id):
                    remote.add(user_id)

        if local_pairs:
            results = await asyncio.gather(
                *(socket.send_json(event) for _, socket in local_pairs),
                return_exceptions=True,
            )
            for (user_id, socket), result in zip(local_pairs, results, strict=True):
                if isinstance(result, Exception):
                    await self.disconnect(user_id, socket)

        # Anyone not here is either on another node or offline. Publishing to an
        # unheld channel is a no-op, so no membership check is needed.
        if remote and self._redis is not None:
            payload = json.dumps(event)
            pipe = self._redis.pipeline()
            for user_id in remote:
                pipe.publish(USER_CHANNEL.format(user_id=user_id), payload)
            await pipe.execute()

    def is_online(self, user_id: str) -> bool:
        return bool(self._online.get(user_id))

    def online_users(self) -> set[str]:
        return {user_id for user_id, nodes in self._online.items() if nodes}

    def connection_count(self) -> int:
        return sum(len(sockets) for sockets in self._local.values())

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    def _mark_online(self, user_id: str, node_id: str) -> None:
        self._online.setdefault(user_id, set()).add(node_id)

    def _mark_offline(self, user_id: str, node_id: str) -> None:
        nodes = self._online.get(user_id)
        if not nodes:
            return
        nodes.discard(node_id)
        if not nodes:
            self._online.pop(user_id, None)

    async def _register(self) -> None:
        """Announce this node and refresh its liveness stamp."""
        if self._redis is None:
            return
        await self._redis.hset(
            NODE_REGISTRY_KEY, self.node_id, str(int(time.time()))
        )
        await self._redis.expire(
            NODE_USERS_KEY.format(node_id=self.node_id), NODE_TTL_SECONDS
        )

    async def _publish_presence(self, user_id: str, *, online: bool) -> None:
        if self._redis is None:
            return
        await self._redis.publish(
            PRESENCE_CHANNEL,
            json.dumps({"user_id": user_id, "node_id": self.node_id, "online": online}),
        )

    async def _listen(self) -> None:
        """Route inbound pub/sub messages to local sockets."""
        assert self._pubsub is not None
        while True:
            try:
                # Short poll under the lock so subscribes are never blocked for
                # long; the sleep below keeps this from spinning the event loop.
                async with self._pubsub_lock:
                    message = await self._pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=0.05
                    )
                if message is None:
                    await asyncio.sleep(0.005)
                    continue

                channel = message["channel"]
                if channel == PRESENCE_CHANNEL:
                    delta = json.loads(message["data"])
                    if delta["node_id"] == self.node_id:
                        continue  # our own echo
                    if delta["online"]:
                        self._mark_online(delta["user_id"], delta["node_id"])
                    else:
                        self._mark_offline(delta["user_id"], delta["node_id"])
                    continue

                # ws:user:{id} - an event for a socket this node holds.
                user_id = channel.rsplit(":", 1)[-1]
                event = json.loads(message["data"])
                async with self._lock:
                    sockets = list(self._local.get(user_id, set()))
                if not sockets:
                    continue
                results = await asyncio.gather(
                    *(socket.send_json(event) for socket in sockets),
                    return_exceptions=True,
                )
                for socket, result in zip(sockets, results, strict=True):
                    if isinstance(result, Exception):
                        await self.disconnect(user_id, socket)

            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover - the listener must not die
                logger.exception("redis listener iteration failed")
                await asyncio.sleep(0.5)

    async def _heartbeat(self) -> None:
        """Keep this node's liveness stamp fresh so peers do not reap it."""
        while True:
            try:
                await asyncio.sleep(HEARTBEAT_SECONDS)
                await self._register()
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover
                logger.exception("redis heartbeat iteration failed")

    async def _reconcile_loop(self) -> None:
        """Rebuild the mirror on a fixed cadence.

        Kept separate from the heartbeat so reaping a dead node is never delayed
        by heartbeat timing - the two have different jobs and different clocks.
        """
        while True:
            try:
                await asyncio.sleep(RECONCILE_SECONDS)
                await self._reconcile()
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover
                logger.exception("redis reconcile iteration failed")

    async def _reconcile(self) -> None:
        """Rebuild the presence mirror from Redis.

        Pub/sub deltas keep presence instant; this keeps it *correct* - it is
        what removes users stranded by a node that died without cleaning up
        (its per-node key simply expires).
        """
        if self._redis is None:
            return

        registry = await self._redis.hgetall(NODE_REGISTRY_KEY)
        now = int(time.time())
        rebuilt: dict[str, set[str]] = {}
        stale: list[str] = []

        for node_id, seen_at in registry.items():
            if node_id != self.node_id and now - int(seen_at) > NODE_TTL_SECONDS:
                stale.append(node_id)
                continue
            members = await self._redis.smembers(
                NODE_USERS_KEY.format(node_id=node_id)
            )
            for user_id in members:
                rebuilt.setdefault(user_id, set()).add(node_id)

        # This node's own sockets are authoritative for this node.
        async with self._lock:
            for user_id in self._local:
                rebuilt.setdefault(user_id, set()).add(self.node_id)

        self._online = rebuilt

        if stale:
            pipe = self._redis.pipeline()
            for node_id in stale:
                pipe.hdel(NODE_REGISTRY_KEY, node_id)
                pipe.delete(NODE_USERS_KEY.format(node_id=node_id))
            await pipe.execute()
            logger.info("reaped %d stale node(s): %s", len(stale), ", ".join(stale))


def new_node_id() -> str:
    return f"{_default_node_id()}-{uuid.uuid4().hex[:6]}"
