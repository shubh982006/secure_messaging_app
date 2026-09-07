import type {
  Attachment,
  ApiErrorBody,
  Contact,
  Conversation,
  LinkPreview,
  Me,
  Message,
  MessageSearchHit,
  UploadedAttachment,
  User,
} from "./types";

export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL?.replace(/\/$/, "") ??
  API_URL.replace(/^http/, "ws");

const API = `${API_URL}/api/v1`;

const ACCESS_KEY = "signal.access_token";
const REFRESH_KEY = "signal.refresh_token";

export const tokens = {
  get access() {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    if (typeof window === "undefined") return null;
    return window.localStorage.getItem(REFRESH_KEY);
  },
  set(access: string, refresh: string) {
    window.localStorage.setItem(ACCESS_KEY, access);
    window.localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    window.localStorage.removeItem(ACCESS_KEY);
    window.localStorage.removeItem(REFRESH_KEY);
  },
};

export class ApiError extends Error {
  code: string;
  status: number;
  detail: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.status = status;
    this.code = body.code;
    this.detail = body.detail ?? {};
  }
}

let refreshInFlight: Promise<boolean> | null = null;

/** Exchange the refresh token for a new pair. Concurrent 401s share one call. */
async function refreshTokens(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    const refresh = tokens.refresh;
    if (!refresh) return false;
    try {
      const response = await fetch(`${API}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!response.ok) return false;
      const body = await response.json();
      tokens.set(body.access_token, body.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  auth?: boolean;
  retry?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true, retry = true } = options;

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth && tokens.access) headers.Authorization = `Bearer ${tokens.access}`;

  const response = await fetch(`${API}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 401 && auth && retry) {
    // Access tokens are short lived by design; rotate and replay once.
    if (await refreshTokens()) {
      return request<T>(path, { ...options, retry: false });
    }
    tokens.clear();
  }

  if (response.status === 204) return undefined as T;

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      response.status,
      payload?.error ?? { code: "NETWORK_ERROR", message: "Request failed" },
    );
  }
  return payload as T;
}

/** Attachment URLs come back relative to the API host. */
export function mediaUrl(url: string): string {
  return url.startsWith("/") ? `${API_URL}${url}` : url;
}

/** Read an image's natural size in the browser so the server needs no decoder. */
function imageDimensions(file: File): Promise<{ width: number; height: number } | null> {
  if (!file.type.startsWith("image/")) return Promise.resolve(null);
  return new Promise((resolve) => {
    const objectUrl = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(objectUrl);
      resolve({ width: image.naturalWidth, height: image.naturalHeight });
    };
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      resolve(null);
    };
    image.src = objectUrl;
  });
}

