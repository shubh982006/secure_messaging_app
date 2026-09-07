# API Contract — Signal Clone

Base URL: `/api/v1` · Content type: `application/json` · Auth: `Authorization: Bearer <access_token>`

Interactive OpenAPI docs are served at `/docs`. This document describes the API **as built**.

---

## Conventions

**Timestamps** — ISO-8601 UTC (`2026-09-07T10:15:30Z`).

**IDs** — UUIDv4 strings.

**Pagination** — cursor-based, never offset.

- Messages: `?before=<seq>` walks backwards (infinite scroll), `?after=<seq>` walks forwards
  (reconnect backfill). Responses carry `next_cursor` (`"seq:12"`, or `null` when exhausted).
- Conversations: `?before=<opaque cursor>` from the previous response's `next_cursor`.

**Error shape** (every non-2xx):

```json
{ "error": { "code": "CONVERSATION_NOT_FOUND", "message": "Human readable", "detail": {} } }
```

**Standard codes**

| HTTP | code | when |
|---|---|---|
| 400 | `VALIDATION_ERROR` | bad or missing fields, empty/oversized message |
| 400 | `OTP_INVALID` / `OTP_EXPIRED` / `OTP_NOT_REQUESTED` | OTP verification failures |
| 401 | `UNAUTHENTICATED` | missing, invalid, expired or revoked token |
| 403 | `FORBIDDEN` | not an admin, or deleting someone else's message |
| 404 | `*_NOT_FOUND` | resource missing — **also returned when you are not a member**, so ids cannot be probed |
| 400 | `FILE_TOO_LARGE` | upload exceeds the size cap |
| 409 | `CONFLICT` / `USERNAME_TAKEN` | duplicate contact, member already present, username in use |
| 422 | `UNPROCESSABLE` / `UNSUPPORTED_MEDIA_TYPE` | semantically impossible, or a disallowed file type |
| 429 | `RATE_LIMITED` | send flood |

---

## 1. Auth / onboarding (OTP mocked — fixed code `123456`)

### `POST /auth/request-otp`

```json
// req
{ "phone_number": "+919999900001" }
// 200
{ "request_id": "uuid", "mocked_code": "123456", "expires_in": 300 }
```

`mocked_code` is returned on purpose: verification is mocked, so the UI prefills it rather than
waiting for an SMS that never arrives. Phone numbers are normalised (spaces stripped, `+` enforced).

### `POST /auth/verify-otp`

Verifies the most recent unconsumed challenge, then issues tokens. Creates the user on first verify.

```json
// req
{ "phone_number": "+919999900001", "code": "123456" }
// 200
{
  "access_token": "jwt", "refresh_token": "jwt", "token_type": "bearer",
  "is_new_user": true,
  "user": { "id": "uuid", "phone_number": "+919999900001", "display_name": null, "avatar_url": null, "about": null, "is_online": false, "last_seen_at": "...", "created_at": "..." }
}
```

### `POST /auth/refresh`

```json
{ "refresh_token": "jwt" }
// 200 -> { "access_token": "jwt", "refresh_token": "jwt", "token_type": "bearer" }
```

**Rotation:** the presented refresh token is revoked as the new pair is issued. Reusing it returns
`401 UNAUTHENTICATED`.

### `POST /auth/logout`

`{ "refresh_token": "jwt" }` → `204`. Revokes that session. Omitting the token revokes **all** of
the caller's sessions.

### `GET /auth/me` → `200` full private user object (same as `GET /users/me`).

---

## 2. Users & contacts

### `PATCH /users/me` — complete or edit the profile

```json
// req (all fields optional)
{ "display_name": "Alice", "avatar_url": "https://.../a.png", "about": "on Signal", "username": "alice" }
// 200 -> full private user object   | 409 USERNAME_TAKEN
```

### `GET /users/search?q=<term>`

Matches display name, username or phone number, excluding the caller. **An empty `q` returns the
people you already share a conversation with** — which is what Signal's "New chat" sheet shows
before you type.

