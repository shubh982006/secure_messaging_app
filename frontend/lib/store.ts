"use client";

import { create } from "zustand";

import { api, tokens } from "./api";
import { socket, type SocketStatus } from "./ws";
import type { Attachment, Conversation, Me, Message, WsEnvelope } from "./types";

interface Toast {
  id: string;
  text: string;
  tone: "info" | "error";
}

interface TypingEntry {
  userId: string;
  name: string;
  at: number;
}

interface State {
  me: Me | null;
  booted: boolean;
  status: SocketStatus;

  conversations: Conversation[];
  activeId: string | null;

  /** conversation_id -> ascending messages */
  messages: Record<string, Message[]>;
  /** conversation_id -> whether older pages remain */
  hasMore: Record<string, boolean>;
  loadingThread: Record<string, boolean>;

  /** conversation_id -> people currently typing */
  typing: Record<string, TypingEntry[]>;
  onlineUsers: Set<string>;

  toasts: Toast[];
  search: string;
  theme: "dark" | "light";

  // actions
  boot: () => Promise<void>;
  setMe: (me: Me) => void;
  signOut: () => Promise<void>;

  loadConversations: () => Promise<void>;
  openConversation: (id: string) => Promise<void>;
  loadOlder: (id: string) => Promise<void>;

  sendMessage: (
    conversationId: string,
    text: string,
    replyToId?: string | null,
    attachments?: Attachment[],
  ) => void;
  deleteMessage: (messageId: string, conversationId: string) => Promise<void>;
  toggleReaction: (messageId: string, conversationId: string, emoji: string) => Promise<void>;
  markRead: (conversationId: string) => void;
  setTyping: (conversationId: string, isTyping: boolean) => void;

  upsertConversation: (conversation: Conversation) => void;
  setSearch: (value: string) => void;
  toast: (text: string, tone?: "info" | "error") => void;
  dismissToast: (id: string) => void;
  toggleTheme: () => void;
}

const TYPING_TTL = 4000;

function sortConversations(list: Conversation[]): Conversation[] {
  return [...list].sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  );
}

/** The one-line summary shown in the conversation list. Mirrors the server's
 *  preview_text so an optimistic row and a fetched one read the same. */
function previewFor(message: {
  content: string | null;
  attachments: Attachment[];
  type: string;
}): string {
  if (message.content) return message.content;
  const attachment = message.attachments[0];
  if (attachment) {
    const mime = attachment.mime_type ?? "";
    if (mime.startsWith("audio/")) return "Voice message";
    if (mime.startsWith("image/")) return "Photo";
    if (mime.startsWith("video/")) return "Video";
    return attachment.name ?? "Attachment";
  }
  return message.type === "image" ? "Photo" : message.type === "file" ? "Attachment" : "";
}

/** Merge a server message into a thread, reconciling the optimistic bubble. */
function mergeMessage(thread: Message[], incoming: Message): Message[] {
  const index = thread.findIndex(
    (m) =>
      m.id === incoming.id ||
      (incoming.client_msg_id != null && m.client_msg_id === incoming.client_msg_id),
  );
  if (index >= 0) {
    const next = [...thread];
    // Keep the higher status: a `read` receipt can land before `message.new`.
    next[index] = { ...next[index], ...incoming, pending: false };
    return next;
  }
  const next = [...thread, incoming];
  next.sort((a, b) => a.seq - b.seq);
  return next;
}

