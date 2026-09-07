"""End-to-end verification against a *running* backend.

Exercises the full stack the way the browser does - REST + live WebSockets,
three concurrent users, receipts, groups, presence, rate limiting.

    # terminal 1
    uvicorn app.main:app --port 8010
    # terminal 2
    python scripts/e2e_check.py

Point it at a deployed instance with E2E_HOST=https://your-api.example.com
"""
import asyncio
import json
import os
import sys
import uuid

import httpx
import websockets

HOST = os.environ.get("E2E_HOST", "http://127.0.0.1:8010")
BASE = f"{HOST}/api/v1"
WS = BASE.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
ok, fail = [], []

def check(name, cond, extra=""):
    (ok if cond else fail).append(name)
    print(("  PASS  " if cond else "  FAIL  ") + name + (f"   {extra}" if extra and not cond else ""))

async def login(client, phone):
    r = await client.post(f"{BASE}/auth/request-otp", json={"phone_number": phone})
    r.raise_for_status()
    code = r.json()["mocked_code"]
    r = await client.post(f"{BASE}/auth/verify-otp", json={"phone_number": phone, "code": code})
    r.raise_for_status()
    return r.json()

class Client:
    def __init__(self, data):
        self.token = data["access_token"]
        self.refresh = data["refresh_token"]
        self.user = data["user"]
        self.ws = None
        self.events = []
    @property
    def h(self): return {"Authorization": f"Bearer {self.token}"}
    async def connect(self):
        self.ws = await websockets.connect(f"{WS}?token={self.token}")
        self._task = asyncio.create_task(self._pump())
        await asyncio.sleep(0.15)
    async def _pump(self):
        try:
            async for raw in self.ws:
                self.events.append(json.loads(raw))
        except Exception:
            pass
    async def send(self, type_, payload, eid=None):
        await self.ws.send(json.dumps({"type": type_, "id": eid or str(uuid.uuid4()), "payload": payload}))
    def of(self, t): return [e for e in self.events if e["type"] == t]
    async def wait_for(self, t, timeout=3.0):
        for _ in range(int(timeout / 0.05)):
            got = self.of(t)
            if got: return got[-1]
            await asyncio.sleep(0.05)
        return None
    async def close(self):
        if self.ws: await self.ws.close()

