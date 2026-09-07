# Signal Clone

A working, real-time Signal clone: mocked OTP auth, 1:1 and group messaging over WebSockets,
delivery/read receipts, typing indicators, presence, and a UI built to match Signal Desktop.

**Companion docs:** [`SYSTEM_DESIGN.md`](./SYSTEM_DESIGN.md) · [`API_CONTRACT.md`](./API_CONTRACT.md)

---

## Table of contents

- [Quick start](#quick-start)
- [Demo logins](#demo-logins)
- [What is implemented](#what-is-implemented)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Database schema](#database-schema)
- [API overview](#api-overview)
- [The four decisions that matter](#the-four-decisions-that-matter)
- [Bonus features](#bonus-features)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Testing](#testing)
- [Deployment](#deployment)
- [Assumptions and known limits](#assumptions-and-known-limits)

---

## Quick start

### Option A — Docker (one command)

```bash
docker compose up --build
# web  -> http://localhost:3000
# api  -> http://localhost:8000/docs
```

### Option B — run the two apps directly

**Backend** (Python 3.11+):

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # every value already has a working default
uvicorn app.main:app --reload --port 8000
```

On first boot the app runs `alembic upgrade head` and seeds demo users, conversations
and message history, so the API is usable immediately. `GET /health` should return `{"status":"ok"}`.

**Frontend** (Node 18.18+):

```bash
cd frontend
npm install
cp .env.example .env.local           # defaults to http://localhost:8000
npm run dev                          # http://localhost:3000
```

> If `npm run dev` renders the page but nothing is clickable, the dev server's HMR socket is
> being blocked by your environment. `npm run build && npm start` behaves identically and is
> unaffected.

---

## Demo logins

Any of the seeded numbers below, with the **fixed OTP `123456`**. The login screen also has
one-tap buttons for each of them.

| Name | Phone number |
|---|---|
| Alice Chen | `+919999900001` |
| Bob Martinez | `+919999900002` |
| Carol Nair | `+919999900003` |
| Dave Okafor | `+919999900004` |
| Erin Walsh | `+919999900005` |

Any *unseeded* number also works — it creates a new account and walks you through profile setup.

**To see the real-time behaviour:** open two browsers (or one normal + one incognito), sign in as
Alice in one and Bob in the other, and put them side by side.

---

## What is implemented

| Requirement | Status | Where |
|---|---|---|
| Mocked OTP auth, fixed code `123456` | Done | `app/services/auth_service.py` |
| JWT access + refresh, rotation, revocation on logout | Done | `app/core/security.py` |
| Session persists across refresh | Done | `lib/api.ts` (token store + silent refresh) |
| Profile: display name, avatar, about | Done | `PATCH /users/me`, `ProfileModal` |
| Conversation list: recency sort, unread badge, preview, presence | Done | `conversation_service.list_conversations` |
| 1:1 real-time messaging | Done | WS `message.send` → persist → fan-out |
| Message status ✓ / ✓✓ / ✓✓ read | Done | high-water marks, see below |
| Typing indicators (ephemeral) | Done | WS `typing.start` / `typing.stop` |
| Groups: create, send, view members, add/remove (admin) | Done | `conversation_service` |
| Persistence + seed data | Done | SQLite + `app/seed.py` |
| Signal UI: list + pane, bubbles, modals, toasts, search | Done | `frontend/components` |
| Presence / last seen | Done | `presence_service` |
| Conversation + in-thread search | Done | `ConversationList`, `ChatPane` |
| Placeholders for calls / stories / linked devices | Done | toasts + `SettingsModal` |
| **Bonus:** attachments (images / files) | Done | `POST /attachments`, drag-drop + paste, inline images, lightbox |
| **Bonus:** message reactions | Done | `POST /messages/{id}/reactions` |
| **Bonus:** reply / quote | Done | `reply_to_id` + quoted block in bubble |
| **Bonus:** disappearing messages | Done | per-conversation retention + server sweeper |
| **Bonus:** dark / light mode | Done | CSS variables, toggle in Settings or `⌘⇧D` |
| **Bonus:** responsive (mobile / tablet / desktop) | Done | list and thread are separate screens below `md` |
| **Bonus:** keyboard shortcuts | Done | `lib/shortcuts.ts`, help modal on `?` |
| **Bonus:** message delete (tombstone) | Done | soft delete |
| **Bonus:** mute per conversation | Done | per-member flag |
| Real E2E encryption | Mocked | plaintext storage; see [Assumptions](#assumptions-and-known-limits) |

---

## Architecture

```
┌──────────────────────── Browser (Next.js) ────────────────────────┐
│  NavRail │ ConversationList │ ChatPane │ Composer │ Modals        │
│                 zustand store  ←→  WebSocket client (reconnect)   │
│                       ↕ REST client (auto token refresh)          │
└───────────────────────────────┬───────────────────────────────────┘
                                │  HTTPS + WSS
┌───────────────────────────────┴───────────────────────────────────┐
│                        FastAPI (async)                            │
│  REST routers            WebSocket gateway                        │
│   auth / users /          auth on handshake, typed event loop     │
│   contacts /                     │                                │
│   conversations /                │                                │
│   messages                       │                                │
│         └────────────┬───────────┘                                │
│                 Service layer  (the domain core)                  │
│      message · conversation · presence · auth · contact           │
│                      │                    │                       │
│              ConnectionManager      SQLAlchemy (async)            │
│              user_id → sockets              │                     │
└──────────────────────┬──────────────────────┬─────────────────────┘
                       │                      │
              (Redis Pub/Sub at scale)   SQLite (WAL) → Postgres
```

**The single rule that keeps this clean:** transports are thin. A message sent over REST and a
message sent over WebSocket call the *same* `message_service.send_message()`, so ordering,
idempotency, receipts and fan-out can never drift between the two paths.

**The single seam that makes it scale:** every outbound real-time event goes through
`ConnectionManager.send_to_users()`. Today it is an in-process dict. Multi-node means implementing
the same three methods over Redis Pub/Sub and swapping one line — no service code changes.
Details in [`SYSTEM_DESIGN.md` §9](./SYSTEM_DESIGN.md).

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js 16 (App Router), TypeScript, Tailwind v4 | App Router keeps the socket and store mounted across conversation navigation. Tailwind v4's CSS-first `@theme` holds the Signal token set. |
| State | Zustand | The store is the single place socket events land; components subscribe to slices, so a message arriving does not re-render the whole app. |
| Backend | FastAPI (async) | One event loop holds thousands of idle WebSocket connections cheaply. The workload is I/O-bound real-time, not CRUD-heavy admin. |
| ORM | SQLAlchemy 2.0 async + Alembic | DB-agnostic: SQLite → Postgres is a URL change plus a migration. |
| DB | SQLite in WAL mode | Required by the brief. WAL gives concurrent readers alongside one writer — the shape of a chat workload. |
| Real-time | Native FastAPI WebSockets | No broker needed at single-node scale; `ConnectionManager` is where Redis plugs in. |
| Auth | JWT (HS256), access + rotating refresh | Access tokens are stateless so any node validates any request. Only refresh tokens are stored, so logout can actually revoke. |

---

## Database schema

```
users ──────┬─< conversation_members >──── conversations
            │                                    │
            ├─< messages ────────────────────────┘
            │      ├─< message_reactions
            │      ├─< attachments
            │      └── reply_to_id ──> messages (self)
            ├─< contacts
            └─< refresh_tokens

otp_requests  (standalone: mocked OTP challenges)
```

| Table | Purpose | Notable columns |
|---|---|---|
| `users` | accounts | `phone_number` UK, `username` UK, `last_seen_at` |
| `conversations` | DM or group | `dm_key` UK, `last_seq` (monotonic counter), `updated_at` (list sort key) |
| `conversation_members` | membership + per-member state | `role`, **`last_read_seq`**, **`last_delivered_seq`**, `muted` |
| `messages` | the thread | `seq`, `type`, `content`, `client_msg_id`, `reply_to_id`, `deleted_at` |
| `message_reactions` | emoji reactions | unique `(message_id, user_id, emoji)` |
| `attachments` | media metadata | `url`, `mime_type`, dimensions |
| `contacts` | address book | unique `(owner_id, contact_user_id)` |
| `refresh_tokens` | revocable sessions | `jti`, `revoked`, `expires_at` |
| `otp_requests` | mocked OTP challenge | `code`, `expires_at`, `consumed` |

**Indexes that carry the load**

- `idx_messages_conv_seq (conversation_id, seq)` — the most important index in the system: it
  powers ordered pagination *and* every receipt comparison.
- `idx_members_user (user_id)` — load a user's conversation list.
- `idx_conversations_updated (updated_at)` — list sorted by recent activity.
- `uq_message_idempotency (conversation_id, sender_id, client_msg_id)` — dedupes retries.
- `conversations.dm_key` unique — exactly one DM per pair.
- `uq_member (conversation_id, user_id)` — no double membership.

---

## API overview

Base URL `/api/v1`. Full request/response bodies in [`API_CONTRACT.md`](./API_CONTRACT.md);
live OpenAPI docs at `/docs`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/request-otp` | issue a (mocked) OTP challenge |
| POST | `/auth/verify-otp` | verify → tokens, creates the user on first login |
| POST | `/auth/refresh` | rotate the token pair |
| POST | `/auth/logout` | revoke the refresh token |
| GET | `/auth/me`, `/users/me` | current user |
| PATCH | `/users/me` | update profile |
| GET | `/users/search?q=` | find people (empty `q` → existing contacts) |
| GET/POST/DELETE | `/contacts` | address book |
| GET | `/conversations` | the main list (cursor paginated) |
| POST | `/conversations` | start a DM (idempotent) or create a group |
| GET/PATCH | `/conversations/{id}` | detail with members / rename, mute |
| POST | `/conversations/{id}/members` | add members (admin only) |
| DELETE | `/conversations/{id}/members/{uid}` | remove (admin) or leave (self) |
| GET | `/conversations/{id}/messages` | history — `?before=<seq>` back, `?after=<seq>` forward |
| POST | `/conversations/{id}/messages` | REST send (fallback for the WS path) |
| POST | `/conversations/{id}/read` | advance the read high-water mark |
| DELETE | `/messages/{id}` | soft delete |
| POST/DELETE | `/messages/{id}/reactions` | reactions |
| POST | `/attachments` | upload one file (multipart), returns metadata to attach |
| WS | `/ws?token=<jwt>` | the real-time channel |

**WebSocket events** — client sends `message.send`, `message.read`, `message.delivered`,
`typing.start/stop`, `presence.ping`; server sends `connected`, `message.ack`, `message.new`,
`message.delivered`, `message.read`, `message.deleted`, `message.reaction`, `typing`,
`presence.update`, `conversation.new`, `conversation.updated`, `member.added`, `member.removed`,
`message.expired`, `error`.

Every non-2xx response uses one envelope:

```json
{ "error": { "code": "CONVERSATION_NOT_FOUND", "message": "…", "detail": {} } }
```

---

## The four decisions that matter

### 1. Per-conversation `seq`, not timestamps

Each conversation carries a `last_seq` counter. Sending does an atomic
`UPDATE conversations SET last_seq = last_seq + 1 ... RETURNING last_seq` and stamps the message
with the result. Two concurrent senders can never receive the same number — SQLite's write lock
serialises them, Postgres's row lock does. Ordering never depends on clocks, which tie and skew.

History pagination is a cursor on `seq` (`?before=42`), never `OFFSET` — O(log n) via the index and
stable while new messages arrive mid-scroll.

### 2. `client_msg_id` idempotency is what makes optimistic UI safe

The client generates a UUID per message and renders the bubble immediately. `(conversation_id,
sender_id, client_msg_id)` is unique, so a retry after a flaky network returns the *existing*
message instead of creating a duplicate. The frontend reconciles the server message onto the
optimistic row by that same id.

This is also how the REST fallback is safe: if the socket is down the client posts over REST with
the same key, and if the queued socket frame later lands, the server dedupes it.

### 3. High-water-mark receipts (the reason groups don't blow up)

A naive design writes one receipt row per message per member — O(messages × members) rows, which
kills a group chat. Instead each membership row carries `last_read_seq` and `last_delivered_seq`:

- a message with `seq = S` is read by member M **iff** `M.last_read_seq >= S`
- marking an entire thread read is **one UPDATE**, not N inserts
- unread count is `conversation.last_seq - member.last_read_seq` — a subtraction, not a `COUNT(*)`
- "read by 3 of 8" is a count over the member rows

**Tick semantics.** In a group the tick only advances when *every* recipient reaches that state,
which is why the receipt events carry the count. One person reading a group message does not turn
the sender's ticks blue.

**A visual note.** Signal draws ticks in the bubble's contrast colour, and the brief asks for a
blue read tick. On Signal's blue outgoing bubble a literal blue tick would be invisible, so: in the
**conversation list** (grey background) the read tick is Signal blue, and **inside the blue bubble**
read renders in a light blue that is unmistakably distinct from the muted white of sent/delivered.
Every tick carries an `aria-label` of `Sending` / `Sent` / `Delivered` / `Read`.

### 4. The socket is the fast path, the database is the truth

Messages are persisted before they are fanned out, so an offline recipient never depends on having
been connected. On reconnect the client does **not** try to replay missed socket events — it calls
`GET /conversations/{id}/messages?after=<last_seen_seq>` and refetches the conversation list. A
dropped connection can therefore lose events without ever losing messages.

The WS client reconnects with exponential backoff (to 20s) plus jitter, so a restarted server does
not get every client back in the same instant.

---

## Bonus features

All of the optional scope is implemented and working, not stubbed.

### Attachments (images and files)

Two-step by design: the file is uploaded first (`POST /attachments`, multipart), then the returned
URL is referenced in the message. That keeps the hot message path pure JSON over the socket, and it
means a failed upload never produces a half-sent message.

- **Attach** with the `+` button, the photo/document buttons, **drag-and-drop onto the thread**, or
  **paste an image straight from the clipboard**.
- Up to 6 files per message, 10 MB each, with an **allowlist** of accepted MIME types — anything not
  explicitly permitted is refused with `422 UNSUPPORTED_MEDIA_TYPE`.
- The client's filename never touches the filesystem: files are stored under a random name and the
  original is kept only as display metadata.
- Images render inline (never upscaled past their natural size) and open in a full-screen lightbox;
  other files render as a download chip with type and size.
- Image dimensions are measured in the browser and posted alongside the file, so the bubble reserves
  the right space before the image loads — and the server needs no image-decoding dependency.
- Files are served from `/media`. Swapping in S3/R2 means reimplementing two functions in
  `app/services/attachment_service.py`.

### Disappearing messages

A per-conversation retention window (`Off`, 30s, 5m, 1h, 8h, 1d, 1w), set from the conversation info
panel by any member, as in Signal.

- Messages sent while the window is on are stamped with `expires_at` at insert time.
- **Expiry is enforced at query time** (`expires_at IS NULL OR expires_at > now`), so a lapsed
  message can never be served even if the sweeper is behind — correctness does not depend on a
  background job.
- A background sweeper then hard-deletes the rows and pushes `message.expired` so open clients drop
  them live; the client also prunes locally each second, so a message vanishes on time without a
  round trip.
- Changing the setting posts a system message into the thread, the header and composer show a timer
  glyph, and each affected bubble carries one next to its timestamp.
- **Existing messages are never retroactively expired** — turning the timer on affects new messages
  only, which is the behaviour people expect and the safer default.

### Keyboard shortcuts

See the [table below](#keyboard-shortcuts). Modifier combinations work everywhere (⌘K should open
search mid-sentence); bare keys like `?` only fire when focus is outside a text field, so typing a
question mark still types a question mark.

### Responsive design

- **Mobile (< 768px):** the conversation list and the thread are separate full-screen views with a
  back button, and the icon rail is hidden — Signal's phone layout.
- **Tablet (768–1024px):** rail + list + thread, with a narrower list column.
- **Desktop (> 1280px):** a wider list column.

### Dark and light mode

Dark is the default, as in Signal. Every colour is a CSS variable, so the theme is one attribute on
`<html>` — no component knows which theme is active. The choice is stored and applied before first
paint by a tiny inline script, so there is no flash of the wrong theme on reload.

---

## Keyboard shortcuts

`⌘` is `Ctrl` on Windows and Linux. Press `?` in the app for this list.

| Shortcut | Action |
|---|---|
| `⌘K` | Focus the chat search |
| `⌘N` | New chat |
| `⌘⇧N` | New group |
| `⌘F` | Search inside the open conversation |
| `⌘I` | Conversation info |
| `⌘,` | Settings |
| `⌘⇧D` | Toggle dark / light theme |
| `Alt ↑` / `Alt ↓` | Previous / next conversation |
| `Enter` | Send |
| `⇧Enter` | New line |
| `⌘V` | Paste an image to attach it |
| `Esc` | Close a modal, clear search, or cancel a reply |
| `?` | Show the shortcuts help |

---

## Testing

```bash
cd backend
pytest -q                                  # 59 unit + API tests

# End-to-end against a running server (REST + live sockets, 3 concurrent users)
uvicorn app.main:app --port 8010 &
python scripts/e2e_check.py                # 67 checks
```

`scripts/e2e_check.py` drives the real stack the way a browser does and asserts the things that are
easy to get subtly wrong: ack → delivered → read tick progression, idempotent retries, gap-free
sequencing, group receipt counts being *partial* until everyone reads, non-members getting 404 on
both read and write, rate limiting, presence on connect/disconnect, and reconnect backfill.

Point it at a deployment with `E2E_HOST=https://your-api.example.com python scripts/e2e_check.py`.

**Frontend:** `npm run typecheck` and `npm run build`. The UI was additionally driven in a real
browser with two live sessions side by side — 57 assertions across login, live send/receive, tick
progression, typing, persistence across refresh, group creation and fan-out, member management,
search, placeholders, theme toggle, image and file attachments (upload, inline render, lightbox,
download link), disappearing messages (picker, system message, timer glyphs, delivery), every
keyboard shortcut, and the mobile/tablet/desktop layouts.

---

## Deployment

**Backend — Railway or Fly.io.** Both keep a process alive and support WebSockets. A `Dockerfile`
and `railway.json` are included; mount a volume at `/data` so `signal.db` survives redeploys.

Environment:

```
JWT_SECRET=<a long random string>          # required — do not ship the default
DATABASE_URL=sqlite+aiosqlite:////data/signal.db
CORS_ORIGINS=https://your-app.vercel.app   # comma separated, or a JSON array
SEED_ON_STARTUP=true
MEDIA_ROOT=/data/media                     # uploads live on the same volume as the DB
```

> Render's free tier cold-starts and drops idle WebSockets, so prefer Railway or Fly for the demo.

**Frontend — Vercel.** Set `NEXT_PUBLIC_API_URL=https://your-api.up.railway.app`. The WebSocket URL
is derived automatically (`https` → `wss`); override with `NEXT_PUBLIC_WS_URL` if the socket lives
elsewhere. These are inlined at build time, so a change needs a redeploy.

CORS already allows any `*.vercel.app` origin by regex, so preview deployments work without
reconfiguring the API on every push.

**Schema on boot.** `app/db/bootstrap.py` runs `alembic upgrade head` at startup and falls back to
`metadata.create_all` if Alembic is unavailable, then seeds only when the database is empty — so a
fresh container comes up usable, and a redeploy never re-seeds over real data.

---

## Assumptions and known limits

Called out deliberately rather than hidden:

- **Encryption is mocked.** Messages are stored in plaintext. The Double Ratchet / X3DH would sit
  client-side: encrypt before send, and the server would store ciphertext blobs it cannot read. The
  *contract* is simulated, not the crypto — the schema and API would not change.
- **OTP is mocked.** The code is fixed and returned in the response so the UI can prefill it. The
  flow around it is real: challenges are rows, they expire, they are single-use. Swapping in Twilio
  is one function in `auth_service.request_otp`.
- **SQLite is single-writer.** Fine for this workload with WAL and short transactions, and nothing
  in the design depends on it — Postgres is a URL change. Called out because it *is* the first
  bottleneck under real concurrency.
- **Presence and connections are per-process.** Documented as the exact swap point for Redis.
  A second instance today would mean two users on different nodes not seeing each other live —
  which is precisely what `RedisConnectionManager` fixes.
- **Rate limiting is in-process** (20 messages / 10s / user). A guard rail for the demo; a Redis
  token bucket for real deployment.
- **Attachments are stored on local disk** under `MEDIA_ROOT` and served from `/media`. That needs a
  persistent volume in production (the same one as the database). Object storage is the real answer
  at scale and is confined to `attachment_service.py`. Uploaded files are not virus-scanned, and
  they are served without an auth check — anyone holding the random URL can fetch the file, which is
  a deliberate simplification, not an oversight.
- **Disappearing messages delete server-side.** A recipient who already received the message could
  in principle have kept a copy; the same is true of Signal. Expiry is enforced at query time so a
  late sweep cannot leak, but the timer starts when the server accepts the message, not when it is
  read.
- **Calls, stories and linked devices are placeholders**, as scoped in the brief.
- **Contact requests and blocking are out of scope.** The `contacts` table is where they'd attach.
- **New group members do not inherit the backlog as unread.** Their high-water marks start at the
  group's current `last_seq`, so joining a busy group shows 1 unread (the "X added You" system
  message), not 400.