export const useStore = create<State>((set, get) => ({
  me: null,
  booted: false,
  status: "closed",

  conversations: [],
  activeId: null,
  messages: {},
  hasMore: {},
  loadingThread: {},
  typing: {},
  onlineUsers: new Set<string>(),
  toasts: [],
  search: "",
  theme: "dark",

  // ------------------------------------------------------------------ boot
  async boot() {
    if (!tokens.access) {
      set({ booted: true });
      return;
    }
    try {
      const me = await api.me();
      set({ me });
      await get().loadConversations();
      attachSocket();
      socket.connect();
    } catch {
      tokens.clear();
      set({ me: null });
    } finally {
      set({ booted: true });
    }
  },

  setMe: (me) => set({ me }),

  async signOut() {
    try {
      await api.logout();
    } catch {
      /* logging out locally matters more than the round trip */
    }
    socket.disconnect();
    tokens.clear();
    set({
      me: null,
      conversations: [],
      messages: {},
      activeId: null,
      typing: {},
      onlineUsers: new Set(),
    });
  },

  // ----------------------------------------------------------- conversations
  async loadConversations() {
    const { conversations } = await api.conversations();
    set({ conversations: sortConversations(conversations) });
  },

  async openConversation(id) {
    set({ activeId: id });
    const existing = get().messages[id];
    if (!existing) {
      set((state) => ({ loadingThread: { ...state.loadingThread, [id]: true } }));
      try {
        const page = await api.messages(id, { limit: 50 });
        set((state) => ({
          messages: { ...state.messages, [id]: page.messages },
          hasMore: { ...state.hasMore, [id]: page.next_cursor !== null },
          loadingThread: { ...state.loadingThread, [id]: false },
        }));
      } catch {
        set((state) => ({ loadingThread: { ...state.loadingThread, [id]: false } }));
      }
    }
    get().markRead(id);
  },

  async loadOlder(id) {
    const thread = get().messages[id] ?? [];
    if (!thread.length || !get().hasMore[id]) return;
    const page = await api.messages(id, { before: thread[0].seq, limit: 50 });
    set((state) => ({
      messages: { ...state.messages, [id]: [...page.messages, ...(state.messages[id] ?? [])] },
      hasMore: { ...state.hasMore, [id]: page.next_cursor !== null },
    }));
  },

  // --------------------------------------------------------------- messaging
  sendMessage(conversationId, text, replyToId = null, attachments = []) {
    const me = get().me;
    const body = text.trim();
    // A message needs either text or at least one attachment.
    if (!me || (!body && attachments.length === 0)) return;

    const conversation = get().conversations.find((c) => c.id === conversationId);
    const messageType = attachments.length
      ? attachments.every((a) => (a.mime_type ?? "").startsWith("image/"))
        ? "image"
        : "file"
      : "text";

    const clientMsgId = crypto.randomUUID();
    const thread = get().messages[conversationId] ?? [];
    const nextSeq = (thread[thread.length - 1]?.seq ?? 0) + 1;
    const replyTo = replyToId
      ? thread.find((m) => m.id === replyToId) ?? null
      : null;

    // Optimistic bubble: rendered instantly with a "sending" clock icon. The
    // client_msg_id makes the eventual server message reconcile onto this row,
    // and makes a retry safe.
    const optimistic: Message = {
      id: `local-${clientMsgId}`,
      conversation_id: conversationId,
      sender_id: me.id,
      seq: nextSeq,
      type: messageType,
      content: body,
      client_msg_id: clientMsgId,
      reply_to: replyTo
        ? {
            id: replyTo.id,
            sender_id: replyTo.sender_id,
            sender_name: null,
            preview: replyTo.content ?? "",
            type: replyTo.type,
          }
        : null,
      reactions: [],
      attachments,
      created_at: new Date().toISOString(),
      edited_at: null,
      deleted_at: null,
      // Mirror the server's retention window so the timer glyph shows at once.
      expires_at: conversation?.disappear_seconds
        ? new Date(Date.now() + conversation.disappear_seconds * 1000).toISOString()
        : null,
      delivered_to: 0,
      read_by: 0,
      recipients: 0,
      status: "sending",
      pending: true,
    };

    set((state) => ({
      messages: {
        ...state.messages,
        [conversationId]: [...(state.messages[conversationId] ?? []), optimistic],
      },
      conversations: sortConversations(
        state.conversations.map((c) =>
          c.id === conversationId
            ? {
                ...c,
                updated_at: optimistic.created_at,
                last_message: {
                  id: optimistic.id,
                  sender_id: me.id,
                  sender_name: me.display_name,
                  type: messageType,
                  preview: previewFor({
                    content: body || null,
                    attachments,
                    type: messageType,
                  }),
                  seq: nextSeq,
                  created_at: optimistic.created_at,
                  status: "sending",
                  deleted: false,
                },
              }
            : c,
        ),
      ),
    }));

    const delivered = socket.send("message.send", {
      conversation_id: conversationId,
      client_msg_id: clientMsgId,
      type: messageType,
      content: body,
      reply_to_id: replyToId,
      attachments,
    });

    if (!delivered) {
      // Socket is down - fall back to REST. Same idempotency key, so if the
      // queued socket frame also lands later the server dedupes it.
      api
        .sendMessage(conversationId, {
          content: body,
          client_msg_id: clientMsgId,
          reply_to_id: replyToId,
          type: messageType,
          attachments,
        })
        .then((message) => {
          set((state) => ({
            messages: {
              ...state.messages,
              [conversationId]: mergeMessage(
                state.messages[conversationId] ?? [],
                message,
              ),
            },
          }));
        })
        .catch(() => {
          set((state) => ({
            messages: {
              ...state.messages,
              [conversationId]: (state.messages[conversationId] ?? []).map((m) =>
                m.client_msg_id === clientMsgId
                  ? { ...m, status: "failed" as const, pending: false }
                  : m,
              ),
            },
          }));
          get().toast("Message failed to send", "error");
        });
    }
  },

  async deleteMessage(messageId, conversationId) {
    try {
      await api.deleteMessage(messageId);
      set((state) => ({
        messages: {
          ...state.messages,
          [conversationId]: (state.messages[conversationId] ?? []).map((m) =>
            m.id === messageId
              ? { ...m, deleted_at: new Date().toISOString(), content: null, reactions: [] }
              : m,
          ),
        },
      }));
      get().toast("Message deleted");
    } catch {
      get().toast("Could not delete that message", "error");
    }
  },

  async toggleReaction(messageId, conversationId, emoji) {
    const me = get().me;
    if (!me) return;
    const thread = get().messages[conversationId] ?? [];
    const message = thread.find((m) => m.id === messageId);
    const mine = message?.reactions.some(
      (r) => r.user_id === me.id && r.emoji === emoji,
    );
    try {
      if (mine) await api.removeReaction(messageId, emoji);
      else await api.addReaction(messageId, emoji);
    } catch {
      get().toast("Could not update that reaction", "error");
    }
  },

  markRead(conversationId) {
    const thread = get().messages[conversationId] ?? [];
    const last = thread[thread.length - 1];
    const conversation = get().conversations.find((c) => c.id === conversationId);
    if (!conversation) return;
    if (conversation.unread_count === 0 && !last) return;

    set((state) => ({
      conversations: state.conversations.map((c) =>
        c.id === conversationId
          ? { ...c, unread_count: 0, my_last_read_seq: c.last_seq }
          : c,
      ),
    }));

    if (!socket.send("message.read", {
      conversation_id: conversationId,
      last_read_message_id: last && !last.pending ? last.id : null,
    })) {
      api.markRead(conversationId, last && !last.pending ? last.id : undefined).catch(() => {});
    }
  },

  setTyping(conversationId, isTyping) {
    socket.send(isTyping ? "typing.start" : "typing.stop", {
      conversation_id: conversationId,
    });
  },

  upsertConversation(conversation) {
    set((state) => {
      const exists = state.conversations.some((c) => c.id === conversation.id);
      const next = exists
        ? state.conversations.map((c) =>
            c.id === conversation.id ? { ...c, ...conversation } : c,
          )
        : [conversation, ...state.conversations];
      return { conversations: sortConversations(next) };
    });
  },

  setSearch: (value) => set({ search: value }),

  toast(text, tone = "info") {
    const id = crypto.randomUUID();
    set((state) => ({ toasts: [...state.toasts, { id, text, tone }] }));
    setTimeout(() => get().dismissToast(id), 3200);
  },

  dismissToast(id) {
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
  },

  toggleTheme() {
    const theme = get().theme === "dark" ? "light" : "dark";
    set({ theme });
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("signal.theme", theme);
  },
}));