```json
{ "results": [ { "id": "uuid", "display_name": "Bob", "username": "bob", "avatar_url": null, "about": "…", "is_online": true, "last_seen_at": "…" } ] }
```

### `GET /users/{user_id}` → `200` public user object.

### `GET /contacts`

```json
{ "contacts": [ { "id": "uuid", "user": { "...public user..." }, "nickname": "Bobby", "created_at": "…" } ] }
```

### `POST /contacts`

```json
{ "phone_number": "+919999900002" }   // or { "username": "bob" } or { "user_id": "uuid" }
// 201 -> contact object   | 409 CONFLICT if already a contact
```

### `DELETE /contacts/{contact_id}` → `204`

---

## 3. Conversations

### `GET /conversations?before=<cursor>&limit=30`

The Signal main list — sorted by `updated_at` desc, with denormalised preview and unread count.
Served in **three queries regardless of page size**.

```json
{
  "conversations": [
    {
      "id": "uuid",
      "type": "direct",
      "name": "Bob Martinez",
      "avatar_url": null,
      "members_count": 2,
      "last_message": {
        "id": "uuid", "sender_id": "uuid", "sender_name": "Bob Martinez",
        "type": "text", "preview": "See you at 6", "seq": 42,
        "created_at": "…", "status": "read", "deleted": false
      },
      "unread_count": 0,
      "is_online": true,
      "last_seen_at": "2026-09-07T10:00:00Z",
      "muted": false,
      "my_role": "member",
      "peer": { "...public user, direct conversations only..." },
      "last_seq": 42,
      "my_last_read_seq": 42,
      "disappear_seconds": 0,
      "created_at": "…",
      "updated_at": "…"
    }
  ],
  "next_cursor": null
}
```

`name` and `avatar_url` resolve to the peer for a direct conversation and to the group's own name
and avatar for a group. `unread_count` is `last_seq - my_last_read_seq`.

### `POST /conversations` — start a DM (idempotent) or create a group

```json
// direct — get-or-create via dm_key; calling it from either side returns the same conversation
{ "type": "direct", "user_id": "uuid-of-peer" }
// group
{ "type": "group", "name": "Weekend Trip", "member_ids": ["uuid", "uuid"], "avatar_url": null }
// 201 -> conversation detail (with members[])
```

Creating a group emits a `system` message ("Alice created the group") and pushes
`conversation.new` to every member.

### `GET /conversations/{id}` — detail including `members[]`

```json
{
  "...all conversation fields...",
  "members": [
    { "user_id": "uuid", "display_name": "Bob", "username": "bob", "avatar_url": null,
      "about": "…", "role": "admin", "last_read_seq": 42, "last_delivered_seq": 42,
      "is_online": true, "last_seen_at": "…", "joined_at": "…" }
  ]
}
```

### `PATCH /conversations/{id}`

```json
{ "name": "New name", "avatar_url": "…", "muted": true, "disappear_seconds": 86400 }
```

`name` / `avatar_url` are **group admin only** (403 otherwise) and emit a system message plus
`conversation.updated`. `muted` is a **per-member preference** and is not admin-gated.

`disappear_seconds` sets the disappearing-message retention window (0 turns it off, max 4 weeks).
Any member may change it, and the change posts a system message into the thread. It applies to
**new messages only** — existing messages are never retroactively expired.

### `POST /conversations/{id}/members` — admin only

```json
{ "user_ids": ["uuid", "uuid"] }
// 200 -> conversation detail; emits member.added + a system message + conversation.updated
```

Joining members' high-water marks start at the group's current `last_seq`, so they do not inherit
the whole backlog as unread.

### `DELETE /conversations/{id}/members/{user_id}`

Admin removes a member, or a member removes themselves (leave). → `204`; emits `member.removed`, a
system message, and `conversation.updated`. If the last admin leaves, admin is reassigned so a group
is never left ownerless.

