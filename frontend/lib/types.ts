export type ConversationType = "direct" | "group";
export type MemberRole = "admin" | "member";
export type MessageStatus = "sending" | "sent" | "delivered" | "read" | "failed";
export type MessageKind = "text" | "image" | "file" | "system";

export interface User {
  id: string;
  username: string | null;
  display_name: string | null;
  avatar_url: string | null;
  about: string | null;
  last_seen_at: string | null;
  is_online: boolean;
}

export interface Me extends User {
  phone_number: string;
  created_at: string | null;
}

export interface Contact {
  id: string;
  user: User;
  /** A locally chosen name that overrides the peer's own display_name. */
  nickname: string | null;
  created_at: string;
}

export interface Member {
  user_id: string;
  display_name: string | null;
  username: string | null;
  avatar_url: string | null;
  about: string | null;
  role: MemberRole;
  last_read_seq: number;
  last_delivered_seq: number;
  is_online: boolean;
  last_seen_at: string | null;
  joined_at: string | null;
}

export interface Attachment {
  id?: string;
  url: string;
  name: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  width: number | null;
  height: number | null;
}

/** What POST /attachments hands back, before it is attached to a message. */
export interface UploadedAttachment extends Attachment {
  kind: "image" | "file";
}

export interface Reaction {
  emoji: string;
  user_id: string;
}

export interface ReplyPreview {
  id: string;
  sender_id: string | null;
  sender_name: string | null;
  preview: string;
  type: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  sender_id: string | null;
  seq: number;
  type: MessageKind;
  content: string | null;
  client_msg_id: string | null;
  reply_to: ReplyPreview | null;
  reactions: Reaction[];
  attachments: Attachment[];
  created_at: string;
  edited_at: string | null;
  deleted_at: string | null;
  expires_at: string | null;
  delivered_to: number;
  read_by: number;
  recipients: number;
  status: MessageStatus;
  /** Client-only: set on an optimistic bubble before the server acks it. */
  pending?: boolean;
}

export interface LastMessagePreview {
  id: string;
  sender_id: string | null;
  sender_name: string | null;
  type: MessageKind;
  preview: string;
  seq: number;
  created_at: string;
  status: MessageStatus;
  deleted: boolean;
}

export interface Conversation {
  id: string;
  type: ConversationType;
  name: string | null;
  avatar_url: string | null;
  members_count: number;
  last_message: LastMessagePreview | null;
  unread_count: number;
  is_online: boolean;
  last_seen_at: string | null;
  muted: boolean;
  my_role: MemberRole;
  peer: User | null;
  last_seq: number;
  my_last_read_seq: number;
  created_at: string | null;
  updated_at: string;
  /** 0 means disappearing messages are off. */
  disappear_seconds: number;
  members?: Member[];
}

export interface WsEnvelope<T = Record<string, unknown>> {
  type: string;
  id: string;
  ts: string;
  payload: T;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  detail?: Record<string, unknown>;
}

export interface LinkPreview {
  url: string;
  title: string | null;
  description: string | null;
  image: string | null;
  site_name: string | null;
}

export interface MessageSearchHit {
  message: Message;
  conversation_id: string;
  conversation_name: string | null;
  conversation_type: ConversationType;
  snippet: string;
}