// --------------------------------------------------------------------------- //
// socket -> store wiring
// --------------------------------------------------------------------------- //
let attached = false;

export function attachSocket() {
  if (attached) return;
  attached = true;

  socket.onStatus((status) => {
    const previous = useStore.getState().status;
    useStore.setState({ status });
    // Reconnected after a drop: the socket may have missed events, so resync
    // from the database, which is the source of truth.
    if (status === "open" && previous === "reconnecting") {
      const { loadConversations, activeId, messages } = useStore.getState();
      loadConversations().catch(() => {});
      if (activeId) {
        const thread = messages[activeId] ?? [];
        const lastSeq = thread[thread.length - 1]?.seq ?? 0;
        api
          .messages(activeId, { after: lastSeq, limit: 100 })
          .then((page) => {
            useStore.setState((state) => ({
              messages: {
                ...state.messages,
                [activeId]: page.messages.reduce(
                  mergeMessage,
                  state.messages[activeId] ?? [],
                ),
              },
            }));
          })
          .catch(() => {});
      }
    }
  });

  socket.on((event) => handleEvent(event));

  setInterval(() => {
    const state = useStore.getState();
    const now = Date.now();

    // Expire stale typing indicators - the server never sends a "stopped" event
    // if the sender simply closed their laptop.
    let typingChanged = false;
    const nextTyping: Record<string, TypingEntry[]> = {};
    for (const [conversationId, entries] of Object.entries(state.typing)) {
      const live = entries.filter((entry) => now - entry.at < TYPING_TTL);
      if (live.length !== entries.length) typingChanged = true;
      if (live.length) nextTyping[conversationId] = live;
    }
    if (typingChanged) useStore.setState({ typing: nextTyping });

    // Drop disappearing messages the moment they lapse, rather than waiting for
    // the server sweep. The server filters them out too, so a refresh agrees.
    let messagesChanged = false;
    const nextMessages: Record<string, Message[]> = {};
    for (const [conversationId, thread] of Object.entries(state.messages)) {
      const live = thread.filter(
        (m) => !m.expires_at || new Date(m.expires_at).getTime() > now,
      );
      if (live.length !== thread.length) messagesChanged = true;
      nextMessages[conversationId] = live;
    }
    if (messagesChanged) useStore.setState({ messages: nextMessages });
  }, 1000);
}