### `DELETE /conversations/{id}` — leave a group (equivalent to removing yourself) → `204`

### `POST /conversations/{id}/read` — advance the read high-water mark

```json
{ "last_read_message_id": "uuid" }   // or { "last_read_seq": 42 }, or {} for "everything"
// 200 -> { "unread_count": 0, "last_read_seq": 42 }
```

Emits `message.read` to the other members. One UPDATE regardless of how many messages are covered.

---

## 4. Messages

### `GET /conversations/{id}/messages?before=<seq>&after=<seq>&limit=50`

Returns messages in **ascending `seq`** (the client renders top to bottom). `before` walks backwards
for infinite scroll; `after` walks forwards to backfill a reconnect.

```json
{
  "messages": [
    {
      "id": "uuid", "conversation_id": "uuid", "sender_id": "uuid", "seq": 42,
      "type": "text", "content": "See you at 6", "client_msg_id": "uuid",
      "reply_to": { "id": "uuid", "sender_id": "uuid", "sender_name": "Bob", "preview": "what time?", "type": "text" },
      "reactions": [ { "emoji": "👍", "user_id": "uuid" } ],
      "attachments": [],
      "created_at": "…", "edited_at": null, "deleted_at": null, "expires_at": null,
      "delivered_to": 1, "read_by": 1, "recipients": 1,
      "status": "read"
    }
  ],
  "next_cursor": "seq:12"
}
```

`recipients` is the member count excluding the sender. `status` is `read` when
`read_by >= recipients`, `delivered` when `delivered_to >= recipients`, otherwise `sent` — so in a
group the tick only advances once **everyone** has reached that state. A deleted message returns
`content: null`, `deleted_at` set, and no reactions or attachments.

### `POST /conversations/{id}/messages` — REST fallback (primary path is WS `message.send`)

```json
// req
{
  "type": "text",                       // text | image | file
  "content": "hello",
  "client_msg_id": "uuid",
  "reply_to_id": null,
  "attachments": [                      // optional, from POST /attachments
    { "url": "/media/ab12….png", "name": "photo.png", "mime_type": "image/png",
      "size_bytes": 51234, "width": 1200, "height": 800 }
  ]
}
// 201 -> created message object; idempotent on client_msg_id
```

A message needs either `content` or at least one attachment. When the window is on, the response
carries a non-null `expires_at`.

Shares the same service call as the WebSocket path, so it also fans out over WS to online members.

### `DELETE /messages/{id}` — soft delete, sender only → `204`; emits `message.deleted`

### `POST /messages/{id}/reactions` — `{ "emoji": "👍" }` → `200` updated message

### `DELETE /messages/{id}/reactions/{emoji}` → `200` updated message

Both emit `message.reaction` with the full reaction set to every member.

### `POST /attachments` — upload one file (multipart/form-data)

| field | type | notes |
|---|---|---|
| `file` | file | required |
| `width` | int | optional; the browser's measured natural width |
| `height` | int | optional |

```json
// 201
{
  "url": "/media/9f2c…c1.png",
  "name": "photo.png",
  "mime_type": "image/png",
  "size_bytes": 51234,
  "width": 1200,
  "height": 800,
  "kind": "image"          // image | file
}
```

Upload first, then reference the returned metadata in `message.send` — that keeps the hot message
path pure JSON. `url` is relative to the API host and is served from `/media`.

Limits: 10 MB per file (`FILE_TOO_LARGE`), and a MIME **allowlist** covering common image, document,
audio and video types (`UNSUPPORTED_MEDIA_TYPE` otherwise). The stored filename is a random UUID —
the client's filename is kept only as display metadata.

---

## 5. WebSocket protocol

**Connect:** `GET /api/v1/ws?token=<access_token>`

The token travels as a query parameter because the browser WebSocket API cannot set headers. An
invalid token is accepted then closed with code **4401** so the client sees a real close code rather
than a generic handshake failure.

**Envelope (both directions):**

