"use client";

import { memo, useEffect, useRef, useState } from "react";

import { timeOfDay } from "@/lib/format";
import type { Attachment, Message } from "@/lib/types";
import { Avatar } from "@/components/Avatar";
import { MessageAttachments } from "@/components/Attachments";
import {
  CopyIcon,
  EmojiIcon,
  KebabIcon,
  ReplyIcon,
  StatusTick,
  TimerIcon,
  TrashIcon,
} from "@/components/icons";

const QUICK_REACTIONS = ["👍", "❤️", "😂", "😮", "😢", "🙏"];

export interface BubbleProps {
  message: Message;
  outgoing: boolean;
  isGroup: boolean;
  senderName: string | null;
  senderAvatar: string | null;
  /** First message of a run by the same author - shows the name + avatar. */
  startsGroup: boolean;
  /** Last message of a run - carries the tail and the timestamp. */
  endsGroup: boolean;
  meId: string;
  onReply: (message: Message) => void;
  onDelete: (message: Message) => void;
  onReact: (message: Message, emoji: string) => void;
  onCopy: (text: string) => void;
  onOpenImage: (attachment: Attachment) => void;
}

function MessageBubbleBase({
  message,
  outgoing,
  isGroup,
  senderName,
  senderAvatar,
  startsGroup,
  endsGroup,
  meId,
  onReply,
  onDelete,
  onReact,
  onCopy,
  onOpenImage,
}: BubbleProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [reactionsOpen, setReactionsOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen && !reactionsOpen) return;
    const onDown = (event: MouseEvent) => {
      if (!wrapper.current?.contains(event.target as Node)) {
        setMenuOpen(false);
        setReactionsOpen(false);
      }
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [menuOpen, reactionsOpen]);

  // --- system message: a centred grey line, like Signal's group events ------
  if (message.type === "system") {
    return (
      <div className="my-3 flex justify-center px-6">
        <span className="rounded-full bg-sig-hover px-3 py-1 text-center text-[12.5px] leading-snug text-sig-text-2">
          {message.content}
        </span>
      </div>
    );
  }

  const deleted = message.deleted_at !== null;

  // Signal squares off the corner on the "tail" side for every message in a run
  // except the last, which keeps the full radius.
  const corner = outgoing
    ? endsGroup
      ? "rounded-br-[18px]"
      : "rounded-br-[5px]"
    : endsGroup
      ? "rounded-bl-[18px]"
      : "rounded-bl-[5px]";

  const grouped = message.reactions.reduce<Record<string, string[]>>((acc, reaction) => {
    (acc[reaction.emoji] ??= []).push(reaction.user_id);
    return acc;
  }, {});

  return (
    <div
      ref={wrapper}
      className={`group/message relative flex w-full gap-2 px-4 ${
        outgoing ? "justify-end" : "justify-start"
      } ${endsGroup ? "mb-2" : "mb-[2px]"}`}
    >
      {/* Group chats show the sender's avatar beside the last message of a run. */}
      {!outgoing && isGroup && (
        <div className="w-7 shrink-0 self-end">
          {endsGroup && (
            <Avatar name={senderName} src={senderAvatar} seed={message.sender_id} size={28} />
          )}
        </div>
      )}

      <div
        className={`flex max-w-[min(560px,72%)] flex-col ${
          outgoing ? "items-end" : "items-start"
        }`}
      >
        <div
          className={`relative rounded-[18px] px-3 py-[7px] ${corner} ${
            outgoing ? "text-white" : "text-sig-text"
          }`}
          style={{
            background: outgoing ? "var(--sig-bubble-out)" : "var(--sig-bubble-in)",
          }}
        >
          {/* Sender name on the first message of a run, in that person's colour. */}
          {!outgoing && isGroup && startsGroup && (
            <p className="mb-0.5 text-[13px] font-semibold text-ultramarine-light">
              {senderName ?? "Unknown"}
            </p>
          )}

          {message.reply_to && !deleted && (
            <button
              onClick={() => {
                document
                  .getElementById(`message-${message.reply_to?.id}`)
                  ?.scrollIntoView({ behavior: "smooth", block: "center" });
              }}
              className="mb-1.5 flex w-full gap-2 rounded-md px-2 py-1.5 text-left"
              style={{
                background: outgoing ? "rgba(255,255,255,0.16)" : "rgba(255,255,255,0.07)",
              }}
            >
              <span
                className="w-[3px] shrink-0 rounded-full"
                style={{ background: outgoing ? "#ffffff" : "var(--color-ultramarine-light)" }}
              />
              <span className="min-w-0">
                <span
                  className={`block text-[12.5px] font-semibold ${
                    outgoing ? "text-white/90" : "text-ultramarine-light"
                  }`}
                >
                  {message.reply_to.sender_id === meId
                    ? "You"
                    : (message.reply_to.sender_name ?? "Unknown")}
                </span>
                <span
                  className={`block truncate text-[13px] ${
                    outgoing ? "text-white/75" : "text-sig-text-2"
                  }`}
                >
                  {message.reply_to.preview}
                </span>
              </span>
            </button>
          )}

          {!deleted && message.attachments.length > 0 && (
            <MessageAttachments
              attachments={message.attachments}
              outgoing={outgoing}
              onOpenImage={onOpenImage}
            />
          )}

          {(deleted || message.content) && (
            <p
              className={`whitespace-pre-wrap break-words text-[14.5px] leading-[1.4] ${
                deleted ? "italic opacity-70" : ""
              }`}
            >
              {deleted ? "This message was deleted" : message.content}
              {/* Reserve space so the timestamp never overlaps the last word. */}
              <span className="pointer-events-none inline-block w-[62px] select-none" />
            </p>
          )}

          {/* An attachment-only bubble still needs room for the timestamp. */}
          {!deleted && !message.content && message.attachments.length > 0 && (
            <span className="block h-[15px]" />
          )}

          <span
            className={`absolute bottom-[6px] right-3 flex select-none items-center gap-1 text-[11px] ${
              outgoing ? "text-white/70" : "text-sig-text-3"
            }`}
          >
            {message.edited_at && !deleted && <span className="italic">edited</span>}
            {message.expires_at && !deleted && (
              <TimerIcon
                size={11}
                strokeWidth={2.2}
                className={outgoing ? "text-white/70" : "text-sig-text-3"}
              />
            )}
            <span>{timeOfDay(message.created_at)}</span>
            {outgoing && !deleted && (
              <StatusTick
                status={message.status}
                // Signal draws ticks in the bubble's contrast colour; a literal
                // blue tick would vanish on a blue bubble, so "read" gets a
                // light blue that stays legible and unmistakably different from
                // the muted white of sent/delivered.
                className={
                  message.status === "read" ? "text-[#B9D3FF]" : "text-white/65"
                }
              />
            )}
          </span>
        </div>

        {Object.keys(grouped).length > 0 && (
          <div
            className={`-mt-2 flex gap-1 rounded-full border px-1.5 py-0.5 ${
              outgoing ? "mr-2" : "ml-2"
            }`}
            style={{
              background: "var(--sig-elevated)",
              borderColor: "var(--sig-border)",
            }}
          >
            {Object.entries(grouped).map(([emoji, userIds]) => (
              <button
                key={emoji}
                onClick={() => onReact(message, emoji)}
                title={userIds.includes(meId) ? "Remove your reaction" : "React"}
                className={`flex items-center gap-0.5 rounded-full px-1 text-[13px] transition-transform hover:scale-110 ${
                  userIds.includes(meId) ? "text-ultramarine-light" : ""
                }`}
              >
                <span>{emoji}</span>
                {userIds.length > 1 && (
                  <span className="text-[11px] text-sig-text-2">{userIds.length}</span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Hover toolbar - Signal reveals these on the side of the bubble. */}
      {!deleted && (
        <div
          className={`absolute top-1 flex items-center gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover/message:opacity-100 ${
            outgoing ? "right-full mr-1" : "left-full ml-1"
          }`}
        >
          <IconAction label="React" onClick={() => setReactionsOpen((open) => !open)}>
            <EmojiIcon size={16} />
          </IconAction>
          <IconAction label="Reply" onClick={() => onReply(message)}>
            <ReplyIcon size={16} />
          </IconAction>
          <IconAction label="More" onClick={() => setMenuOpen((open) => !open)}>
            <KebabIcon size={16} />
          </IconAction>
        </div>
      )}

      {reactionsOpen && (
        <div
          className={`animate-pop absolute -top-9 z-20 flex gap-1 rounded-full border px-2 py-1.5 ${
            outgoing ? "right-4" : "left-4"
          }`}
          style={{
            background: "var(--sig-elevated)",
            borderColor: "var(--sig-border)",
            boxShadow: "var(--sig-shadow)",
          }}
        >
          {QUICK_REACTIONS.map((emoji) => (
            <button
              key={emoji}
              onClick={() => {
                onReact(message, emoji);
                setReactionsOpen(false);
              }}
              className="rounded-full px-1 text-[18px] transition-transform hover:scale-125"
            >
              {emoji}
            </button>
          ))}
        </div>
      )}

      {menuOpen && (
        <div
          className={`animate-pop absolute top-8 z-20 w-40 overflow-hidden rounded-lg border py-1 ${
            outgoing ? "right-8" : "left-8"
          }`}
          style={{
            background: "var(--sig-elevated)",
            borderColor: "var(--sig-border)",
            boxShadow: "var(--sig-shadow)",
          }}
        >
          <MenuItem
            icon={<ReplyIcon size={15} />}
            label="Reply"
            onClick={() => {
              onReply(message);
              setMenuOpen(false);
            }}
          />
          <MenuItem
            icon={<CopyIcon size={15} />}
            label="Copy text"
            onClick={() => {
              onCopy(message.content ?? "");
              setMenuOpen(false);
            }}
          />
          {outgoing && (
            <MenuItem
              icon={<TrashIcon size={15} />}
              label="Delete"
              danger
              onClick={() => {
                onDelete(message);
                setMenuOpen(false);
              }}
            />
          )}
        </div>
      )}
    </div>
  );
}

function IconAction({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className="focus-ring flex h-7 w-7 items-center justify-center rounded-full text-sig-text-3 transition-colors hover:bg-sig-hover hover:text-sig-text"
    >
      {children}
    </button>
  );
}

function MenuItem({
  icon,
  label,
  onClick,
  danger = false,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center gap-2.5 px-3 py-2 text-left text-[14px] transition-colors hover:bg-sig-hover ${
        danger ? "text-sig-danger" : "text-sig-text"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

export const MessageBubble = memo(MessageBubbleBase);
