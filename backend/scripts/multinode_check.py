"""Proof that the Redis fan-out actually works across separate API processes.

SYSTEM_DESIGN.md claims the only thing between one node and N is swapping
`ConnectionManager`. This script proves it rather than asserting it:

  * two independent uvicorn processes, each with its own event loop and its own
    in-process socket table, sharing one Redis and one database
  * user A connects to node 1 ONLY, user B to node 2 ONLY
  * a message sent on node 1 must arrive on node 2, and receipts must travel
    back the other way

If the fan-out were still in-process, every cross-node assertion here fails.

    python scripts/multinode_check.py
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import websockets

BACKEND = Path(__file__).resolve().parents[1]
NODE_A_PORT = int(os.environ.get("NODE_A_PORT", 8021))
NODE_B_PORT = int(os.environ.get("NODE_B_PORT", 8022))
# A dedicated DB index: presence is namespaced per Redis database, so sharing
# one with a running dev server would mix foreign nodes into the registry.
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/15")
DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"sqlite+aiosqlite:///{BACKEND / 'multinode.db'}"
)

ok, fail = [], []


def check(name: str, cond: bool, extra: str = "") -> None:
    (ok if cond else fail).append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))


class Node:
    def __init__(self, port: int, node_id: str) -> None:
        self.port = port
        self.node_id = node_id
        self.base = f"http://127.0.0.1:{port}"
        self.process: subprocess.Popen | None = None

    def start(self) -> None:
        env = {
            **os.environ,
            "DATABASE_URL": DATABASE_URL,
            "REDIS_URL": REDIS_URL,
            "NODE_ID": self.node_id,
            "JWT_SECRET": "multinode-test-secret",
            "SEED_ON_STARTUP": "true",
            "PYTHONPATH": str(BACKEND),
        }
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app",
             "--host", "127.0.0.1", "--port", str(self.port), "--log-level", "warning"],
            cwd=BACKEND, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def wait_ready(self, timeout: float = 45) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                response = httpx.get(f"{self.base}/health", timeout=1)
                if response.status_code == 200:
                    return response.json()
            except Exception:
                pass
            time.sleep(0.3)
        raise RuntimeError(f"node {self.node_id} on :{self.port} never became ready")

    def stop(self, *, hard: bool = False) -> None:
        """``hard=True`` is SIGKILL: no graceful shutdown, no chance to publish
        offline deltas. That is the case worth testing, because a crashed or
        OOM-killed node never gets to say goodbye."""
        if self.process and self.process.poll() is None:
            if hard:
                self.process.kill()
                self.process.wait(timeout=10)
                return
            self.process.send_signal(signal.SIGINT)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()


class Client:
    """A WebSocket client pinned to exactly one node."""

    def __init__(self, node: Node, token: str, user: dict) -> None:
        self.node = node
        self.token = token
        self.user = user
        self.events: list[dict] = []
        self.ws = None

    async def connect(self) -> None:
        url = f"ws://127.0.0.1:{self.node.port}/api/v1/ws?token={self.token}"
        self.ws = await websockets.connect(url)
        asyncio.create_task(self._pump())
        await asyncio.sleep(0.3)

    async def _pump(self) -> None:
        try:
            async for raw in self.ws:
                self.events.append(json.loads(raw))
        except Exception:
            pass

    async def send(self, event_type: str, payload: dict) -> None:
        await self.ws.send(json.dumps({
            "type": event_type, "id": str(uuid.uuid4()), "payload": payload
        }))

    def of(self, event_type: str) -> list[dict]:
        return [e for e in self.events if e["type"] == event_type]

    async def wait_for(self, event_type: str, timeout: float = 6.0) -> dict | None:
        for _ in range(int(timeout / 0.05)):
            found = self.of(event_type)
            if found:
                return found[-1]
            await asyncio.sleep(0.05)
        return None

    async def close(self) -> None:
        if self.ws:
            await self.ws.close()


async def login(base: str, phone: str) -> tuple[str, dict]:
    async with httpx.AsyncClient(timeout=10) as http:
        await http.post(f"{base}/api/v1/auth/request-otp", json={"phone_number": phone})
        response = await http.post(
            f"{base}/api/v1/auth/verify-otp",
            json={"phone_number": phone, "code": "123456"},
        )
        body = response.json()
        return body["access_token"], body["user"]


async def run(node_a: Node, node_b: Node) -> int:
    health_a = node_a.wait_ready()
    health_b = node_b.wait_ready()

    print("\n=== 1. TWO INDEPENDENT NODES ===")
    check("node A is up", health_a["status"] == "ok", str(health_a))
    check("node B is up", health_b["status"] == "ok", str(health_b))
    check("both report the redis fan-out",
          health_a["fanout"] == "redis" and health_b["fanout"] == "redis",
          f"{health_a['fanout']} / {health_b['fanout']}")
    check("they are genuinely different processes",
          health_a["node_id"] != health_b["node_id"],
          f"{health_a['node_id']} vs {health_b['node_id']}")

    # Tokens are stateless, so a token minted on A is valid on B - which is the
    # thing that makes the app tier horizontally scalable in the first place.
    token_a, user_a = await login(node_a.base, "+919999900001")
    token_b, user_b = await login(node_b.base, "+919999900002")

    async with httpx.AsyncClient(timeout=10) as http:
        cross = await http.get(
            f"{node_b.base}/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token_a}"},
        )
    check("a token minted on node A is accepted by node B",
          cross.status_code == 200 and cross.json()["id"] == user_a["id"],
          f"{cross.status_code} {cross.text[:120]}")

    print("\n=== 2. SOCKETS ON SEPARATE NODES ===")
    alice = Client(node_a, token_a, user_a)
    bob = Client(node_b, token_b, user_b)
    await alice.connect()
    await bob.connect()
    await asyncio.sleep(1.0)

    check("Alice's socket is held by node A", (await alice.wait_for("connected")) is not None)
    check("Bob's socket is held by node B", (await bob.wait_for("connected")) is not None)

    a_health = httpx.get(f"{node_a.base}/health").json()
    b_health = httpx.get(f"{node_b.base}/health").json()
    check("each node holds exactly one socket",
          a_health["live_sockets"] == 1 and b_health["live_sockets"] == 1,
          f"A={a_health['live_sockets']} B={b_health['live_sockets']}")
    check("but both see 2 users online cluster-wide",
          a_health["online_users"] == 2 and b_health["online_users"] == 2,
          f"A={a_health['online_users']} B={b_health['online_users']}")

    print("\n=== 3. CROSS-NODE PRESENCE ===")
    # Two independent paths have to work, and they are tested separately:
    #   (a) the snapshot in `connected`, for peers who were ALREADY online on
    #       another node when this client connected
    #   (b) the pub/sub delta, for peers who come online afterwards
    bob_connected = (await bob.wait_for("connected"))["payload"]
    check("node B's snapshot lists Alice, who is online on node A",
          user_a["id"] in bob_connected["online_user_ids"],
          str(bob_connected))

    alice_deltas = [
        e for e in alice.of("presence.update")
        if e["payload"]["user_id"] == user_b["id"] and e["payload"]["is_online"]
    ]
    check("node A received a live presence delta when Bob connected to node B",
          len(alice_deltas) > 0, str(alice.of("presence.update")))

    print("\n=== 4. CROSS-NODE MESSAGE DELIVERY ===")
    async with httpx.AsyncClient(timeout=10) as http:
        conversation = (await http.post(
            f"{node_a.base}/api/v1/conversations",
            json={"type": "direct", "user_id": user_b["id"]},
            headers={"Authorization": f"Bearer {token_a}"},
        )).json()

    text = f"crossing nodes {uuid.uuid4().hex[:8]}"
    client_msg_id = str(uuid.uuid4())
    started = time.perf_counter()
    await alice.send("message.send", {
        "conversation_id": conversation["id"],
        "client_msg_id": client_msg_id,
        "type": "text",
        "content": text,
    })

    ack = await alice.wait_for("message.ack")
    check("sender is acked by its own node", ack is not None and ack["payload"]["client_msg_id"] == client_msg_id)

    delivered = await bob.wait_for("message.new")
    latency_ms = (time.perf_counter() - started) * 1000
    check("MESSAGE CROSSED FROM NODE A TO NODE B",
          delivered is not None and delivered["payload"]["message"]["content"] == text,
          str(delivered))
    if delivered:
        print(f"         cross-node delivery latency: {latency_ms:.1f} ms")

    print("\n=== 5. CROSS-NODE RECEIPTS ===")
    message_id = ack["payload"]["message_id"]
    await bob.send("message.delivered", {
        "conversation_id": conversation["id"], "message_id": message_id
    })
    receipt = await alice.wait_for("message.delivered")
    check("delivery receipt travelled B -> A", receipt is not None and receipt["payload"]["delivered_to"] == 1, str(receipt))

    await bob.send("message.read", {
        "conversation_id": conversation["id"], "last_read_message_id": message_id
    })
    await asyncio.sleep(0.8)
    reads = [e for e in alice.of("message.read") if not e["payload"].get("self")]
    check("read receipt travelled B -> A", len(reads) > 0 and reads[-1]["payload"]["read_by"] == 1, str(reads))

    print("\n=== 6. CROSS-NODE TYPING ===")
    await alice.send("typing.start", {"conversation_id": conversation["id"]})
    typing = await bob.wait_for("typing")
    check("typing relayed A -> B", typing is not None and typing["payload"]["is_typing"] is True, str(typing))

    print("\n=== 7. CROSS-NODE GROUP FAN-OUT ===")
    token_c, user_c = await login(node_a.base, "+919999900003")
    carol = Client(node_a, token_c, user_c)
    await carol.connect()
    await asyncio.sleep(0.5)

    async with httpx.AsyncClient(timeout=10) as http:
        group = (await http.post(
            f"{node_a.base}/api/v1/conversations",
            json={"type": "group", "name": "Cross-node squad",
                  "member_ids": [user_b["id"], user_c["id"]]},
            headers={"Authorization": f"Bearer {token_a}"},
        )).json()

    group_text = f"group across nodes {uuid.uuid4().hex[:6]}"
    await alice.send("message.send", {
        "conversation_id": group["id"], "client_msg_id": str(uuid.uuid4()),
        "type": "text", "content": group_text,
    })
    await asyncio.sleep(1.2)

    on_b = [e for e in bob.of("message.new") if e["payload"]["message"].get("content") == group_text]
    on_c = [e for e in carol.of("message.new") if e["payload"]["message"].get("content") == group_text]
    check("group message reached the member on the OTHER node", len(on_b) == 1, f"count={len(on_b)}")
    check("group message reached the member on the SAME node", len(on_c) == 1, f"count={len(on_c)}")

    print("\n=== 8. NODE FAILURE ===")
    await carol.close()
    await asyncio.sleep(0.6)
    b_health = httpx.get(f"{node_b.base}/health").json()
    check("node B saw Carol disconnect from node A",
          b_health["online_users"] == 2, f"online={b_health['online_users']}")

    # SIGKILL node A: no graceful shutdown, so it never gets to publish offline
    # deltas. Node B can only notice via the heartbeat going stale, which is the
    # hard-failure detection window worth measuring.
    killed_at = time.time()
    node_a.stop(hard=True)
    reaped_after = None
    while time.time() - killed_at < 40:
        await asyncio.sleep(0.5)
        b_health = httpx.get(f"{node_b.base}/health").json()
        if b_health["online_users"] <= 1:
            reaped_after = time.time() - killed_at
            break
    if reaped_after is not None:
        print(f"         node B reaped the SIGKILLed node after {reaped_after:.1f}s")

    check("node B survives node A dying", b_health["status"] == "ok")
    check("node B drops the dead node's users from presence",
          b_health["online_users"] == 1, f"online={b_health['online_users']}")

    await bob.close()

    print("\n" + "=" * 62)
    print(f"  {len(ok)} passed, {len(fail)} failed")
    for name in fail:
        print("   -", name)
    print("=" * 62)
    return 1 if fail else 0


def main() -> int:
    db_file = BACKEND / "multinode.db"
    for suffix in ("", "-wal", "-shm"):
        Path(str(db_file) + suffix).unlink(missing_ok=True)

    import redis as redis_sync

    client = redis_sync.from_url(REDIS_URL)
    client.flushdb()

    node_a = Node(NODE_A_PORT, "node-A")
    node_b = Node(NODE_B_PORT, "node-B")
    try:
        node_a.start()
        node_a.wait_ready()      # let A create the schema before B races it
        node_b.start()
        return asyncio.run(run(node_a, node_b))
    finally:
        node_a.stop()
        node_b.stop()
        client.flushdb()
        for suffix in ("", "-wal", "-shm"):
            Path(str(db_file) + suffix).unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