```json
{ "type": "message.send", "id": "client-event-uuid", "ts": "2026-09-07T10:15:30Z", "payload": { } }
```

`id` lets the client correlate an inbound `message.ack` with the exact event it sent.

### Client → server

| type | payload | effect |
|---|---|---|
| `message.send` | `{ conversation_id, client_msg_id, type, content, reply_to_id?, attachments? }` | persist + fan out; server replies `message.ack` |
| `message.read` | `{ conversation_id, last_read_message_id? , last_read_seq? }` | advance read high-water mark; notify members |
| `message.delivered` | `{ conversation_id, message_id }` | advance delivered mark; notify the sender |
| `typing.start` / `typing.stop` | `{ conversation_id }` | ephemeral relay, never persisted |
| `presence.ping` | `{}` | heartbeat; replies `presence.pong` |

### Server → client

| type | payload |
|---|---|
| `connected` | `{ user_id, online_user_ids }` — sent once on connect so presence renders immediately |
| `message.ack` | `{ client_msg_id, message_id, conversation_id, seq, created_at, status: "sent" }` |
| `message.new` | `{ message }` (full object as in §4) — sent to **all** members including the sender's other devices |
| `message.delivered` | `{ conversation_id, message_id, user_id, last_delivered_seq, delivered_to }` |
| `message.read` | `{ conversation_id, user_id, last_read_seq, read_by }` — the sender's own echo also carries `unread_count` and `self: true` |
| `message.deleted` | `{ conversation_id, message_id }` |
| `message.expired` | `{ conversation_id, message_ids[] }` — disappearing messages that just lapsed |
| `message.reaction` | `{ conversation_id, message_id, reactions[] }` |
| `typing` | `{ conversation_id, user_id, is_typing }` |
| `presence.update` | `{ user_id, is_online, last_seen_at }` |
| `conversation.new` | `{ conversation }` — a DM or group you were just added to |
| `conversation.updated` | `{ conversation }` — rename, avatar or membership change, rendered per viewer |
| `member.added` | `{ conversation_id, user_ids, by_user_id }` |
| `member.removed` | `{ conversation_id, user_id, by_user_id }` — also delivered to the removed user |
| `presence.pong` | `{}` |
| `error` | `{ code, message }` — a failed event never closes the socket |

### Example send round-trip

```
C→S  { "type":"message.send", "id":"e1",
       "payload":{ "conversation_id":"c1","client_msg_id":"m9","type":"text","content":"hi" } }
S→C  { "type":"message.ack",  "payload":{ "client_msg_id":"m9","message_id":"srv1","seq":43,"status":"sent" } }          // ✓
S→C  { "type":"message.delivered", "payload":{ "conversation_id":"c1","message_id":"srv1","user_id":"u2","last_delivered_seq":43,"delivered_to":1 } }  // ✓✓
S→C  { "type":"message.read", "payload":{ "conversation_id":"c1","user_id":"u2","last_read_seq":43,"read_by":1 } }       // ✓✓ read
```

### Reconnect / offline sync

On reconnect the client does **not** rely on replaying missed socket events. It refetches the
conversation list and calls `GET /conversations/{id}/messages?after=<last_seen_seq>` to backfill,
then resumes the live socket. The database is the source of truth; the socket is the fast path.

The client reconnects with exponential backoff capped at 20s, with jitter so a restarted server does
not receive every client back at the same instant. Messages sent while the socket is down are queued
(up to 50) and also retried over REST with the same `client_msg_id`, so nothing is lost or
duplicated.

---

## 6. Rate limiting & validation

- `message.send`: 20 messages / 10s / user (configurable). Exceeding it returns an `error` event
  with code `RATE_LIMITED` over WS, or `429` over REST. Enforced per process; a Redis token bucket
  is the multi-node replacement.
- `content` is capped at 8 KB and must be non-empty after trimming; types are checked by Pydantic
  before any DB write.
- Every conversation and message route verifies membership before returning or mutating data.