export const api = {
  // --- auth ---------------------------------------------------------------
  requestOtp: (phone_number: string) =>
    request<{ request_id: string; mocked_code: string; expires_in: number }>(
      "/auth/request-otp",
      { method: "POST", body: { phone_number }, auth: false },
    ),

  verifyOtp: (phone_number: string, code: string) =>
    request<{
      access_token: string;
      refresh_token: string;
      is_new_user: boolean;
      user: Me;
    }>("/auth/verify-otp", {
      method: "POST",
      body: { phone_number, code },
      auth: false,
    }),

  logout: () =>
    request<void>("/auth/logout", {
      method: "POST",
      body: { refresh_token: tokens.refresh },
    }),

  me: () => request<Me>("/users/me"),

  updateProfile: (patch: Partial<Pick<Me, "display_name" | "avatar_url" | "about" | "username">>) =>
    request<Me>("/users/me", { method: "PATCH", body: patch }),

  searchUsers: (q: string) =>
    request<{ results: User[] }>(`/users/search?q=${encodeURIComponent(q)}`),

  // --- contacts -----------------------------------------------------------
  contacts: () => request<{ contacts: Contact[] }>("/contacts"),

  /** Identify the peer by exactly one of phone_number, username or user_id. */
  addContact: (body: {
    phone_number?: string;
    username?: string;
    user_id?: string;
    nickname?: string | null;
  }) => request<Contact>("/contacts", { method: "POST", body }),

  deleteContact: (id: string) =>
    request<void>(`/contacts/${id}`, { method: "DELETE" }),

  // --- conversations ------------------------------------------------------
  conversations: (before?: string) =>
    request<{ conversations: Conversation[]; next_cursor: string | null }>(
      `/conversations${before ? `?before=${encodeURIComponent(before)}` : ""}`,
    ),

  conversation: (id: string) => request<Conversation>(`/conversations/${id}`),

  startDirect: (user_id: string) =>
    request<Conversation>("/conversations", {
      method: "POST",
      body: { type: "direct", user_id },
    }),

  createGroup: (name: string, member_ids: string[], avatar_url?: string | null) =>
    request<Conversation>("/conversations", {
      method: "POST",
      body: { type: "group", name, member_ids, avatar_url },
    }),

  updateConversation: (
    id: string,
    patch: {
      name?: string;
      avatar_url?: string | null;
      muted?: boolean;
      disappear_seconds?: number;
    },
  ) => request<Conversation>(`/conversations/${id}`, { method: "PATCH", body: patch }),

  addMembers: (id: string, user_ids: string[]) =>
    request<Conversation>(`/conversations/${id}/members`, {
      method: "POST",
      body: { user_ids },
    }),

  removeMember: (id: string, user_id: string) =>
    request<void>(`/conversations/${id}/members/${user_id}`, { method: "DELETE" }),

  leaveConversation: (id: string) =>
    request<void>(`/conversations/${id}`, { method: "DELETE" }),

  markRead: (id: string, last_read_message_id?: string) =>
    request<{ unread_count: number; last_read_seq: number }>(
      `/conversations/${id}/read`,
      { method: "POST", body: { last_read_message_id: last_read_message_id ?? null } },
    ),

  // --- messages -----------------------------------------------------------
  messages: (id: string, params: { before?: number; after?: number; limit?: number } = {}) => {
    const search = new URLSearchParams();
    if (params.before !== undefined) search.set("before", String(params.before));
    if (params.after !== undefined) search.set("after", String(params.after));
    search.set("limit", String(params.limit ?? 50));
    return request<{ messages: Message[]; next_cursor: string | null }>(
      `/conversations/${id}/messages?${search.toString()}`,
    );
  },

  /** REST fallback used only when the socket is down. */
  sendMessage: (
    id: string,
    body: {
      content: string;
      client_msg_id: string;
      reply_to_id?: string | null;
      type?: string;
      attachments?: Attachment[];
    },
  ) =>
    request<Message>(`/conversations/${id}/messages`, {
      method: "POST",
      body: { type: "text", ...body },
    }),

  /**
   * Upload one file, then reference the returned URL in a message. Two steps on
   * purpose: it keeps the hot message path pure JSON over the socket.
   */
  uploadAttachment: async (file: File): Promise<UploadedAttachment> => {
    const dimensions = await imageDimensions(file);
    const form = new FormData();
    form.append("file", file);
    if (dimensions) {
      form.append("width", String(dimensions.width));
      form.append("height", String(dimensions.height));
    }

    const headers: Record<string, string> = {};
    if (tokens.access) headers.Authorization = `Bearer ${tokens.access}`;

    let response = await fetch(`${API}/attachments`, { method: "POST", headers, body: form });
    if (response.status === 401 && (await refreshTokens())) {
      headers.Authorization = `Bearer ${tokens.access}`;
      response = await fetch(`${API}/attachments`, { method: "POST", headers, body: form });
    }

    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new ApiError(
        response.status,
        payload?.error ?? { code: "UPLOAD_FAILED", message: "Upload failed" },
      );
    }
    return payload as UploadedAttachment;
  },

  deleteMessage: (id: string) => request<void>(`/messages/${id}`, { method: "DELETE" }),

  /** Full-text search across every conversation the user belongs to. */
  searchMessages: (q: string, conversationId?: string) => {
    const search = new URLSearchParams({ q });
    if (conversationId) search.set("conversation_id", conversationId);
    return request<{ results: MessageSearchHit[]; query: string }>(
      `/search/messages?${search.toString()}`,
    );
  },

  linkPreview: (url: string) =>
    request<LinkPreview>(`/links/preview?url=${encodeURIComponent(url)}`),

  addReaction: (id: string, emoji: string) =>
    request<Message>(`/messages/${id}/reactions`, { method: "POST", body: { emoji } }),

  removeReaction: (id: string, emoji: string) =>
    request<Message>(`/messages/${id}/reactions/${encodeURIComponent(emoji)}`, {
      method: "DELETE",
    }),
};
