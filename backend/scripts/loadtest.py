"""WebSocket load test - real numbers instead of "should scale".

Opens N concurrent WebSocket connections, has half of them send messages to the
other half, and measures the latency that actually matters: **the time from the
sender pressing enter to the recipient's device having the message** (send ->
message.new on the peer), not just the server's own ack.

    python scripts/loadtest.py --connections 200 --messages 10
    python scripts/loadtest.py --connections 1000 --messages 5 --host http://127.0.0.1:8010

Run it against a server started WITHOUT --reload; the reloader's file watcher
distorts the numbers badly.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
import uuid

import httpx
import websockets


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int(len(ordered) * pct / 100), len(ordered) - 1)
    return ordered[index]


class Participant:
    def __init__(self, host: str, phone: str) -> None:
        self.host = host
        self.phone = phone
        self.token: str = ""
        self.user_id: str = ""
        self.ws = None
        self.conversation_id: str = ""
        # client_msg_id -> perf_counter at send, for the sender
        self.sent_at: dict[str, float] = {}
        # end-to-end latencies observed as a RECIPIENT
        self.received: list[tuple[str, float]] = []
        self.acks: list[float] = []
        self.errors = 0

    async def login(self, http: httpx.AsyncClient) -> None:
        await http.post(f"{self.host}/api/v1/auth/request-otp", json={"phone_number": self.phone})
        response = await http.post(
            f"{self.host}/api/v1/auth/verify-otp",
            json={"phone_number": self.phone, "code": "123456"},
        )
        body = response.json()
        self.token = body["access_token"]
        self.user_id = body["user"]["id"]

    async def connect(self) -> None:
        ws_host = self.host.replace("http://", "ws://").replace("https://", "wss://")
        self.ws = await websockets.connect(
            f"{ws_host}/api/v1/ws?token={self.token}",
            ping_interval=20,
            max_queue=None,
        )

    async def pump(self, registry: dict[str, float]) -> None:
        """Record arrival times. `registry` is the shared send-time table."""
        try:
            async for raw in self.ws:
                event = json.loads(raw)
                kind = event.get("type")
                if kind == "message.new":
                    client_msg_id = event["payload"]["message"].get("client_msg_id")
                    started = registry.get(client_msg_id)
                    if started is not None:
                        self.received.append((client_msg_id, (time.perf_counter() - started) * 1000))
                elif kind == "message.ack":
                    started = registry.get(event["payload"].get("client_msg_id"))
                    if started is not None:
                        self.acks.append((time.perf_counter() - started) * 1000)
                elif kind == "error":
                    self.errors += 1
        except Exception:
            pass

    async def close(self) -> None:
        if self.ws:
            await self.ws.close()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("LOAD_HOST", "http://127.0.0.1:8010"))
    parser.add_argument(
        "--hosts",
        default="",
        help="comma separated node URLs; senders and receivers are split across "
             "them so every message crosses a node boundary",
    )
    parser.add_argument("--connections", type=int, default=200, help="concurrent sockets")
    parser.add_argument("--messages", type=int, default=10, help="messages per sending pair")
    parser.add_argument("--rate", type=float, default=0.0, help="seconds between sends (0 = as fast as possible)")
    args = parser.parse_args()

    pairs = args.connections // 2
    if pairs < 1:
        print("need at least 2 connections")
        return 1

    print(f"target      : {args.host}")
    print(f"connections : {args.connections} ({pairs} sender/receiver pairs)")
    print(f"messages    : {args.messages} per pair -> {pairs * args.messages} total\n")

    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()] or [args.host]
    if len(hosts) > 1:
        print(f"nodes       : {len(hosts)} -> {', '.join(hosts)}")
        print("              senders on node 1, receivers on the rest, so every")
        print("              message must cross the Redis fan-out\n")

    stamp = uuid.uuid4().hex[:6]

    def host_for(index: int) -> str:
        """Spread the *senders* evenly across nodes, and put each one's partner
        on a different node.

        Both halves matter. Spreading senders is what actually distributes the
        work (persisting and fanning out a message is done by the sender's
        node); putting the partner elsewhere is what forces every message
        through the Redis hop. Pinning all senders to one node measures a single
        node with extra latency, not a cluster.
        """
        if len(hosts) == 1:
            return hosts[0]
        pair_index = index if index < pairs else index - pairs
        offset = 0 if index < pairs else 1
        return hosts[(pair_index + offset) % len(hosts)]

    participants = [
        Participant(host_for(index), f"+9188{stamp}{index:04d}")
        for index in range(args.connections)
    ]

    # --- sign up ------------------------------------------------------------
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=60, limits=httpx.Limits(max_connections=50)) as http:
        for chunk in range(0, len(participants), 50):
            await asyncio.gather(*(p.login(http) for p in participants[chunk : chunk + 50]))
    print(f"signed up {len(participants)} users in {time.perf_counter() - started:.1f}s")

    senders = participants[:pairs]
    receivers = participants[pairs:]

    async with httpx.AsyncClient(timeout=60, limits=httpx.Limits(max_connections=50)) as http:
        started = time.perf_counter()
        for chunk in range(0, pairs, 50):
            batch = list(zip(senders, receivers, strict=True))[chunk : chunk + 50]
            results = await asyncio.gather(*(
                http.post(
                    f"{sender.host}/api/v1/conversations",
                    json={"type": "direct", "user_id": receiver.user_id},
                    headers={"Authorization": f"Bearer {sender.token}"},
                )
                for sender, receiver in batch
            ))
            for (sender, receiver), response in zip(batch, results, strict=True):
                conversation_id = response.json()["id"]
                sender.conversation_id = conversation_id
                receiver.conversation_id = conversation_id
        print(f"created {pairs} conversations in {time.perf_counter() - started:.1f}s")

    # --- connect ------------------------------------------------------------
    registry: dict[str, float] = {}
    started = time.perf_counter()
    connect_errors = 0
    for chunk in range(0, len(participants), 100):
        batch = participants[chunk : chunk + 100]
        results = await asyncio.gather(*(p.connect() for p in batch), return_exceptions=True)
        connect_errors += sum(1 for r in results if isinstance(r, Exception))
    connect_seconds = time.perf_counter() - started
    live = [p for p in participants if p.ws is not None and p.ws.state.name == "OPEN"]
    print(f"opened {len(live)}/{args.connections} sockets in {connect_seconds:.1f}s "
          f"({connect_errors} failed)")

    pumps = [asyncio.create_task(p.pump(registry)) for p in participants]
    await asyncio.sleep(1.0)

    for host in hosts:
        health = httpx.get(f"{host}/health", timeout=10).json()
        print(f"{host:28s} {health['live_sockets']:4d} sockets held, "
              f"{health['online_users']:4d} online cluster-wide "
              f"({health['fanout']}, {health['database']})")
    print()

    # --- send ---------------------------------------------------------------
    async def drive(sender: Participant) -> None:
        for _ in range(args.messages):
            client_msg_id = str(uuid.uuid4())
            registry[client_msg_id] = time.perf_counter()
            try:
                await sender.ws.send(json.dumps({
                    "type": "message.send",
                    "id": str(uuid.uuid4()),
                    "payload": {
                        "conversation_id": sender.conversation_id,
                        "client_msg_id": client_msg_id,
                        "type": "text",
                        "content": "load test payload",
                    },
                }))
            except Exception:
                sender.errors += 1
            if args.rate:
                await asyncio.sleep(args.rate)

    expected = pairs * args.messages
    started = time.perf_counter()
    await asyncio.gather(*(drive(sender) for sender in senders))
    send_seconds = time.perf_counter() - started

    # Drain: wait until deliveries stop arriving.
    previous = -1
    for _ in range(120):
        await asyncio.sleep(0.5)
        total = sum(len(p.received) for p in receivers)
        if total >= expected or total == previous:
            break
        previous = total
    elapsed = time.perf_counter() - started

    latencies = [ms for p in receivers for _, ms in p.received]
    acks = [ms for p in senders for ms in p.acks]
    delivered = len(latencies)
    errors = sum(p.errors for p in participants)

    for task in pumps:
        task.cancel()
    await asyncio.gather(*(p.close() for p in participants), return_exceptions=True)

    # --- report -------------------------------------------------------------
    print("=" * 60)
    print("  RESULTS")
    print("=" * 60)
    print(f"  concurrent sockets      {len(live)}")
    print(f"  socket open rate        {len(live) / connect_seconds:,.0f} /s")
    print(f"  messages sent           {expected}")
    print(f"  messages delivered      {delivered}  ({delivered / expected * 100:.1f}%)")
    print(f"  send burst duration     {send_seconds:.2f}s")
    print(f"  throughput (delivered)  {delivered / elapsed:,.0f} msg/s")
    print(f"  rate-limit rejections   {errors}")
    if acks:
        print(f"\n  server ack (send -> persisted + acked)")
        print(f"    p50 {percentile(acks, 50):7.1f} ms    p95 {percentile(acks, 95):7.1f} ms"
              f"    p99 {percentile(acks, 99):7.1f} ms")
    if latencies:
        print(f"\n  END-TO-END (sender enter -> recipient's device)")
        print(f"    min {min(latencies):7.1f} ms    mean {statistics.mean(latencies):7.1f} ms")
        print(f"    p50 {percentile(latencies, 50):7.1f} ms    p95 {percentile(latencies, 95):7.1f} ms"
              f"    p99 {percentile(latencies, 99):7.1f} ms    max {max(latencies):7.1f} ms")
    print("=" * 60)
    return 0 if delivered >= expected * 0.99 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