async def main():
    async with httpx.AsyncClient(timeout=10) as http:
        print("\n=== 1. AUTH ===")
        a = Client(await login(http, "+919999900001"))
        b = Client(await login(http, "+919999900002"))
        c = Client(await login(http, "+919999900003"))
        check("verify-otp issues tokens for seeded users", bool(a.token and b.token))
        check("seeded profile is intact", a.user["display_name"] == "Alice Chen", a.user)

        r = await http.get(f"{BASE}/auth/me", headers=a.h)
        check("GET /auth/me returns the caller", r.json()["id"] == a.user["id"])

        r = await http.get(f"{BASE}/auth/me")
        check("missing token -> 401 UNAUTHENTICATED",
              r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED", r.text)

        r = await http.post(f"{BASE}/auth/refresh", json={"refresh_token": a.refresh})
        check("refresh rotates the token pair", r.status_code == 200 and r.json()["access_token"] != a.token)
        old_refresh = a.refresh
        a.refresh = r.json()["refresh_token"]
        r = await http.post(f"{BASE}/auth/refresh", json={"refresh_token": old_refresh})
        check("used refresh token is revoked", r.status_code == 401, r.text)

        await http.post(f"{BASE}/auth/request-otp", json={"phone_number": "+919999900001"})
        r = await http.post(f"{BASE}/auth/verify-otp", json={"phone_number": "+919999900001", "code": "000000"})
        check("wrong OTP rejected", r.status_code == 400 and r.json()["error"]["code"] == "OTP_INVALID", r.text)
        r = await http.post(f"{BASE}/auth/verify-otp", json={"phone_number": "+919999900009", "code": "123456"})
        check("verify without requesting a code is rejected",
              r.status_code == 400 and r.json()["error"]["code"] == "OTP_NOT_REQUESTED", r.text)

        print("\n=== 2. CONVERSATION LIST (seed) ===")
        r = await http.get(f"{BASE}/conversations", headers=a.h)
        convs = r.json()["conversations"]
        check("Alice has seeded conversations", len(convs) >= 4, len(convs))
        ts = [c["updated_at"] for c in convs]
        check("list sorted by recency desc", ts == sorted(ts, reverse=True))
        check("previews present", all(c["last_message"] for c in convs))
        check("unread badge computed", any(c["unread_count"] > 0 for c in convs),
              [(c["name"], c["unread_count"]) for c in convs])
        dm = next(c for c in convs if c["type"] == "direct" and c["name"] == "Bob Martinez")
        check("direct conversation names resolve to the peer", dm["name"] == "Bob Martinez")
        check("group conversations present", any(c["type"] == "group" for c in convs))

        r = await http.get(f"{BASE}/conversations/{dm['id']}/messages?limit=5", headers=a.h)
        page = r.json()
        seqs = [m["seq"] for m in page["messages"]]
        check("history returns ascending seq", seqs == sorted(seqs), seqs)
        check("history paginates with a cursor", page["next_cursor"] is not None, page["next_cursor"])
        r2 = await http.get(f"{BASE}/conversations/{dm['id']}/messages?limit=5&before={seqs[0]}", headers=a.h)
        check("before cursor walks backwards", all(m["seq"] < seqs[0] for m in r2.json()["messages"]))

        print("\n=== 3. REALTIME 1:1 ===")
        await a.connect(); await b.connect(); await c.connect()
        check("ws handshake accepted", (await a.wait_for("connected")) is not None)
        pres = await b.wait_for("presence.update")
        check("presence broadcast on connect", pres is not None and pres["payload"]["is_online"] is True, pres)

        cmid = str(uuid.uuid4())
        await a.send("message.send", {"conversation_id": dm["id"], "client_msg_id": cmid, "type": "text", "content": "Hello from the e2e test"})
        ack = await a.wait_for("message.ack")
        check("sender receives message.ack", ack is not None and ack["payload"]["client_msg_id"] == cmid, ack)
        check("ack carries a seq", ack and isinstance(ack["payload"]["seq"], int))
        check("ack status is 'sent' (single tick)", ack and ack["payload"]["status"] == "sent", ack)

        new = await b.wait_for("message.new")
        check("recipient receives message.new live", new is not None and new["payload"]["message"]["content"] == "Hello from the e2e test", new)
        msg_id = ack["payload"]["message_id"]
        check("recipient message id matches ack", new["payload"]["message"]["id"] == msg_id)

        # idempotent retry
        await a.send("message.send", {"conversation_id": dm["id"], "client_msg_id": cmid, "type": "text", "content": "Hello from the e2e test"})
        await asyncio.sleep(0.4)
        acks = [e for e in a.of("message.ack") if e["payload"]["client_msg_id"] == cmid]
        check("retry is idempotent (same message id)", len({x["payload"]["message_id"] for x in acks}) == 1, acks)

        print("\n=== 4. RECEIPTS ===")
        await b.send("message.delivered", {"conversation_id": dm["id"], "message_id": msg_id})
        d = await a.wait_for("message.delivered")
        check("sender notified of delivery (double tick)", d is not None and d["payload"]["delivered_to"] == 1, d)

        await b.send("message.read", {"conversation_id": dm["id"], "last_read_message_id": msg_id})
        rd = [e for e in (await asyncio.sleep(0.5), a.of("message.read"))[1]]
        check("sender notified of read (blue tick)", len(rd) > 0 and rd[-1]["payload"]["read_by"] == 1, rd)

        r = await http.get(f"{BASE}/conversations/{dm['id']}/messages?limit=3", headers=a.h)
        last = r.json()["messages"][-1]
        check("message status is 'read' after receipt", last["status"] == "read", last["status"])
        check("read_by counter exposed", last["read_by"] == 1, last)

        r = await http.get(f"{BASE}/conversations", headers=b.h)
        bconv = next(x for x in r.json()["conversations"] if x["id"] == dm["id"])
        check("unread clears after read", bconv["unread_count"] == 0, bconv["unread_count"])

        print("\n=== 5. TYPING ===")
        await a.send("typing.start", {"conversation_id": dm["id"]})
        t = await b.wait_for("typing")
        check("typing relayed to peer", t is not None and t["payload"]["is_typing"] is True, t)
        check("typing not relayed to self", len(a.of("typing")) == 0)
        await a.send("typing.stop", {"conversation_id": dm["id"]})
        await asyncio.sleep(0.3)
        check("typing.stop relayed", b.of("typing")[-1]["payload"]["is_typing"] is False)

        print("\n=== 6. GROUPS ===")
        r = await http.post(f"{BASE}/conversations", headers=a.h, json={
            "type": "group", "name": "E2E Squad", "member_ids": [b.user["id"], c.user["id"]]})
        check("group created", r.status_code == 201, r.text)
        g = r.json()
        check("creator is admin", g["my_role"] == "admin", g["my_role"])
        check("group has 3 members", g["members_count"] == 3, g["members_count"])
        gnew = await b.wait_for("conversation.new")
        check("members told about the new group live", gnew is not None, gnew)

        await a.send("message.send", {"conversation_id": g["id"], "client_msg_id": str(uuid.uuid4()), "type": "text", "content": "group ping"})
        await asyncio.sleep(0.4)
        gb = [e for e in b.of("message.new") if e["payload"]["message"]["conversation_id"] == g["id"]]
        gc = [e for e in c.of("message.new") if e["payload"]["message"]["conversation_id"] == g["id"]]
        check("group message fans out to all members", len(gb) >= 1 and len(gc) >= 1, (len(gb), len(gc)))

        gmsg = gb[-1]["payload"]["message"]
        await b.send("message.read", {"conversation_id": g["id"], "last_read_message_id": gmsg["id"]})
        await asyncio.sleep(0.35)
        r = await http.get(f"{BASE}/conversations/{g['id']}/messages", headers=a.h)
        gm = [m for m in r.json()["messages"] if m["id"] == gmsg["id"]][0]
        check("group receipt counts are partial (1 of 2 read)", gm["read_by"] == 1 and gm["recipients"] == 2, gm)
        check("status stays 'sent' until everyone reads", gm["status"] != "read", gm["status"])

        # admin add / remove
        d_user = (await http.get(f"{BASE}/users/search?q=dave", headers=a.h)).json()["results"][0]
        r = await http.post(f"{BASE}/conversations/{g['id']}/members", headers=a.h, json={"user_ids": [d_user["id"]]})
        check("admin can add members", r.status_code == 200 and r.json()["members_count"] == 4, r.text[:200])
        sysm = [e for e in b.of("message.new")
                if e["payload"]["message"]["conversation_id"] == g["id"] and e["payload"]["message"]["type"] == "system"]
        check("member.added emits a system message", len(sysm) >= 1, sysm)
        check("system message text reads naturally", sysm[-1]["payload"]["message"]["content"] == "Alice Chen added Dave Okafor", sysm[-1]["payload"]["message"]["content"])

        r = await http.post(f"{BASE}/conversations/{g['id']}/members", headers=b.h, json={"user_ids": [d_user["id"]]})
        check("non-admin cannot add members -> 403", r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN", r.text)

        r = await http.delete(f"{BASE}/conversations/{g['id']}/members/{d_user['id']}", headers=a.h)
        check("admin can remove a member", r.status_code == 204, r.text)
        rm = await b.wait_for("member.removed")
        check("member.removed event emitted", rm is not None, rm)

        r = await http.delete(f"{BASE}/conversations/{g['id']}", headers=c.h)
        check("member can leave a group", r.status_code == 204, r.text)
        r = await http.get(f"{BASE}/conversations/{g['id']}", headers=c.h)
        check("left group is no longer readable", r.status_code == 404, r.status_code)

        print("\n=== 7. DM GET-OR-CREATE + AUTHZ ===")
        r1 = await http.post(f"{BASE}/conversations", headers=a.h, json={"type": "direct", "user_id": c.user["id"]})
        r2 = await http.post(f"{BASE}/conversations", headers=c.h, json={"type": "direct", "user_id": a.user["id"]})
        check("direct conversation is idempotent both ways", r1.json()["id"] == r2.json()["id"], (r1.json()["id"], r2.json()["id"]))

        r = await http.get(f"{BASE}/conversations/{dm['id']}", headers=c.h)
        check("non-member cannot read a conversation -> 404", r.status_code == 404, r.status_code)
        r = await http.post(f"{BASE}/conversations/{dm['id']}/messages", headers=c.h,
                            json={"type": "text", "content": "sneaky", "client_msg_id": str(uuid.uuid4())})
        check("non-member cannot post -> 404", r.status_code == 404, r.status_code)

        print("\n=== 8. REST FALLBACK, REACTIONS, DELETE ===")
        r = await http.post(f"{BASE}/conversations/{dm['id']}/messages", headers=a.h,
                            json={"type": "text", "content": "via REST", "client_msg_id": str(uuid.uuid4())})
        check("REST send works", r.status_code == 201, r.text[:200])
        rest_msg = r.json()
        rn = [e for e in b.of("message.new") if e["payload"]["message"]["id"] == rest_msg["id"]]
        check("REST send also fans out over WS", len(rn) == 1, len(rn))

        r = await http.post(f"{BASE}/messages/{rest_msg['id']}/reactions", headers=b.h, json={"emoji": "👍"})
        check("reaction added", r.status_code == 200 and r.json()["reactions"][0]["emoji"] == "👍", r.text[:200])
        react = await a.wait_for("message.reaction")
        check("reaction broadcast", react is not None, react)

        r = await http.delete(f"{BASE}/messages/{rest_msg['id']}", headers=b.h)
        check("cannot delete someone else's message -> 403", r.status_code == 403, r.status_code)
        r = await http.delete(f"{BASE}/messages/{rest_msg['id']}", headers=a.h)
        check("sender can soft-delete", r.status_code == 204, r.text)
        dele = await b.wait_for("message.deleted")
        check("message.deleted broadcast", dele is not None, dele)
        r = await http.get(f"{BASE}/conversations/{dm['id']}/messages?limit=5", headers=a.h)
        tomb = [m for m in r.json()["messages"] if m["id"] == rest_msg["id"]][0]
        check("soft delete leaves a tombstone", tomb["deleted_at"] is not None and tomb["content"] is None, tomb)

        print("\n=== 9. VALIDATION / LIMITS ===")
        r = await http.post(f"{BASE}/conversations/{dm['id']}/messages", headers=a.h, json={"type": "text", "content": "   "})
        check("empty message rejected", r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR", r.text[:200])
        r = await http.post(f"{BASE}/conversations/{dm['id']}/messages", headers=a.h, json={"type": "text", "content": "x" * 9000})
        check("oversized message rejected", r.status_code == 400, r.status_code)

        before_acks = len(a.of("message.ack"))
        for i in range(30):
            await a.send("message.send", {"conversation_id": dm["id"], "client_msg_id": str(uuid.uuid4()), "type": "text", "content": f"flood {i}"})
        await asyncio.sleep(6)
        errs = [e for e in a.of("error") if e["payload"]["code"] == "RATE_LIMITED"]
        accepted = len(a.of("message.ack")) - before_acks
        check("send flood is rate limited", len(errs) > 0, len(errs))
        check("rate limiter caps the window at 20", accepted <= 20, accepted)

        print("\n=== 10. RECONNECT BACKFILL + PRESENCE OFFLINE ===")
        r = await http.get(f"{BASE}/conversations/{dm['id']}/messages?after=1&limit=100", headers=b.h)
        after = r.json()["messages"]
        check("after= backfills forwards", all(m["seq"] > 1 for m in after) and len(after) > 1, len(after))

        await a.close()
        await asyncio.sleep(0.5)
        offline = [e for e in b.of("presence.update") if e["payload"]["is_online"] is False]
        check("presence offline on disconnect", len(offline) > 0, offline)
        check("last_seen_at stamped", bool(offline and offline[-1]["payload"]["last_seen_at"]), offline[-1] if offline else None)

        r = await httpx.AsyncClient().get("http://127.0.0.1:8010/health")
        check("health reports live sockets", r.json()["live_sockets"] >= 2, r.json())

        await b.close(); await c.close()

    print("\n" + "=" * 62)
    print(f"  {len(ok)} passed, {len(fail)} failed")
    if fail:
        print("  FAILURES:")
        for f in fail: print("   -", f)
    print("=" * 62)
    return 1 if fail else 0

sys.exit(asyncio.run(main()))