function handleEvent(event: WsEnvelope) {
  const state = useStore.getState();

  switch (event.type) {
    case "connected": {
      const ids = (event.payload.online_user_ids as string[]) ?? [];
      useStore.setState({ onlineUsers: new Set(ids) });
      break;
    }

    case "message.new": {
      const message = (event.payload as { message: Message }).message;
      const isMine = message.sender_id === state.me?.id;
      const isActive = state.activeId === message.conversation_id;

      useStore.setState((current) => {
        const thread = current.messages[message.conversation_id];
        // Only extend threads we have already loaded; an unopened conversation
        // gets its history on demand.
        const nextMessages = thread
          ? { ...current.messages, [message.conversation_id]: mergeMessage(thread, message) }
          : current.messages;

        const conversations = current.conversations.map((c) =>
          c.id === message.conversation_id
            ? {
                ...c,
                updated_at: message.created_at,
                last_seq: Math.max(c.last_seq, message.seq),
                unread_count:
                  isMine || isActive ? 0 : c.unread_count + 1,
                my_last_read_seq: isMine || isActive ? message.seq : c.my_last_read_seq,
                last_message: {
                  id: message.id,
                  sender_id: message.sender_id,
                  sender_name: null,
                  type: message.type,
                  preview: previewFor(message),
                  seq: message.seq,
                  created_at: message.created_at,
                  status: message.status,
                  deleted: false,
                },
              }
            : c,
        );

        // Someone who was typing has now sent - clear their indicator.
        const typingForConversation = (current.typing[message.conversation_id] ?? []).filter(
          (entry) => entry.userId !== message.sender_id,
        );

        return {
          messages: nextMessages,
          conversations: sortConversations(conversations),
          typing: { ...current.typing, [message.conversation_id]: typingForConversation },
        };
      });

      if (!isMine) {
        // Auto-acknowledge delivery the moment the device has the message.
        socket.send("message.delivered", {
          conversation_id: message.conversation_id,
          message_id: message.id,
        });
        if (isActive && document.visibilityState === "visible") {
          useStore.getState().markRead(message.conversation_id);
        }
      }

      // A conversation we did not know about (someone started a chat with us).
      if (!state.conversations.some((c) => c.id === message.conversation_id)) {
        api.conversation(message.conversation_id)
          .then((conversation) => useStore.getState().upsertConversation(conversation))
          .catch(() => {});
      }
      break;
    }

    case "message.ack": {
      const ack = event.payload as unknown as {
        client_msg_id: string;
        message_id: string;
        conversation_id: string;
        seq: number;
        created_at: string;
        status: Message["status"];
      };
      useStore.setState((current) => ({
        messages: {
          ...current.messages,
          [ack.conversation_id]: (current.messages[ack.conversation_id] ?? []).map((m) =>
            m.client_msg_id === ack.client_msg_id
              ? {
                  ...m,
                  id: ack.message_id,
                  seq: ack.seq,
                  created_at: ack.created_at,
                  status: m.status === "sending" ? ack.status : m.status,
                  pending: false,
                }
              : m,
          ),
        },
        conversations: current.conversations.map((c) =>
          c.id === ack.conversation_id
            ? {
                ...c,
                last_seq: Math.max(c.last_seq, ack.seq),
                my_last_read_seq: Math.max(c.my_last_read_seq, ack.seq),
                last_message:
                  c.last_message && c.last_message.seq >= ack.seq
                    ? { ...c.last_message, id: ack.message_id, status: ack.status }
                    : c.last_message,
              }
            : c,
        ),
      }));
      break;
    }

    case "message.delivered": {
      const info = event.payload as unknown as {
        conversation_id: string;
        last_delivered_seq: number;
        delivered_to: number;
      };
      applyReceipt(info.conversation_id, info.last_delivered_seq, "delivered", info.delivered_to);
      break;
    }

    case "message.read": {
      const info = event.payload as unknown as {
        conversation_id: string;
        last_read_seq: number;
        read_by: number;
        self?: boolean;
      };
      if (info.self) break; // our own read marker, nothing to repaint
      applyReceipt(info.conversation_id, info.last_read_seq, "read", info.read_by);
      break;
    }

    case "message.deleted": {
      const info = event.payload as unknown as {
        conversation_id: string;
        message_id: string;
      };
      useStore.setState((current) => ({
        messages: {
          ...current.messages,
          [info.conversation_id]: (current.messages[info.conversation_id] ?? []).map((m) =>
            m.id === info.message_id
              ? { ...m, deleted_at: new Date().toISOString(), content: null, reactions: [] }
              : m,
          ),
        },
      }));
      break;
    }

    case "message.expired": {
      const info = event.payload as unknown as {
        conversation_id: string;
        message_ids: string[];
      };
      const gone = new Set(info.message_ids);
      useStore.setState((current) => ({
        messages: {
          ...current.messages,
          [info.conversation_id]: (current.messages[info.conversation_id] ?? []).filter(
            (m) => !gone.has(m.id),
          ),
        },
      }));
      break;
    }

    case "message.reaction": {
      const info = event.payload as unknown as {
        conversation_id: string;
        message_id: string;
        reactions: Message["reactions"];
      };
      useStore.setState((current) => ({
        messages: {
          ...current.messages,
          [info.conversation_id]: (current.messages[info.conversation_id] ?? []).map((m) =>
            m.id === info.message_id ? { ...m, reactions: info.reactions } : m,
          ),
        },
      }));
      break;
    }

    case "typing": {
      const info = event.payload as unknown as {
        conversation_id: string;
        user_id: string;
        is_typing: boolean;
      };
      const conversation = state.conversations.find((c) => c.id === info.conversation_id);
      const name =
        conversation?.members?.find((m) => m.user_id === info.user_id)?.display_name ??
        conversation?.peer?.display_name ??
        "Someone";

      useStore.setState((current) => {
        const entries = (current.typing[info.conversation_id] ?? []).filter(
          (entry) => entry.userId !== info.user_id,
        );
        if (info.is_typing) entries.push({ userId: info.user_id, name, at: Date.now() });
        return { typing: { ...current.typing, [info.conversation_id]: entries } };
      });
      break;
    }

    case "presence.update": {
      const info = event.payload as unknown as {
        user_id: string;
        is_online: boolean;
        last_seen_at: string | null;
      };
      useStore.setState((current) => {
        const online = new Set(current.onlineUsers);
        if (info.is_online) online.add(info.user_id);
        else online.delete(info.user_id);
        return {
          onlineUsers: online,
          conversations: current.conversations.map((c) =>
            c.peer?.id === info.user_id
              ? {
                  ...c,
                  is_online: info.is_online,
                  last_seen_at: info.last_seen_at ?? c.last_seen_at,
                  peer: { ...c.peer, is_online: info.is_online, last_seen_at: info.last_seen_at },
                }
              : c,
          ),
        };
      });
      break;
    }

    case "conversation.new":
    case "conversation.updated": {
      const conversation = (event.payload as { conversation: Conversation }).conversation;
      useStore.getState().upsertConversation(conversation);
      break;
    }

    case "member.removed": {
      const info = event.payload as unknown as {
        conversation_id: string;
        user_id: string;
      };
      if (info.user_id === state.me?.id) {
        useStore.setState((current) => ({
          conversations: current.conversations.filter((c) => c.id !== info.conversation_id),
          activeId: current.activeId === info.conversation_id ? null : current.activeId,
        }));
        useStore.getState().toast("You were removed from the group");
      }
      break;
    }

    case "auth.expired": {
      useStore.getState().toast("Session expired, please sign in again", "error");
      break;
    }

    case "error": {
      const info = event.payload as unknown as { code: string; message: string };
      if (info.code === "RATE_LIMITED") {
        useStore.getState().toast("You're sending messages too quickly", "error");
      }
      break;
    }

    default:
      break;
  }
}

/**
 * Roll a high-water mark forward across every one of my messages at or below it.
 *
 * In a group the tick only advances once *every* recipient has reached that
 * state, which is why the count travels with the event - one person reading a
 * group message must not turn the sender's ticks blue.
 */
function applyReceipt(
  conversationId: string,
  seq: number,
  status: "delivered" | "read",
  reachedBy: number,
) {
  const store = useStore.getState();
  const me = store.me;
  if (!me) return;

  const conversation = store.conversations.find((c) => c.id === conversationId);
  const recipients = Math.max(1, (conversation?.members_count ?? 2) - 1);
  if (reachedBy < recipients) return;

  const rank = { sending: 0, failed: 0, sent: 1, delivered: 2, read: 3 };

  useStore.setState((current) => ({
    messages: {
      ...current.messages,
      [conversationId]: (current.messages[conversationId] ?? []).map((m) =>
        m.sender_id === me.id && m.seq <= seq && rank[m.status] < rank[status]
          ? { ...m, status }
          : m,
      ),
    },
    conversations: current.conversations.map((c) =>
      c.id === conversationId &&
      c.last_message &&
      c.last_message.sender_id === me.id &&
      c.last_message.seq <= seq &&
      rank[c.last_message.status] < rank[status]
        ? { ...c, last_message: { ...c.last_message, status } }
        : c,
    ),
  }));
}
